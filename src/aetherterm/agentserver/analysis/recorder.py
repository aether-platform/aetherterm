"""アクティビティレコーダー

作業アクティビティをリアルタイムで記録し、
レポート生成のためのデータを収集します。
"""

import asyncio
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from aetherterm.common.report_models import ActivityType, WorkActivity

logger = logging.getLogger(__name__)


class ActivityRecorder:
    """作業アクティビティをリアルタイムで記録

    コマンド実行、ファイル操作、エージェントアクションなどを
    時系列で記録し、レポート生成に使用します。
    """

    def __init__(self, buffer_size: int = 1000):
        self._buffer: List[WorkActivity] = []
        self._buffer_size = buffer_size
        self._current_context: Dict[str, Any] = {}
        self._session_activities: Dict[str, List[WorkActivity]] = {}
        self._lock = asyncio.Lock()

    async def record_command(
        self,
        session_id: str,
        command: str,
        output: str,
        exit_code: int,
        duration: float,
        agent_id: Optional[str] = None,
    ) -> None:
        """コマンド実行を記録

        Args:
            session_id: セッションID
            command: 実行されたコマンド
            output: コマンドの出力
            exit_code: 終了コード
            duration: 実行時間（秒）
            agent_id: 実行したエージェントのID
        """
        # コマンドの要約を生成
        summary = self._summarize_command(command, output, exit_code)

        # タグを抽出
        tags = self._extract_command_tags(command)

        activity = WorkActivity(
            timestamp=datetime.utcnow(),
            activity_type=ActivityType.COMMAND,
            title=f"コマンド実行: {command.split()[0] if command else 'unknown'}",
            description=summary,
            agent_id=agent_id,
            command=command,
            exit_code=exit_code,
            duration_seconds=duration,
            tags=tags,
            metadata={
                "output_lines": len(output.splitlines()),
                "output_preview": output[:200] if output else "",
            },
        )

        await self._add_activity(session_id, activity)

    async def record_file_operation(
        self,
        session_id: str,
        file_path: str,
        action: str,
        diff: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> None:
        """ファイル操作を記録

        Args:
            session_id: セッションID
            file_path: ファイルパス
            action: 操作タイプ（create, edit, delete）
            diff: 変更差分
            agent_id: 実行したエージェントのID
        """
        # アクティビティタイプを決定
        activity_type = {
            "create": ActivityType.FILE_CREATE,
            "created": ActivityType.FILE_CREATE,
            "edit": ActivityType.FILE_EDIT,
            "modified": ActivityType.FILE_EDIT,
            "delete": ActivityType.FILE_DELETE,
            "deleted": ActivityType.FILE_DELETE,
        }.get(action.lower(), ActivityType.FILE_EDIT)

        # アクションの日本語表記
        action_jp = {
            "create": "作成",
            "created": "作成",
            "edit": "編集",
            "modified": "編集",
            "delete": "削除",
            "deleted": "削除",
        }.get(action.lower(), action)

        activity = WorkActivity(
            timestamp=datetime.utcnow(),
            activity_type=activity_type,
            title=f"ファイル{action_jp}: {os.path.basename(file_path)}",
            description=self._summarize_file_change(file_path, action, diff),
            agent_id=agent_id,
            file_path=file_path,
            file_action=action,
            diff=diff[:1000] if diff else None,  # 差分は最大1000文字
            tags=self._extract_file_tags(file_path),
            metadata={
                "file_extension": os.path.splitext(file_path)[1],
                "directory": os.path.dirname(file_path),
            },
        )

        await self._add_activity(session_id, activity)

    async def record_agent_action(
        self,
        session_id: str,
        agent_id: str,
        action: str,
        description: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """エージェントアクションを記録

        Args:
            session_id: セッションID
            agent_id: エージェントID
            action: アクションタイプ
            description: アクションの説明
            metadata: 追加のメタデータ
        """
        activity = WorkActivity(
            timestamp=datetime.utcnow(),
            activity_type=ActivityType.AGENT_ACTION,
            title=action,
            description=description,
            agent_id=agent_id,
            tags=["agent", agent_id],
            metadata=metadata or {},
        )

        await self._add_activity(session_id, activity)

    async def record_code_generation(
        self,
        session_id: str,
        description: str,
        code: str,
        language: str,
        agent_id: Optional[str] = None,
    ) -> None:
        """コード生成を記録

        Args:
            session_id: セッションID
            description: 生成内容の説明
            code: 生成されたコード
            language: プログラミング言語
            agent_id: 生成したエージェントのID
        """
        activity = WorkActivity(
            timestamp=datetime.utcnow(),
            activity_type=ActivityType.CODE_GENERATION,
            title="コード生成",
            description=description,
            agent_id=agent_id,
            generated_content=code[:500],  # 最初の500文字
            tags=["code", language],
            metadata={
                "language": language,
                "lines": len(code.splitlines()),
                "characters": len(code),
            },
        )

        await self._add_activity(session_id, activity)

    async def record_user_intervention(
        self,
        session_id: str,
        intervention_type: str,
        message: str,
        response: Any,
        response_time: float,
        agent_id: Optional[str] = None,
    ) -> None:
        """ユーザー介入を記録

        Args:
            session_id: セッションID
            intervention_type: 介入タイプ
            message: 介入要求メッセージ
            response: ユーザーの応答
            response_time: 応答時間（秒）
            agent_id: 要求元エージェントのID
        """
        activity = WorkActivity(
            timestamp=datetime.utcnow(),
            activity_type=ActivityType.USER_INTERVENTION,
            title=f"ユーザー介入: {intervention_type}",
            description=f"{message} → {response}",
            agent_id=agent_id,
            duration_seconds=response_time,
            tags=["intervention", intervention_type],
            metadata={"intervention_type": intervention_type, "response": str(response)},
        )

        await self._add_activity(session_id, activity)

    async def record_error(
        self,
        session_id: str,
        error_type: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        agent_id: Optional[str] = None,
    ) -> None:
        """エラーを記録

        Args:
            session_id: セッションID
            error_type: エラータイプ
            message: エラーメッセージ
            details: エラーの詳細
            agent_id: 関連するエージェントのID
        """
        activity = WorkActivity(
            timestamp=datetime.utcnow(),
            activity_type=ActivityType.ERROR,
            title=f"エラー: {error_type}",
            description=message,
            agent_id=agent_id,
            tags=["error", error_type],
            metadata=details or {},
        )

        await self._add_activity(session_id, activity)

    async def get_session_activities(
        self,
        session_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[WorkActivity]:
        """セッションのアクティビティを取得

        Args:
            session_id: セッションID
            start_time: 開始時刻（含む）
            end_time: 終了時刻（含む）

        Returns:
            List[WorkActivity]: アクティビティのリスト
        """
        async with self._lock:
            activities = self._session_activities.get(session_id, [])

            if start_time or end_time:
                filtered = []
                for activity in activities:
                    if start_time and activity.timestamp < start_time:
                        continue
                    if end_time and activity.timestamp > end_time:
                        continue
                    filtered.append(activity)
                return filtered

            return activities.copy()

    async def clear_session(self, session_id: str) -> None:
        """セッションのアクティビティをクリア"""
        async with self._lock:
            self._session_activities.pop(session_id, None)

    def update_context(self, key: str, value: Any) -> None:
        """現在のコンテキストを更新"""
        self._current_context[key] = value

    def get_context(self) -> Dict[str, Any]:
        """現在のコンテキストを取得"""
        return self._current_context.copy()

    async def _add_activity(self, session_id: str, activity: WorkActivity) -> None:
        """アクティビティを追加"""
        async with self._lock:
            # バッファに追加
            self._buffer.append(activity)
            if len(self._buffer) > self._buffer_size:
                self._buffer = self._buffer[-self._buffer_size :]

            # セッション別に保存
            if session_id not in self._session_activities:
                self._session_activities[session_id] = []

            self._session_activities[session_id].append(activity)

    def _summarize_command(self, command: str, output: str, exit_code: int) -> str:
        """コマンドを要約"""
        if exit_code == 0:
            status = "正常終了"
        else:
            status = f"エラー終了 (exit code: {exit_code})"

        # 出力から重要な情報を抽出
        output_lines = output.splitlines()
        if len(output_lines) > 5:
            output_summary = f"出力: {len(output_lines)}行"
        elif output_lines:
            output_summary = f"出力: {output_lines[0][:50]}..."
        else:
            output_summary = "出力なし"

        return f"{command} - {status} - {output_summary}"

    def _summarize_file_change(self, file_path: str, action: str, diff: Optional[str]) -> str:
        """ファイル変更を要約"""
        summary_parts = [f"{file_path} を{action}しました"]

        if diff:
            # 差分から変更行数を計算
            added_lines = len([l for l in diff.splitlines() if l.startswith("+")])
            removed_lines = len([l for l in diff.splitlines() if l.startswith("-")])

            if added_lines or removed_lines:
                summary_parts.append(f"(+{added_lines}行, -{removed_lines}行)")

        return " ".join(summary_parts)

    def _extract_command_tags(self, command: str) -> List[str]:
        """コマンドからタグを抽出"""
        tags = []

        # コマンド名を抽出
        cmd_parts = command.split()
        if cmd_parts:
            cmd_name = cmd_parts[0]
            tags.append(f"cmd:{cmd_name}")

            # 一般的なコマンドのカテゴリを追加
            if cmd_name in ["git", "svn", "hg"]:
                tags.append("vcs")
            elif cmd_name in ["npm", "yarn", "pnpm", "pip", "poetry", "cargo"]:
                tags.append("package")
            elif cmd_name in ["docker", "podman", "kubectl"]:
                tags.append("container")
            elif cmd_name in ["make", "cmake", "gradle", "mvn"]:
                tags.append("build")
            elif cmd_name in ["python", "node", "ruby", "go", "rust"]:
                tags.append("runtime")

        return tags

    def _extract_file_tags(self, file_path: str) -> List[str]:
        """ファイルパスからタグを抽出"""
        tags = []

        # 拡張子
        ext = os.path.splitext(file_path)[1].lower()
        if ext:
            tags.append(f"ext:{ext}")

            # ファイルタイプ
            if ext in [".py", ".pyw"]:
                tags.append("python")
            elif ext in [".js", ".mjs", ".jsx"]:
                tags.append("javascript")
            elif ext in [".ts", ".tsx"]:
                tags.append("typescript")
            elif ext in [".java", ".class", ".jar"]:
                tags.append("java")
            elif ext in [".c", ".h", ".cpp", ".hpp", ".cc"]:
                tags.append("c/c++")
            elif ext in [".go"]:
                tags.append("go")
            elif ext in [".rs"]:
                tags.append("rust")
            elif ext in [".md", ".rst", ".txt"]:
                tags.append("docs")
            elif ext in [".json", ".yaml", ".yml", ".toml", ".ini"]:
                tags.append("config")

        # ディレクトリベース
        dir_path = os.path.dirname(file_path).lower()
        if "test" in dir_path:
            tags.append("test")
        if "doc" in dir_path:
            tags.append("docs")
        if "src" in dir_path or "lib" in dir_path:
            tags.append("source")

        return tags
