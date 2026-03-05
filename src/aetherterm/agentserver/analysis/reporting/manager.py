"""レポートマネージャー

実行レポートと時系列作業レポートの生成・管理を行います。
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from aetherterm.common.report_models import (
    AgentExecution,
    ExecutionReport,
    ExecutionStep,
    ReportType,
    TimelineReport,
    UserIntervention,
)

from ..recorder import ActivityRecorder
from .templates import ReportTemplate
from .timeline_generator import TimelineReportGenerator

logger = logging.getLogger(__name__)


class SessionRecorder:
    """セッション記録"""

    def __init__(self, session_id: str, title: str, description: str):
        self.session_id = session_id
        self.title = title
        self.description = description
        self.started_at = datetime.utcnow()
        self.agent_executions: Dict[str, AgentExecution] = {}
        self.interventions: List[UserIntervention] = []
        self.artifacts: Dict[str, Any] = {}
        self.generated_files: List[str] = []
        self.modified_files: List[str] = []
        self.errors: List[Dict[str, Any]] = []
        self.warnings: List[Dict[str, Any]] = []
        self.metrics: Dict[str, float] = {}

    def add_agent_execution(self, agent_id: str, agent_type: str, task_id: UUID) -> None:
        """エージェント実行を追加"""
        self.agent_executions[agent_id] = AgentExecution(
            agent_id=agent_id, agent_type=agent_type, task_id=task_id
        )

    def complete_agent_execution(self, agent_id: str, status: str = "completed") -> None:
        """エージェント実行を完了"""
        if agent_id in self.agent_executions:
            execution = self.agent_executions[agent_id]
            execution.completed_at = datetime.utcnow()
            execution.status = status


class ReportStorage:
    """レポートストレージ"""

    def __init__(self, base_path: str = "./reports"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    async def save_report(
        self, report: Union[ExecutionReport, TimelineReport], format: str = "json"
    ) -> str:
        """レポートを保存

        Args:
            report: レポート
            format: 保存フォーマット（json, markdown）

        Returns:
            str: 保存されたファイルパス
        """
        # レポートタイプに基づいてディレクトリを作成
        if isinstance(report, ExecutionReport):
            report_dir = self.base_path / "execution" / report.session_id
        else:
            report_dir = self.base_path / "timeline" / report.session_id

        report_dir.mkdir(parents=True, exist_ok=True)

        # ファイル名を生成
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

        if format == "json":
            file_path = report_dir / f"report_{timestamp}.json"
            content = json.dumps(report.to_dict(), indent=2, ensure_ascii=False)
        elif format == "markdown":
            file_path = report_dir / f"report_{timestamp}.md"
            template = ReportTemplate()
            if isinstance(report, ExecutionReport):
                content = template.generate_execution_report_markdown(report)
            else:
                content = template.generate_timeline_report_markdown(report)
        else:
            raise ValueError(f"不明なフォーマット: {format}")

        # ファイルに保存
        file_path.write_text(content, encoding="utf-8")

        logger.info(f"レポートを保存しました: {file_path}")
        return str(file_path)

    async def list_reports(
        self,
        report_type: Optional[ReportType] = None,
        session_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """レポート一覧を取得

        Args:
            report_type: レポートタイプ
            session_id: セッションID
            limit: 取得数制限

        Returns:
            List[Dict[str, Any]]: レポートメタデータのリスト
        """
        reports = []

        # 検索対象ディレクトリを決定
        if report_type == ReportType.EXECUTION_DETAIL:
            search_dirs = [self.base_path / "execution"]
        elif report_type == ReportType.TIMELINE_ACTIVITY:
            search_dirs = [self.base_path / "timeline"]
        else:
            search_dirs = [self.base_path / "execution", self.base_path / "timeline"]

        for search_dir in search_dirs:
            if not search_dir.exists():
                continue

            # セッションIDでフィルタ
            if session_id:
                session_dirs = [search_dir / session_id]
            else:
                session_dirs = [d for d in search_dir.iterdir() if d.is_dir()]

            for session_dir in session_dirs:
                if not session_dir.exists():
                    continue

                # レポートファイルを検索
                for report_file in sorted(session_dir.glob("report_*.json"), reverse=True):
                    if len(reports) >= limit:
                        break

                    try:
                        # メタデータを読み込み
                        with open(report_file, encoding="utf-8") as f:
                            data = json.load(f)

                        reports.append(
                            {
                                "file_path": str(report_file),
                                "report_id": data.get("report_id"),
                                "session_id": data.get("session_id"),
                                "title": data.get("title"),
                                "created_at": data.get("created_at"),
                                "report_type": "execution"
                                if "execution" in str(report_file)
                                else "timeline",
                            }
                        )
                    except Exception as e:
                        logger.warning(f"レポートファイルの読み込みに失敗: {report_file} - {e}")

        return reports[:limit]


class ReportManager:
    """レポートマネージャー

    実行レポートの生成と管理を行います。
    """

    def __init__(self, activity_recorder: ActivityRecorder, storage_path: str = "./reports"):
        self._activity_recorder = activity_recorder
        self._active_sessions: Dict[str, SessionRecorder] = {}
        self._report_storage = ReportStorage(storage_path)
        self._timeline_generator = TimelineReportGenerator(activity_recorder)
        self._template = ReportTemplate()

    async def start_recording(self, session_id: str, title: str, description: str = "") -> None:
        """セッションの記録を開始

        Args:
            session_id: セッションID
            title: セッションタイトル
            description: セッションの説明
        """
        if session_id in self._active_sessions:
            logger.warning(f"セッション {session_id} は既に記録中です")
            return

        recorder = SessionRecorder(session_id, title, description)
        self._active_sessions[session_id] = recorder

        logger.info(f"セッション記録を開始しました: {session_id} - {title}")

    async def stop_recording(self, session_id: str) -> None:
        """セッションの記録を停止

        Args:
            session_id: セッションID
        """
        if session_id not in self._active_sessions:
            logger.warning(f"セッション {session_id} は記録されていません")
            return

        del self._active_sessions[session_id]
        logger.info(f"セッション記録を停止しました: {session_id}")

    async def record_agent_start(
        self, session_id: str, agent_id: str, agent_type: str, task_id: UUID
    ) -> None:
        """エージェント開始を記録"""
        recorder = self._active_sessions.get(session_id)
        if recorder:
            recorder.add_agent_execution(agent_id, agent_type, task_id)

    async def record_agent_complete(
        self, session_id: str, agent_id: str, status: str = "completed"
    ) -> None:
        """エージェント完了を記録"""
        recorder = self._active_sessions.get(session_id)
        if recorder:
            recorder.complete_agent_execution(agent_id, status)

    async def record_agent_step(self, session_id: str, agent_id: str, step: ExecutionStep) -> None:
        """エージェントステップを記録"""
        recorder = self._active_sessions.get(session_id)
        if recorder and agent_id in recorder.agent_executions:
            recorder.agent_executions[agent_id].steps.append(step)

    async def record_intervention(self, session_id: str, intervention: UserIntervention) -> None:
        """ユーザー介入を記録"""
        recorder = self._active_sessions.get(session_id)
        if recorder:
            recorder.interventions.append(intervention)

        # アクティビティとしても記録
        await self._activity_recorder.record_user_intervention(
            session_id=session_id,
            intervention_type=intervention.type,
            message=intervention.message,
            response=intervention.user_response,
            response_time=intervention.response_time_seconds or 0.0,
        )

    async def record_file_generated(self, session_id: str, file_path: str) -> None:
        """生成ファイルを記録"""
        recorder = self._active_sessions.get(session_id)
        if recorder:
            recorder.generated_files.append(file_path)

    async def record_file_modified(self, session_id: str, file_path: str) -> None:
        """変更ファイルを記録"""
        recorder = self._active_sessions.get(session_id)
        if recorder:
            recorder.modified_files.append(file_path)

    async def record_error(
        self,
        session_id: str,
        error_type: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """エラーを記録"""
        recorder = self._active_sessions.get(session_id)
        if recorder:
            recorder.errors.append(
                {
                    "timestamp": datetime.utcnow().isoformat(),
                    "type": error_type,
                    "message": message,
                    "details": details or {},
                }
            )

    async def record_warning(
        self,
        session_id: str,
        warning_type: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """警告を記録"""
        recorder = self._active_sessions.get(session_id)
        if recorder:
            recorder.warnings.append(
                {
                    "timestamp": datetime.utcnow().isoformat(),
                    "type": warning_type,
                    "message": message,
                    "details": details or {},
                }
            )

    async def update_metrics(self, session_id: str, metrics: Dict[str, float]) -> None:
        """メトリクスを更新"""
        recorder = self._active_sessions.get(session_id)
        if recorder:
            recorder.metrics.update(metrics)

    async def generate_execution_report(
        self, session_id: str, save: bool = True, format: str = "markdown"
    ) -> Union[ExecutionReport, str]:
        """実行詳細レポートを生成

        Args:
            session_id: セッションID
            save: レポートを保存するか
            format: 出力フォーマット（markdown, json）

        Returns:
            Union[ExecutionReport, str]: レポートまたは保存パス
        """
        recorder = self._active_sessions.get(session_id)
        activities = await self._activity_recorder.get_session_activities(session_id)

        if not recorder and not activities:
            raise ValueError(f"セッション {session_id} のデータが見つかりません")

        # レポートを構築
        report = ExecutionReport(
            session_id=session_id,
            title=recorder.title if recorder else f"実行レポート - {session_id}",
            description=recorder.description if recorder else "",
            created_at=datetime.utcnow(),
        )

        if recorder:
            # セッション記録からデータを取得
            report.agent_executions = list(recorder.agent_executions.values())
            report.intervention_details = [
                {
                    "timestamp": ui.timestamp.isoformat(),
                    "type": ui.type,
                    "message": ui.message,
                    "response": ui.user_response,
                    "response_time": ui.response_time_seconds,
                }
                for ui in recorder.interventions
            ]
            report.generated_files = recorder.generated_files
            report.modified_files = recorder.modified_files
            report.errors = recorder.errors
            report.warnings = recorder.warnings
            report.performance_metrics = recorder.metrics

            # 統計を計算
            total_steps = sum(len(ae.steps) for ae in report.agent_executions)
            failed_steps = sum(
                1 for ae in report.agent_executions for step in ae.steps if step.status == "failed"
            )

            report.total_steps = total_steps
            report.failed_steps = failed_steps
            report.success_rate = (
                (total_steps - failed_steps) / total_steps if total_steps > 0 else 1.0
            )
            report.total_interventions = len(recorder.interventions)

            # 実行時間を計算
            if recorder.started_at:
                report.total_duration_seconds = (
                    datetime.utcnow() - recorder.started_at
                ).total_seconds()

        # レポートを保存
        if save:
            save_path = await self._report_storage.save_report(report, format)
            return save_path

        return report

    async def generate_timeline_report(
        self,
        session_id: str,
        period_start: Optional[datetime] = None,
        period_end: Optional[datetime] = None,
        auto_section: bool = True,
        save: bool = True,
        format: str = "markdown",
    ) -> Union[TimelineReport, str]:
        """時系列作業レポートを生成

        Args:
            session_id: セッションID
            period_start: 開始時刻
            period_end: 終了時刻
            auto_section: 自動セクション分け
            save: レポートを保存するか
            format: 出力フォーマット

        Returns:
            Union[TimelineReport, str]: レポートまたは保存パス
        """
        report = await self._timeline_generator.generate_timeline_report(
            session_id=session_id,
            period_start=period_start,
            period_end=period_end,
            auto_section=auto_section,
        )

        # レポートを保存
        if save:
            save_path = await self._report_storage.save_report(report, format)
            return save_path

        return report

    async def get_live_summary(self, session_id: str) -> Dict[str, Any]:
        """実行中のサマリーを取得

        Args:
            session_id: セッションID

        Returns:
            Dict[str, Any]: ライブサマリー
        """
        recorder = self._active_sessions.get(session_id)
        activities = await self._activity_recorder.get_session_activities(session_id)

        if not recorder:
            return {"error": "セッションが記録されていません"}

        # 現在の状態を集計
        active_agents = sum(
            1 for ae in recorder.agent_executions.values() if ae.status == "running"
        )

        completed_agents = sum(
            1 for ae in recorder.agent_executions.values() if ae.status == "completed"
        )

        recent_activities = activities[-10:] if activities else []

        return {
            "session_id": session_id,
            "title": recorder.title,
            "started_at": recorder.started_at.isoformat(),
            "duration_seconds": (datetime.utcnow() - recorder.started_at).total_seconds(),
            "active_agents": active_agents,
            "completed_agents": completed_agents,
            "total_activities": len(activities),
            "total_interventions": len(recorder.interventions),
            "generated_files": len(recorder.generated_files),
            "modified_files": len(recorder.modified_files),
            "errors": len(recorder.errors),
            "warnings": len(recorder.warnings),
            "recent_activities": [
                {
                    "timestamp": a.timestamp.isoformat(),
                    "type": a.activity_type.value,
                    "title": a.title,
                    "description": a.description[:100],
                }
                for a in recent_activities
            ],
        }

    async def list_reports(
        self,
        report_type: Optional[ReportType] = None,
        session_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """レポート一覧を取得"""
        return await self._report_storage.list_reports(
            report_type=report_type, session_id=session_id, limit=limit
        )
