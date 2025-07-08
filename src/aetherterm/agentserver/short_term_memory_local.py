"""
ローカル短期記憶分析システム - AgentServer側

短期記憶データを使ってAgentServer内で即座に分析・対応を行う
ControlServerに送信する前にローカルで実行可能な機能を提供
"""

import asyncio
import logging
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from uuid import uuid4

logger = logging.getLogger(__name__)


@dataclass
class MemoryPattern:
    """検出されたパターン"""

    pattern_id: str
    pattern_type: str  # error_spike, performance_degradation, user_behavior, command_sequence
    description: str
    severity: str  # info, warning, error, critical
    frequency: int
    first_seen: str
    last_seen: str
    sessions_affected: List[str]
    suggested_action: Optional[str] = None


@dataclass
class QuickInsight:
    """即座の洞察"""

    insight_id: str
    insight_type: str  # trend, anomaly, pattern, recommendation
    title: str
    description: str
    priority: str  # low, medium, high, urgent
    timestamp: str
    related_sessions: List[str]
    data: Dict


class LocalShortTermAnalyzer:
    """ローカル短期記憶分析システム"""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id

        # 短期記憶ストレージ（軽量）
        self.recent_commands = deque(maxlen=100)  # 最新100コマンド
        self.error_events = deque(maxlen=50)  # 最新50エラー
        self.performance_metrics = deque(maxlen=100)  # 最新100メトリクス
        self.user_interactions = deque(maxlen=200)  # 最新200インタラクション

        # パターン検出
        self.detected_patterns = []
        self.quick_insights = []

        # セッション別統計
        self.session_stats = defaultdict(
            lambda: {
                "command_count": 0,
                "error_count": 0,
                "last_activity": None,
                "performance_scores": [],
                "user_activity_level": "normal",
            }
        )

        # リアルタイム閾値
        self.error_spike_threshold = 5  # 5分間で5エラー以上
        self.slow_command_threshold = 2.0  # 2秒以上のコマンド
        self.frequent_error_threshold = 3  # 同じエラーが3回以上

        # タスク管理
        self.analysis_task = None

    async def start(self):
        """ローカル分析開始"""
        logger.info(f"Starting local short-term analyzer for agent {self.agent_id}")

        # リアルタイム分析タスクを開始
        self.analysis_task = asyncio.create_task(self._real_time_analysis_loop())

    async def stop(self):
        """ローカル分析停止"""
        if self.analysis_task:
            self.analysis_task.cancel()
            try:
                await self.analysis_task
            except asyncio.CancelledError:
                pass

        logger.info(f"Stopped local short-term analyzer for agent {self.agent_id}")

    def record_command(
        self, session_id: str, command: str, exit_code: int = None, execution_time: float = None
    ):
        """コマンド実行を記録"""

        entry = {
            "session_id": session_id,
            "command": command[:100],  # 最初の100文字
            "exit_code": exit_code,
            "execution_time": execution_time,
            "timestamp": datetime.utcnow().isoformat(),
        }

        self.recent_commands.append(entry)
        self.session_stats[session_id]["command_count"] += 1
        self.session_stats[session_id]["last_activity"] = entry["timestamp"]

        # リアルタイム分析
        asyncio.create_task(self._analyze_command_immediate(entry))

    def record_error(self, session_id: str, error_type: str, error_message: str):
        """エラーを記録"""

        entry = {
            "session_id": session_id,
            "error_type": error_type,
            "error_message": error_message[:200],
            "timestamp": datetime.utcnow().isoformat(),
        }

        self.error_events.append(entry)
        self.session_stats[session_id]["error_count"] += 1

        # リアルタイム分析
        asyncio.create_task(self._analyze_error_immediate(entry))

    def record_performance(self, session_id: str, metric_name: str, value: float, unit: str = None):
        """パフォーマンス指標を記録"""

        entry = {
            "session_id": session_id,
            "metric_name": metric_name,
            "value": value,
            "unit": unit,
            "timestamp": datetime.utcnow().isoformat(),
        }

        self.performance_metrics.append(entry)
        self.session_stats[session_id]["performance_scores"].append(value)

        # パフォーマンススコア管理（最新10件のみ保持）
        if len(self.session_stats[session_id]["performance_scores"]) > 10:
            self.session_stats[session_id]["performance_scores"] = self.session_stats[session_id][
                "performance_scores"
            ][-10:]

        # リアルタイム分析
        asyncio.create_task(self._analyze_performance_immediate(entry))

    def record_user_interaction(self, session_id: str, interaction_type: str, details: str = None):
        """ユーザーインタラクションを記録"""

        entry = {
            "session_id": session_id,
            "interaction_type": interaction_type,
            "details": details,
            "timestamp": datetime.utcnow().isoformat(),
        }

        self.user_interactions.append(entry)

        # ユーザー活動レベルの更新
        self._update_user_activity_level(session_id)

    async def _real_time_analysis_loop(self):
        """リアルタイム分析ループ"""
        while True:
            try:
                await asyncio.sleep(30)  # 30秒間隔
                await self._perform_pattern_analysis()
                await self._generate_quick_insights()
                await self._cleanup_old_data()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in real-time analysis loop: {e}")

    async def _analyze_command_immediate(self, command_entry: Dict):
        """コマンドの即座分析"""

        session_id = command_entry["session_id"]
        execution_time = command_entry.get("execution_time", 0)
        exit_code = command_entry.get("exit_code", 0)

        # 遅いコマンドの検出
        if execution_time and execution_time > self.slow_command_threshold:
            insight = QuickInsight(
                insight_id=str(uuid4()),
                insight_type="performance",
                title="遅いコマンド検出",
                description=f"コマンド実行が{execution_time:.2f}秒かかりました: {command_entry['command'][:50]}",
                priority="medium",
                timestamp=datetime.utcnow().isoformat(),
                related_sessions=[session_id],
                data={"execution_time": execution_time, "threshold": self.slow_command_threshold},
            )
            self.quick_insights.append(insight)

        # 連続するエラーコマンドの検出
        if exit_code != 0:
            recent_errors = [
                cmd
                for cmd in list(self.recent_commands)[-5:]
                if cmd["session_id"] == session_id and cmd.get("exit_code", 0) != 0
            ]

            if len(recent_errors) >= 3:
                insight = QuickInsight(
                    insight_id=str(uuid4()),
                    insight_type="anomaly",
                    title="連続コマンドエラー",
                    description=f"セッション {session_id} で連続してコマンドエラーが発生しています",
                    priority="high",
                    timestamp=datetime.utcnow().isoformat(),
                    related_sessions=[session_id],
                    data={"consecutive_errors": len(recent_errors)},
                )
                self.quick_insights.append(insight)

    async def _analyze_error_immediate(self, error_entry: Dict):
        """エラーの即座分析"""

        session_id = error_entry["session_id"]
        error_type = error_entry["error_type"]

        # エラースパイクの検出
        five_minutes_ago = datetime.utcnow() - timedelta(minutes=5)
        recent_errors = [
            err
            for err in self.error_events
            if datetime.fromisoformat(err["timestamp"].replace("Z", "+00:00")) >= five_minutes_ago
            and err["session_id"] == session_id
        ]

        if len(recent_errors) >= self.error_spike_threshold:
            insight = QuickInsight(
                insight_id=str(uuid4()),
                insight_type="anomaly",
                title="エラースパイク検出",
                description=f"セッション {session_id} で5分間に{len(recent_errors)}件のエラーが発生",
                priority="urgent",
                timestamp=datetime.utcnow().isoformat(),
                related_sessions=[session_id],
                data={"error_count": len(recent_errors), "time_window": "5min"},
            )
            self.quick_insights.append(insight)

        # 頻発エラーの検出
        same_error_count = sum(
            1
            for err in self.error_events
            if err["error_type"] == error_type and err["session_id"] == session_id
        )

        if same_error_count >= self.frequent_error_threshold:
            insight = QuickInsight(
                insight_id=str(uuid4()),
                insight_type="pattern",
                title="頻発エラー検出",
                description=f"エラータイプ '{error_type}' が{same_error_count}回発生しています",
                priority="high",
                timestamp=datetime.utcnow().isoformat(),
                related_sessions=[session_id],
                data={"error_type": error_type, "frequency": same_error_count},
            )
            self.quick_insights.append(insight)

    async def _analyze_performance_immediate(self, perf_entry: Dict):
        """パフォーマンスの即座分析"""

        session_id = perf_entry["session_id"]
        metric_name = perf_entry["metric_name"]
        value = perf_entry["value"]

        # パフォーマンス劣化の検出（平均より50%以上悪い場合）
        session_scores = self.session_stats[session_id]["performance_scores"]
        if len(session_scores) >= 3:
            avg_score = sum(session_scores[:-1]) / len(session_scores[:-1])  # 最新を除く平均

            if value > avg_score * 1.5:  # 50%以上悪化
                insight = QuickInsight(
                    insight_id=str(uuid4()),
                    insight_type="performance",
                    title="パフォーマンス劣化",
                    description=f"{metric_name}が平均より{((value / avg_score - 1) * 100):.1f}%悪化: {value}",
                    priority="medium",
                    timestamp=datetime.utcnow().isoformat(),
                    related_sessions=[session_id],
                    data={"metric": metric_name, "value": value, "average": avg_score},
                )
                self.quick_insights.append(insight)

    async def _perform_pattern_analysis(self):
        """パターン分析の実行"""

        # コマンドシーケンスパターンの検出
        await self._detect_command_patterns()

        # エラーパターンの検出
        await self._detect_error_patterns()

        # ユーザー行動パターンの検出
        await self._detect_user_behavior_patterns()

    async def _detect_command_patterns(self):
        """コマンドパターンの検出"""

        # 最近のコマンドから頻出パターンを抽出
        recent_commands = list(self.recent_commands)[-50:]  # 最新50件

        # 連続するコマンドのペアを分析
        command_pairs = []
        for i in range(len(recent_commands) - 1):
            if recent_commands[i]["session_id"] == recent_commands[i + 1]["session_id"]:
                pair = (
                    recent_commands[i]["command"].split()[0]
                    if recent_commands[i]["command"]
                    else "",
                    recent_commands[i + 1]["command"].split()[0]
                    if recent_commands[i + 1]["command"]
                    else "",
                )
                command_pairs.append(pair)

        # 頻出ペアの検出
        pair_counts = defaultdict(int)
        for pair in command_pairs:
            pair_counts[pair] += 1

        for pair, count in pair_counts.items():
            if count >= 3:  # 3回以上現れるパターン
                pattern = MemoryPattern(
                    pattern_id=str(uuid4()),
                    pattern_type="command_sequence",
                    description=f"コマンドペア '{pair[0]} → {pair[1]}' が{count}回実行されました",
                    severity="info",
                    frequency=count,
                    first_seen=datetime.utcnow().isoformat(),
                    last_seen=datetime.utcnow().isoformat(),
                    sessions_affected=["multiple"],
                    suggested_action=f"'{pair[0]} && {pair[1]}'のような複合コマンドを検討してください",
                )
                self.detected_patterns.append(pattern)

    async def _detect_error_patterns(self):
        """エラーパターンの検出"""

        # エラータイプ別の頻度分析
        error_type_counts = defaultdict(int)
        session_error_map = defaultdict(list)

        for error in self.error_events:
            error_type_counts[error["error_type"]] += 1
            session_error_map[error["session_id"]].append(error)

        # 高頻度エラーパターン
        for error_type, count in error_type_counts.items():
            if count >= 5:  # 5回以上のエラー
                affected_sessions = [
                    sid
                    for sid, errors in session_error_map.items()
                    if any(e["error_type"] == error_type for e in errors)
                ]

                pattern = MemoryPattern(
                    pattern_id=str(uuid4()),
                    pattern_type="error_spike",
                    description=f"エラータイプ '{error_type}' が{count}回発生しています",
                    severity="warning" if count < 10 else "error",
                    frequency=count,
                    first_seen=datetime.utcnow().isoformat(),
                    last_seen=datetime.utcnow().isoformat(),
                    sessions_affected=affected_sessions,
                    suggested_action=f"'{error_type}'の根本原因を調査してください",
                )
                self.detected_patterns.append(pattern)

    async def _detect_user_behavior_patterns(self):
        """ユーザー行動パターンの検出"""

        # セッション別のアクティビティレベル分析
        for session_id, stats in self.session_stats.items():
            command_count = stats["command_count"]
            error_count = stats["error_count"]

            # 高エラー率の検出
            if command_count > 10 and error_count / command_count > 0.3:  # 30%以上のエラー率
                pattern = MemoryPattern(
                    pattern_id=str(uuid4()),
                    pattern_type="user_behavior",
                    description=f"セッション {session_id} でエラー率が{(error_count / command_count * 100):.1f}%と高い状態です",
                    severity="warning",
                    frequency=1,
                    first_seen=datetime.utcnow().isoformat(),
                    last_seen=datetime.utcnow().isoformat(),
                    sessions_affected=[session_id],
                    suggested_action="ユーザーサポートやチュートリアルの提供を検討してください",
                )
                self.detected_patterns.append(pattern)

    async def _generate_quick_insights(self):
        """クイックインサイトの生成"""

        # セッション統計からのインサイト
        total_commands = sum(stats["command_count"] for stats in self.session_stats.values())
        total_errors = sum(stats["error_count"] for stats in self.session_stats.values())
        active_sessions = len([s for s in self.session_stats.values() if s["command_count"] > 0])

        if total_commands > 0:
            overall_error_rate = (total_errors / total_commands) * 100

            if overall_error_rate > 15:  # 15%以上のエラー率
                insight = QuickInsight(
                    insight_id=str(uuid4()),
                    insight_type="trend",
                    title="全体エラー率上昇",
                    description=f"全セッションのエラー率が{overall_error_rate:.1f}%と高い状態です",
                    priority="high",
                    timestamp=datetime.utcnow().isoformat(),
                    related_sessions=list(self.session_stats.keys()),
                    data={"error_rate": overall_error_rate, "total_commands": total_commands},
                )
                self.quick_insights.append(insight)

    def _update_user_activity_level(self, session_id: str):
        """ユーザー活動レベルの更新"""

        # 最近の5分間のインタラクション数をカウント
        five_minutes_ago = datetime.utcnow() - timedelta(minutes=5)
        recent_interactions = [
            interaction
            for interaction in self.user_interactions
            if (
                interaction["session_id"] == session_id
                and datetime.fromisoformat(interaction["timestamp"].replace("Z", "+00:00"))
                >= five_minutes_ago
            )
        ]

        interaction_count = len(recent_interactions)

        # 活動レベルの判定
        if interaction_count > 20:
            level = "very_active"
        elif interaction_count > 10:
            level = "active"
        elif interaction_count > 3:
            level = "normal"
        else:
            level = "low"

        self.session_stats[session_id]["user_activity_level"] = level

    async def _cleanup_old_data(self):
        """古いデータのクリーンアップ"""

        # パターンとインサイトの制限
        if len(self.detected_patterns) > 50:
            self.detected_patterns = self.detected_patterns[-25:]  # 最新25件のみ保持

        if len(self.quick_insights) > 100:
            self.quick_insights = self.quick_insights[-50:]  # 最新50件のみ保持

        # 非アクティブなセッション統計のクリーンアップ
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        inactive_sessions = []

        for session_id, stats in self.session_stats.items():
            if stats["last_activity"]:
                try:
                    last_activity = datetime.fromisoformat(
                        stats["last_activity"].replace("Z", "+00:00")
                    )
                    if last_activity < one_hour_ago:
                        inactive_sessions.append(session_id)
                except:
                    inactive_sessions.append(session_id)

        for session_id in inactive_sessions:
            del self.session_stats[session_id]

    def get_current_insights(self) -> List[Dict]:
        """現在のインサイトを取得"""

        # 最新のインサイトを優先度順でソート
        sorted_insights = sorted(
            self.quick_insights[-20:],  # 最新20件
            key=lambda x: {"urgent": 4, "high": 3, "medium": 2, "low": 1}[x.priority],
            reverse=True,
        )

        return [
            {
                "insight_id": insight.insight_id,
                "type": insight.insight_type,
                "title": insight.title,
                "description": insight.description,
                "priority": insight.priority,
                "timestamp": insight.timestamp,
                "sessions": insight.related_sessions,
                "data": insight.data,
            }
            for insight in sorted_insights
        ]

    def get_detected_patterns(self) -> List[Dict]:
        """検出されたパターンを取得"""

        return [
            {
                "pattern_id": pattern.pattern_id,
                "type": pattern.pattern_type,
                "description": pattern.description,
                "severity": pattern.severity,
                "frequency": pattern.frequency,
                "sessions_affected": pattern.sessions_affected,
                "suggested_action": pattern.suggested_action,
            }
            for pattern in self.detected_patterns[-10:]  # 最新10件
        ]

    def get_session_summary(self, session_id: str) -> Dict:
        """特定セッションのサマリを取得"""

        if session_id not in self.session_stats:
            return {"error": "Session not found"}

        stats = self.session_stats[session_id]

        # セッション関連のインサイト
        session_insights = [
            insight
            for insight in self.quick_insights[-50:]
            if session_id in insight.related_sessions
        ]

        # セッション関連のエラー
        session_errors = [error for error in self.error_events if error["session_id"] == session_id]

        return {
            "session_id": session_id,
            "command_count": stats["command_count"],
            "error_count": stats["error_count"],
            "error_rate": (stats["error_count"] / max(stats["command_count"], 1)) * 100,
            "activity_level": stats["user_activity_level"],
            "last_activity": stats["last_activity"],
            "avg_performance": sum(stats["performance_scores"]) / len(stats["performance_scores"])
            if stats["performance_scores"]
            else None,
            "recent_insights": len(session_insights),
            "recent_errors": len(session_errors),
        }

    def get_agent_summary(self) -> Dict:
        """エージェント全体のサマリを取得"""

        total_commands = sum(stats["command_count"] for stats in self.session_stats.values())
        total_errors = sum(stats["error_count"] for stats in self.session_stats.values())
        active_sessions = len(self.session_stats)

        return {
            "agent_id": self.agent_id,
            "active_sessions": active_sessions,
            "total_commands": total_commands,
            "total_errors": total_errors,
            "overall_error_rate": (total_errors / max(total_commands, 1)) * 100,
            "recent_insights": len(self.quick_insights),
            "detected_patterns": len(self.detected_patterns),
            "memory_usage": {
                "commands": len(self.recent_commands),
                "errors": len(self.error_events),
                "performance_metrics": len(self.performance_metrics),
                "user_interactions": len(self.user_interactions),
            },
        }
