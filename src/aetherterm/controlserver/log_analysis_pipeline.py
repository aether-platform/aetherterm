"""LogAnalysisPipeline — log compression + LLM analysis extracted from CentralController.

Owns ``_analysis_history`` state and orchestrates the compress → analyze → dispatch
pipeline.  Uses ``safe_create_task`` to avoid the bare ``asyncio.create_task`` antipattern.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict

from aetherterm.common.models import LogAnalysisResult
from aetherterm.common.zmq_utils import safe_create_task

from .llm_analyzer import LLMLogAnalyzer
from .log_analysis_config import LogAnalysisConfig
from .log_pattern_compressor import LogPatternCompressor

if TYPE_CHECKING:
    from .central_controller import CentralController

logger = logging.getLogger(__name__)


class LogAnalysisPipeline:
    """Compress → LLM-analyze → dispatch log analysis results."""

    def __init__(
        self,
        config: LogAnalysisConfig,
        compressor: LogPatternCompressor,
        analyzer: LLMLogAnalyzer,
        controller: CentralController,
    ) -> None:
        self._config = config
        self._compressor = compressor
        self._analyzer = analyzer
        self._ctrl = controller
        self._analysis_history: dict[str, list[LogAnalysisResult]] = {}

    # ------------------------------------------------------------------
    # Buffer flush callback (entry point from LogBufferManager)
    # ------------------------------------------------------------------

    async def on_log_flush(self, session_id: str, entries: list[dict]) -> None:
        """Buffer flush callback: spawn analysis as a safe background task."""
        safe_create_task(
            self._analyze_and_dispatch(session_id, entries),
            name=f"log-analysis-{session_id}",
            logger=logger,
        )

    # ------------------------------------------------------------------
    # Core pipeline
    # ------------------------------------------------------------------

    async def _analyze_and_dispatch(self, session_id: str, entries: list[dict]) -> None:
        """Compress → LLM analysis → broadcast results → auto-block if needed."""
        try:
            # 1. Pattern compression
            compressed = self._compressor.compress(session_id, entries)
            logger.info(
                f"Log compression for {session_id}: "
                f"{compressed.total_lines} lines → {compressed.unique_patterns} patterns "
                f"({compressed.compression_ratio:.1f}x)"
            )

            # 2. LLM analysis
            result = await self._analyzer.analyze(compressed)

            # 3. Save to history (keep last 10)
            if session_id not in self._analysis_history:
                self._analysis_history[session_id] = []
            self._analysis_history[session_id].append(result)
            if len(self._analysis_history[session_id]) > 10:
                self._analysis_history[session_id] = self._analysis_history[session_id][-10:]

            # 4. Broadcast to admins
            await self._ctrl.broadcast_to_admins(
                {
                    "type": "log_analysis_result",
                    "session_id": session_id,
                    "analysis_type": result.analysis_type,
                    "anomalies": result.anomalies,
                    "summary": result.summary,
                    "risk_level": result.risk_level,
                    "model_used": result.model_used,
                    "token_usage": result.token_usage,
                    "compression": {
                        "total_lines": compressed.total_lines,
                        "unique_patterns": compressed.unique_patterns,
                        "compression_ratio": compressed.compression_ratio,
                    },
                    "timestamp": result.timestamp,
                }
            )

            # 5. Auto-block on high/critical threat
            if result.risk_level in ("high", "critical"):
                await self._auto_block_on_threat(session_id, result)

        except Exception:
            logger.exception(f"Error in log analysis pipeline for session {session_id}")

    # ------------------------------------------------------------------
    # Auto-blocking
    # ------------------------------------------------------------------

    async def _auto_block_on_threat(
        self, session_id: str, result: LogAnalysisResult
    ) -> None:
        """Auto-block a session when LLM analysis detects high/critical threat."""
        if result.risk_level == "critical" and not self._config.auto_block_on_critical:
            logger.info(
                f"Critical risk for {session_id} but auto_block_on_critical disabled"
            )
            return
        if result.risk_level == "high" and not self._config.auto_block_on_high:
            logger.warning(
                f"High risk detected for {session_id} (auto-block disabled): {result.summary}"
            )
            await self._ctrl.broadcast_to_admins({
                "type": "threat_warning",
                "session_id": session_id,
                "risk_level": result.risk_level,
                "summary": result.summary,
                "timestamp": datetime.now().isoformat(),
            })
            return

        logger.warning(
            f"AI detected {result.risk_level} threat for session {session_id}, auto-blocking"
        )

        reason = (
            f"Auto-block: {result.risk_level} risk detected by LLM analysis. "
            f"{result.summary}"
        )

        # Prefer ZMQ targeted block
        if self._ctrl._zmq_controller:
            await self._ctrl._zmq_controller.send_block_input(
                session_id=session_id, reason=reason
            )

        # Record in legacy block tracking + notify admins
        await self._ctrl.execute_block_session(
            {
                "session_id": session_id,
                "reason": reason,
                "admin_user": "system_auto_block",
            }
        )

    # ------------------------------------------------------------------
    # On-demand query
    # ------------------------------------------------------------------

    async def handle_get_log_analysis(self, websocket: Any, data: dict) -> None:
        """Return analysis history for a session via WebSocket."""
        session_id = data.get("session_id", "")
        history = self._analysis_history.get(session_id, [])

        results = []
        for r in history:
            results.append(
                {
                    "analysis_type": r.analysis_type,
                    "anomalies": r.anomalies,
                    "summary": r.summary,
                    "risk_level": r.risk_level,
                    "timestamp": r.timestamp,
                    "model_used": r.model_used,
                    "token_usage": r.token_usage,
                }
            )

        await websocket.send(
            json.dumps(
                {
                    "type": "log_analysis_history",
                    "session_id": session_id,
                    "results": results,
                    "timestamp": datetime.now().isoformat(),
                }
            )
        )

    @property
    def analysis_history(self) -> dict[str, list[LogAnalysisResult]]:
        """Expose history for REST API access."""
        return self._analysis_history
