"""時系列レポート生成器

作業アクティビティを時系列で整理し、
読みやすい作業レポートを生成します。
"""

import logging
import os
from datetime import datetime, timedelta
from typing import List, Optional

from ..common.report_models import (
    ActivityType,
    TimelineReport,
    WorkActivity,
    WorkSection,
)
from .activity_recorder import ActivityRecorder

logger = logging.getLogger(__name__)


class TimelineReportGenerator:
    """時系列レポート生成器

    アクティビティを分析し、意味のあるセクションに分割して
    時系列レポートを生成します。
    """

    def __init__(self, activity_recorder: ActivityRecorder):
        self.activity_recorder = activity_recorder

    async def generate_timeline_report(
        self,
        session_id: str,
        period_start: Optional[datetime] = None,
        period_end: Optional[datetime] = None,
        auto_section: bool = True,
    ) -> TimelineReport:
        """時系列レポートを生成

        Args:
            session_id: セッションID
            period_start: 開始時刻
            period_end: 終了時刻
            auto_section: 自動セクション分け

        Returns:
            TimelineReport: 生成されたレポート
        """
        # アクティビティを収集
        activities = await self.activity_recorder.get_session_activities(
            session_id, period_start, period_end
        )

        if not activities:
            logger.warning(f"セッション {session_id} にアクティビティがありません")
            return TimelineReport(
                session_id=session_id,
                title=f"作業レポート - {session_id}",
                period_start=period_start or datetime.utcnow(),
                period_end=period_end or datetime.utcnow(),
            )

        # 期間を決定
        if not period_start:
            period_start = activities[0].timestamp
        if not period_end:
            period_end = activities[-1].timestamp

        # レポートを初期化
        report = TimelineReport(
            session_id=session_id,
            title=f"作業レポート - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            period_start=period_start,
            period_end=period_end,
            raw_activities=activities,
        )

        # セクション分け
        if auto_section:
            sections = await self._auto_create_sections(activities)
        else:
            sections = [
                WorkSection(
                    title="全アクティビティ",
                    started_at=activities[0].timestamp,
                    completed_at=activities[-1].timestamp,
                    activities=activities,
                    summary="すべての作業アクティビティ",
                )
            ]

        report.work_sections = sections

        # 統計を集計
        self._calculate_statistics(report)

        # サマリーを生成
        self._generate_summaries(report)

        return report

    async def _auto_create_sections(self, activities: List[WorkActivity]) -> List[WorkSection]:
        """アクティビティを自動的にセクション分け

        Args:
            activities: アクティビティリスト

        Returns:
            List[WorkSection]: セクションのリスト
        """
        if not activities:
            return []

        sections = []
        current_section_activities = []
        current_theme = None
        last_timestamp = None

        # 時間間隔の閾値（30分以上離れたら新セクション）
        time_threshold = timedelta(minutes=30)

        for activity in activities:
            # 新しいセクションが必要かチェック
            need_new_section = False

            # 時間が大きく離れている場合
            if last_timestamp and (activity.timestamp - last_timestamp) > time_threshold:
                need_new_section = True

            # テーマが変わった場合
            new_theme = self._detect_activity_theme(activity)
            if current_theme and new_theme != current_theme:
                # ただし、関連性が高い場合は同じセクションに含める
                if not self._are_themes_related(current_theme, new_theme):
                    need_new_section = True

            # 新しいセクションを作成
            if need_new_section and current_section_activities:
                section = await self._create_section(current_section_activities)
                sections.append(section)
                current_section_activities = []

            current_section_activities.append(activity)
            current_theme = new_theme
            last_timestamp = activity.timestamp

        # 最後のセクション
        if current_section_activities:
            section = await self._create_section(current_section_activities)
            sections.append(section)

        return sections

    async def _create_section(self, activities: List[WorkActivity]) -> WorkSection:
        """アクティビティからセクションを作成

        Args:
            activities: アクティビティリスト

        Returns:
            WorkSection: 作成されたセクション
        """
        if not activities:
            raise ValueError("アクティビティが空です")

        # セクションのタイトルとサマリーを生成
        title = self._generate_section_title(activities)
        summary = self._generate_section_summary(activities)

        # ゴール達成状況を判定
        goal_achieved = self._check_goal_achievement(activities)

        section = WorkSection(
            title=title,
            started_at=activities[0].timestamp,
            completed_at=activities[-1].timestamp,
            activities=activities,
            summary=summary,
            goal_achieved=goal_achieved,
        )

        return section

    def _detect_activity_theme(self, activity: WorkActivity) -> str:
        """アクティビティのテーマを検出"""
        # タグベースでテーマを判定
        if "test" in activity.tags:
            return "testing"
        if "docs" in activity.tags:
            return "documentation"
        if "build" in activity.tags:
            return "building"
        if "vcs" in activity.tags:
            return "version_control"
        if "package" in activity.tags:
            return "dependency_management"

        # アクティビティタイプベース
        if activity.activity_type in [ActivityType.FILE_CREATE, ActivityType.FILE_EDIT]:
            return "coding"
        if activity.activity_type == ActivityType.CODE_GENERATION:
            return "code_generation"
        if activity.activity_type == ActivityType.ERROR:
            return "error_handling"

        return "general"

    def _are_themes_related(self, theme1: str, theme2: str) -> bool:
        """2つのテーマが関連しているかチェック"""
        related_themes = {
            "coding": {"code_generation", "testing", "error_handling"},
            "testing": {"coding", "error_handling"},
            "documentation": {"coding"},
            "building": {"testing", "dependency_management"},
            "version_control": {"coding", "documentation"},
        }

        return theme2 in related_themes.get(theme1, set())

    def _generate_section_title(self, activities: List[WorkActivity]) -> str:
        """セクションのタイトルを生成"""
        # 主要なアクティビティタイプを特定
        type_counts = {}
        for activity in activities:
            type_counts[activity.activity_type] = type_counts.get(activity.activity_type, 0) + 1

        main_type = max(type_counts, key=type_counts.get)

        # タイトルマッピング
        title_map = {
            ActivityType.COMMAND: "コマンド実行",
            ActivityType.FILE_CREATE: "ファイル作成",
            ActivityType.FILE_EDIT: "ファイル編集",
            ActivityType.CODE_GENERATION: "コード生成",
            ActivityType.AGENT_ACTION: "エージェント操作",
            ActivityType.USER_INTERVENTION: "ユーザー対話",
            ActivityType.ERROR: "エラー対応",
        }

        base_title = title_map.get(main_type, "作業")

        # 具体的な内容を追加
        if main_type in [ActivityType.FILE_CREATE, ActivityType.FILE_EDIT]:
            # ファイル名を抽出
            file_names = set()
            for activity in activities:
                if activity.file_path:
                    file_names.add(os.path.basename(activity.file_path))

            if len(file_names) == 1:
                return f"{base_title}: {list(file_names)[0]}"
            if len(file_names) <= 3:
                return f"{base_title}: {', '.join(list(file_names)[:3])}"
            return f"{base_title}: {len(file_names)}個のファイル"

        return base_title

    def _generate_section_summary(self, activities: List[WorkActivity]) -> str:
        """セクションのサマリーを生成"""
        summaries = []

        # アクティビティタイプ別に集計
        type_counts = {}
        for activity in activities:
            type_counts[activity.activity_type] = type_counts.get(activity.activity_type, 0) + 1

        # サマリーを構築
        for activity_type, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
            if activity_type == ActivityType.COMMAND:
                summaries.append(f"{count}個のコマンドを実行")
            elif activity_type == ActivityType.FILE_CREATE:
                summaries.append(f"{count}個のファイルを作成")
            elif activity_type == ActivityType.FILE_EDIT:
                summaries.append(f"{count}個のファイルを編集")
            elif activity_type == ActivityType.CODE_GENERATION:
                summaries.append(f"{count}回のコード生成")
            elif activity_type == ActivityType.ERROR:
                summaries.append(f"{count}個のエラーが発生")

        # 実行時間を追加
        duration = activities[-1].timestamp - activities[0].timestamp
        if duration.total_seconds() > 60:
            minutes = int(duration.total_seconds() / 60)
            summaries.append(f"作業時間: {minutes}分")

        return "、".join(summaries[:3])  # 最大3つまで

    def _check_goal_achievement(self, activities: List[WorkActivity]) -> bool:
        """ゴール達成状況を判定"""
        # エラーが多い場合は未達成
        error_count = sum(1 for a in activities if a.activity_type == ActivityType.ERROR)
        if error_count > len(activities) * 0.3:  # 30%以上がエラー
            return False

        # 最後のアクティビティがエラーの場合は未達成
        if activities and activities[-1].activity_type == ActivityType.ERROR:
            return False

        # その他の場合は達成とみなす
        return True

    def _calculate_statistics(self, report: TimelineReport) -> None:
        """統計を計算"""
        activities = report.raw_activities

        # 基本統計
        report.total_activities = len(activities)
        report.total_commands = sum(
            1 for a in activities if a.activity_type == ActivityType.COMMAND
        )
        report.files_created = sum(
            1 for a in activities if a.activity_type == ActivityType.FILE_CREATE
        )
        report.files_modified = sum(
            1 for a in activities if a.activity_type == ActivityType.FILE_EDIT
        )

        # 総作業時間
        if activities:
            report.total_duration_seconds = (
                activities[-1].timestamp - activities[0].timestamp
            ).total_seconds()

    def _generate_summaries(self, report: TimelineReport) -> None:
        """サマリーを生成"""
        # 主な成果
        achievements = []

        if report.files_created > 0:
            achievements.append(f"{report.files_created}個の新規ファイルを作成")

        if report.files_modified > 0:
            achievements.append(f"{report.files_modified}個のファイルを更新")

        if report.total_commands > 10:
            achievements.append(f"{report.total_commands}個のコマンドを実行")

        # セクション別の成果
        for section in report.work_sections:
            if section.goal_achieved and section.title not in ["全アクティビティ", "作業"]:
                achievements.append(f"{section.title}を完了")

        report.key_achievements = achievements[:5]  # 最大5個

        # 発生した問題
        problems = []
        error_activities = [
            a for a in report.raw_activities if a.activity_type == ActivityType.ERROR
        ]

        if error_activities:
            error_types = set()
            for activity in error_activities:
                if "error_type" in activity.metadata:
                    error_types.add(activity.metadata["error_type"])

            if error_types:
                problems.append(f"エラータイプ: {', '.join(list(error_types)[:3])}")
            else:
                problems.append(f"{len(error_activities)}個のエラーが発生")

        report.problems_encountered = problems

        # 次のステップ（簡易的な推奨）
        next_steps = []

        if error_activities:
            next_steps.append("エラーの原因調査と修正")

        if report.files_created > 0 and "test" not in [a.title for a in report.raw_activities]:
            next_steps.append("作成したコードのテストを実行")

        if not any("docs" in a.tags for a in report.raw_activities):
            next_steps.append("ドキュメントの更新")

        report.next_steps = next_steps[:3]  # 最大3個
