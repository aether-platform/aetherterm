"""
Context Inference Service - Application Layer

Service for context inference, pattern learning, and operation analytics.
Integrates with the context inference usecase for AI-powered terminal insights.
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

from aetherterm.agentserver.application.usecases.context_inference import (
    OperationPatternLearner,
    OperationContextInferenceEngine,
    OperationType,
    OperationStage,
    OperationContext,
    ContextInferenceResult,
)

log = logging.getLogger("aetherterm.services.context")


class ContextService:
    """
    Application service for context inference and pattern learning.

    Provides high-level interface for:
    - Learning operation patterns from terminal activities
    - Inferring current operation context
    - Providing predictions and suggestions
    - Analytics and insights
    """

    def __init__(self):
        self.pattern_learner = OperationPatternLearner()
        self.inference_engine = OperationContextInferenceEngine()
        self._active_sessions = {}

    async def initialize(self):
        """Initialize the context service and load existing patterns."""
        try:
            await self.pattern_learner.initialize()
            await self.inference_engine.initialize()
            log.info("Context service initialized successfully")
        except Exception as e:
            log.error(f"Failed to initialize context service: {e}")
            raise

    async def start_session_tracking(self, session_id: str, user_id: str = None) -> bool:
        """Start tracking context for a terminal session."""
        try:
            session_context = {
                "session_id": session_id,
                "user_id": user_id,
                "start_time": datetime.utcnow(),
                "command_history": [],
                "current_operation": None,
                "patterns": [],
                "working_directory": "/",
                "environment": {},
            }

            self._active_sessions[session_id] = session_context
            log.info(f"Started context tracking for session {session_id}")
            return True

        except Exception as e:
            log.error(f"Failed to start session tracking: {e}")
            return False

    async def track_command(
        self,
        session_id: str,
        command: str,
        working_directory: str = None,
        exit_code: int = None,
        output: str = None,
    ) -> Optional[ContextInferenceResult]:
        """Track a command execution and update context."""
        try:
            if session_id not in self._active_sessions:
                await self.start_session_tracking(session_id)

            session = self._active_sessions[session_id]

            # Update session state
            if working_directory:
                session["working_directory"] = working_directory

            # Add to command history
            command_entry = {
                "command": command,
                "timestamp": datetime.utcnow(),
                "working_directory": working_directory or session["working_directory"],
                "exit_code": exit_code,
                "output_length": len(output) if output else 0,
            }
            session["command_history"].append(command_entry)

            # Learn from the command pattern
            await self.pattern_learner.learn_from_command(
                command=command,
                context={
                    "working_directory": session["working_directory"],
                    "recent_commands": [c["command"] for c in session["command_history"][-5:]],
                    "session_duration": (datetime.utcnow() - session["start_time"]).total_seconds(),
                },
            )

            # Infer current operation context
            inference_result = await self.inference_engine.infer_context(
                current_command=command,
                command_history=session["command_history"],
                working_directory=session["working_directory"],
            )

            # Update current operation
            if inference_result and inference_result.operation_type:
                session["current_operation"] = {
                    "type": inference_result.operation_type,
                    "stage": inference_result.stage,
                    "confidence": inference_result.confidence,
                    "updated_at": datetime.utcnow(),
                }

            return inference_result

        except Exception as e:
            log.error(f"Failed to track command for session {session_id}: {e}")
            return None

    async def get_predictions(
        self, session_id: str, current_input: str = "", limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Get command predictions based on current context."""
        try:
            if session_id not in self._active_sessions:
                return []

            session = self._active_sessions[session_id]

            # Get predictions from inference engine
            predictions = await self.inference_engine.predict_next_commands(
                current_input=current_input,
                command_history=session["command_history"],
                working_directory=session["working_directory"],
                current_operation=session.get("current_operation"),
                limit=limit,
            )

            return predictions

        except Exception as e:
            log.error(f"Failed to get predictions for session {session_id}: {e}")
            return []

    async def get_session_analytics(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get analytics for a specific session."""
        try:
            if session_id not in self._active_sessions:
                return None

            session = self._active_sessions[session_id]
            command_history = session["command_history"]

            if not command_history:
                return None

            # Calculate basic analytics
            total_commands = len(command_history)
            session_duration = (datetime.utcnow() - session["start_time"]).total_seconds()
            commands_per_minute = (
                (total_commands / session_duration) * 60 if session_duration > 0 else 0
            )

            # Command frequency analysis
            command_freq = {}
            for cmd_entry in command_history:
                base_cmd = cmd_entry["command"].split()[0] if cmd_entry["command"] else "unknown"
                command_freq[base_cmd] = command_freq.get(base_cmd, 0) + 1

            # Most common commands
            most_common = sorted(command_freq.items(), key=lambda x: x[1], reverse=True)[:10]

            # Operation analysis
            current_op = session.get("current_operation", {})

            analytics = {
                "session_id": session_id,
                "total_commands": total_commands,
                "session_duration_seconds": session_duration,
                "commands_per_minute": round(commands_per_minute, 2),
                "most_common_commands": most_common,
                "current_operation": current_op,
                "working_directory": session["working_directory"],
                "start_time": session["start_time"].isoformat(),
                "last_command_time": command_history[-1]["timestamp"].isoformat()
                if command_history
                else None,
            }

            return analytics

        except Exception as e:
            log.error(f"Failed to get session analytics: {e}")
            return None

    async def get_operation_insights(
        self, session_id: str, operation_type: Optional[OperationType] = None
    ) -> Dict[str, Any]:
        """Get insights about operations and patterns."""
        try:
            # Get patterns from pattern learner
            insights = await self.pattern_learner.get_operation_insights(
                operation_type=operation_type, session_context=self._active_sessions.get(session_id)
            )

            return insights

        except Exception as e:
            log.error(f"Failed to get operation insights: {e}")
            return {}

    async def cleanup_session(self, session_id: str) -> bool:
        """Clean up tracking for a terminated session."""
        try:
            if session_id in self._active_sessions:
                session = self._active_sessions[session_id]

                # Save final session data for learning
                await self.pattern_learner.finalize_session(session)

                # Remove from active sessions
                del self._active_sessions[session_id]

                log.info(f"Cleaned up context tracking for session {session_id}")
                return True
            return False

        except Exception as e:
            log.error(f"Failed to cleanup session {session_id}: {e}")
            return False

    async def get_active_sessions(self) -> List[str]:
        """Get list of currently tracked sessions."""
        return list(self._active_sessions.keys())

    async def export_patterns(self) -> Dict[str, Any]:
        """Export learned patterns for backup or analysis."""
        try:
            return await self.pattern_learner.export_patterns()
        except Exception as e:
            log.error(f"Failed to export patterns: {e}")
            return {}

    async def import_patterns(self, patterns_data: Dict[str, Any]) -> bool:
        """Import patterns from backup or external source."""
        try:
            return await self.pattern_learner.import_patterns(patterns_data)
        except Exception as e:
            log.error(f"Failed to import patterns: {e}")
            return False
