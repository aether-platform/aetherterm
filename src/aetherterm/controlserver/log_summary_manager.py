"""
ログサマリ管理システム - ControlServer側

AgentServerから送信される短期記憶データを収集・統合してログサマリを生成
"""

import asyncio
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)
@dataclass
class ShortTermMemory:
    """AgentServerからの短期記憶データ"""

    agent_id: str
    session_id: str
    memory_type: str  # command_execution, user_interaction, error_event, performance_metric
    content: str
    metadata: Dict
    timestamp: str
    severity: str = "info"  # debug, info, warning, error, critical
@dataclass
class LogSummary:
    """生成されたログサマリ"""

    summary_id: str
    period_start: str
    period_end: str
    affected_agents: List[str]
    affected_sessions: List[str]
    event_count: int
    summary_content: str
    key_insights: List[str]
    error_summary: Optional[str]
    performance_summary: Optional[str]
    recommendations: List[str]
    timestamp: str
class LogSummaryManager:
    """ログサマリ管理システム"""

    def __init__(self):
        # 短期記憶ストレージ（AgentServerからの受信データ）
        self.short_term_memories: Dict[str, List[ShortTermMemory]] = {}

        # 生成されたサマリ
        self.log_summaries: List[LogSummary] = []

        # 設定
        self.summary_interval = 300  # 5分間隔でサマリ生成
        self.memory_retention_hours = 24  # 24時間で短期記憶をクリア
        self.max_summaries = 100  # 最大保持サマリ数

        # バックグラウンドタスク
        self.summary_task = None
        self.cleanup_task = None

    async def start(self):
        """ログサマリ管理開始"""
        logger.info("Starting LogSummaryManager")

        # バックグラウンドタスクを開始
        self.summary_task = asyncio.create_task(self._summary_generation_loop())
        self.cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop(self):
        """ログサマリ管理停止"""
        logger.info("Stopping LogSummaryManager")

        if self.summary_task:
            self.summary_task.cancel()
        if self.cleanup_task:
            self.cleanup_task.cancel()

        try:
            await asyncio.gather(self.summary_task, self.cleanup_task, return_exceptions=True)
        except Exception:
            pass

    async def receive_short_term_memory(self, memory_data: Dict):
        """AgentServerからの短期記憶データを受信"""
        try:
            memory = ShortTermMemory(
                agent_id=memory_data["agent_id"],
                session_id=memory_data["session_id"],
                memory_type=memory_data["memory_type"],
                content=memory_data["content"],
                metadata=memory_data.get("metadata", {}),
                timestamp=memory_data.get("timestamp", datetime.utcnow().isoformat()),
                severity=memory_data.get("severity", "info"),
            )

            # エージェント別に短期記憶を保存
            if memory.agent_id not in self.short_term_memories:
                self.short_term_memories[memory.agent_id] = []

            self.short_term_memories[memory.agent_id].append(memory)

            logger.debug(f"Received short-term memory from {memory.agent_id}: {memory.memory_type}")

            # 緊急度が高い場合は即座にサマリ生成を検討
            if memory.severity in ["error", "critical"]:
                await self._generate_emergency_summary(memory)

        except Exception as e:
            logger.error(f"Error processing short-term memory: {e}")

    async def _summary_generation_loop(self):
        """定期的なサマリ生成ループ"""
        while True:
            try:
                await asyncio.sleep(self.summary_interval)
                await self._generate_periodic_summary()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in summary generation loop: {e}")

    async def _cleanup_loop(self):
        """定期的なクリーンアップループ"""
        while True:
            try:
                await asyncio.sleep(3600)  # 1時間間隔
                await self._cleanup_old_data()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")

    async def _generate_periodic_summary(self):
        """定期的なサマリ生成"""
        if not self.short_term_memories:
            return

        current_time = datetime.utcnow()
        period_start = current_time - timedelta(seconds=self.summary_interval)

        # 期間内のメモリを収集
        period_memories = []
        for agent_id, memories in self.short_term_memories.items():
            for memory in memories:
                memory_time = datetime.fromisoformat(memory.timestamp.replace("Z", "+00:00"))
                if memory_time >= period_start:
                    period_memories.append(memory)

        if not period_memories:
            return

        # サマリ生成
        summary = await self._create_summary(period_memories, period_start, current_time)
        self.log_summaries.append(summary)

        # 最大サマリ数を超えた場合は古いものを削除
        if len(self.log_summaries) > self.max_summaries:
            self.log_summaries = self.log_summaries[-self.max_summaries :]

        logger.info(
            f"Generated periodic summary: {summary.summary_id} ({summary.event_count} events)"
        )

    async def _generate_emergency_summary(self, critical_memory: ShortTermMemory):
        """緊急サマリ生成"""
        current_time = datetime.utcnow()

        # 関連する最近のメモリを収集
        related_memories = [critical_memory]

        # 同じセッションやエージェントの関連メモリを追加
        if critical_memory.agent_id in self.short_term_memories:
            for memory in self.short_term_memories[critical_memory.agent_id]:
                memory_time = datetime.fromisoformat(memory.timestamp.replace("Z", "+00:00"))
                if (current_time - memory_time).total_seconds() <= 600:  # 10分以内
                    if memory != critical_memory:
                        related_memories.append(memory)

        # 緊急サマリ生成
        summary = await self._create_summary(
            related_memories, current_time - timedelta(minutes=10), current_time, is_emergency=True
        )

        self.log_summaries.append(summary)

        logger.warning(
            f"Generated emergency summary: {summary.summary_id} (triggered by {critical_memory.severity})"
        )

    async def _create_summary(
        self,
        memories: List[ShortTermMemory],
        period_start: datetime,
        period_end: datetime,
        is_emergency: bool = False,
    ) -> LogSummary:
        """サマリ作成"""

        # 基本統計
        affected_agents = list(set(memory.agent_id for memory in memories))
        affected_sessions = list(set(memory.session_id for memory in memories))

        # イベント分類
        event_types = {}
        error_events = []
        performance_events = []

        for memory in memories:
            event_types[memory.memory_type] = event_types.get(memory.memory_type, 0) + 1

            if memory.severity in ["error", "critical"]:
                error_events.append(memory)
            elif memory.memory_type == "performance_metric":
                performance_events.append(memory)

        # サマリ内容生成
        summary_content = await self._generate_summary_content(memories, event_types, is_emergency)

        # キーインサイト生成
        key_insights = await self._generate_key_insights(memories, event_types)

        # エラーサマリ
        error_summary = await self._generate_error_summary(error_events) if error_events else None

        # パフォーマンスサマリ
        performance_summary = (
            await self._generate_performance_summary(performance_events)
            if performance_events
            else None
        )

        # 推奨事項
        recommendations = await self._generate_recommendations(
            memories, error_events, performance_events
        )

        return LogSummary(
            summary_id=str(uuid4()),
            period_start=period_start.isoformat(),
            period_end=period_end.isoformat(),
            affected_agents=affected_agents,
            affected_sessions=affected_sessions,
            event_count=len(memories),
            summary_content=summary_content,
            key_insights=key_insights,
            error_summary=error_summary,
            performance_summary=performance_summary,
            recommendations=recommendations,
            timestamp=datetime.utcnow().isoformat(),
        )

    async def _generate_summary_content(
        self, memories: List[ShortTermMemory], event_types: Dict[str, int], is_emergency: bool
    ) -> str:
        """サマリ内容生成"""

        lines = []

        if is_emergency:
            lines.append("🚨 **緊急ログサマリ**")
        else:
            lines.append("📊 **定期ログサマリ**")

        lines.append(f"期間: {len(memories)}件のイベントを分析")
        lines.append("")

        # イベントタイプ別の統計
        lines.append("**イベントタイプ別統計:**")
        for event_type, count in sorted(event_types.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"- {event_type}: {count}件")

        lines.append("")

        # 重要なイベントのハイライト
        critical_events = [m for m in memories if m.severity in ["error", "critical"]]
        if critical_events:
            lines.append("**重要なイベント:**")
            for event in critical_events[:5]:  # 最大5件
                lines.append(f"- [{event.severity.upper()}] {event.content[:100]}...")

        return "\n".join(lines)

    async def _generate_key_insights(
        self, memories: List[ShortTermMemory], event_types: Dict[str, int]
    ) -> List[str]:
        """キーインサイト生成"""

        insights = []

        # エラー頻度分析
        error_count = sum(1 for m in memories if m.severity in ["error", "critical"])
        if error_count > 0:
            error_rate = (error_count / len(memories)) * 100
            insights.append(f"エラー率: {error_rate:.1f}% ({error_count}/{len(memories)}件)")

        # 最も活発なエージェント
        agent_activity = {}
        for memory in memories:
            agent_activity[memory.agent_id] = agent_activity.get(memory.agent_id, 0) + 1

        if agent_activity:
            most_active = max(agent_activity.items(), key=lambda x: x[1])
            insights.append(f"最も活発なエージェント: {most_active[0]} ({most_active[1]}件)")

        # 時間帯分析
        hour_distribution = {}
        for memory in memories:
            try:
                hour = datetime.fromisoformat(memory.timestamp.replace("Z", "+00:00")).hour
                hour_distribution[hour] = hour_distribution.get(hour, 0) + 1
            except:
                pass

        if hour_distribution:
            peak_hour = max(hour_distribution.items(), key=lambda x: x[1])
            insights.append(f"ピークアクティビティ時間: {peak_hour[0]}時 ({peak_hour[1]}件)")

        return insights

    async def _generate_error_summary(self, error_events: List[ShortTermMemory]) -> str:
        """エラーサマリ生成"""
        if not error_events:
            return None

        lines = []
        lines.append(f"**エラー分析 ({len(error_events)}件):**")

        # エラータイプ別の集計
        error_types = {}
        for event in error_events:
            # エラー内容からタイプを推定
            content_lower = event.content.lower()
            if "connection" in content_lower:
                error_type = "接続エラー"
            elif "permission" in content_lower or "access" in content_lower:
                error_type = "権限エラー"
            elif "timeout" in content_lower:
                error_type = "タイムアウト"
            elif "not found" in content_lower:
                error_type = "リソース不足"
            else:
                error_type = "その他のエラー"

            error_types[error_type] = error_types.get(error_type, 0) + 1

        for error_type, count in sorted(error_types.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"- {error_type}: {count}件")

        return "\n".join(lines)

    async def _generate_performance_summary(self, performance_events: List[ShortTermMemory]) -> str:
        """パフォーマンスサマリ生成"""
        if not performance_events:
            return None

        lines = []
        lines.append(f"**パフォーマンス分析 ({len(performance_events)}件):**")

        # メトリクス分析
        response_times = []
        memory_usage = []

        for event in performance_events:
            metadata = event.metadata
            if "response_time" in metadata:
                try:
                    response_times.append(float(metadata["response_time"]))
                except:
                    pass
            if "memory_usage" in metadata:
                try:
                    memory_usage.append(float(metadata["memory_usage"]))
                except:
                    pass

        if response_times:
            avg_response = sum(response_times) / len(response_times)
            max_response = max(response_times)
            lines.append(f"- 平均レスポンス時間: {avg_response:.2f}ms")
            lines.append(f"- 最大レスポンス時間: {max_response:.2f}ms")

        if memory_usage:
            avg_memory = sum(memory_usage) / len(memory_usage)
            max_memory = max(memory_usage)
            lines.append(f"- 平均メモリ使用量: {avg_memory:.1f}MB")
            lines.append(f"- 最大メモリ使用量: {max_memory:.1f}MB")

        return "\n".join(lines)

    async def _generate_recommendations(
        self,
        memories: List[ShortTermMemory],
        error_events: List[ShortTermMemory],
        performance_events: List[ShortTermMemory],
    ) -> List[str]:
        """推奨事項生成"""

        recommendations = []

        # エラー率が高い場合
        if error_events and len(error_events) / len(memories) > 0.1:
            recommendations.append(
                "エラー率が10%を超えています。システムの安定性を確認してください。"
            )

        # パフォーマンス問題
        slow_events = [e for e in performance_events if e.metadata.get("response_time", 0) > 1000]
        if slow_events:
            recommendations.append(
                "レスポンス時間が1秒を超えるイベントが検出されました。パフォーマンス最適化を検討してください。"
            )

        # 高頻度エージェント
        agent_counts = {}
        for memory in memories:
            agent_counts[memory.agent_id] = agent_counts.get(memory.agent_id, 0) + 1

        if agent_counts:
            max_count = max(agent_counts.values())
            if max_count > len(memories) * 0.5:
                recommendations.append(
                    "特定のエージェントに負荷が集中しています。負荷分散を検討してください。"
                )

        return recommendations

    async def _cleanup_old_data(self):
        """古いデータのクリーンアップ"""
        current_time = datetime.utcnow()
        cutoff_time = current_time - timedelta(hours=self.memory_retention_hours)

        # 短期記憶のクリーンアップ
        cleaned_count = 0
        for agent_id in list(self.short_term_memories.keys()):
            memories = self.short_term_memories[agent_id]

            # 期限切れのメモリを削除
            filtered_memories = []
            for memory in memories:
                try:
                    memory_time = datetime.fromisoformat(memory.timestamp.replace("Z", "+00:00"))
                    if memory_time >= cutoff_time:
                        filtered_memories.append(memory)
                    else:
                        cleaned_count += 1
                except:
                    # パース失敗したものは削除
                    cleaned_count += 1

            if filtered_memories:
                self.short_term_memories[agent_id] = filtered_memories
            else:
                del self.short_term_memories[agent_id]

        if cleaned_count > 0:
            logger.info(f"Cleaned up {cleaned_count} old short-term memories")

    def get_recent_summaries(self, limit: int = 10) -> List[Dict]:
        """最近のサマリを取得"""
        recent_summaries = self.log_summaries[-limit:] if self.log_summaries else []
        return [asdict(summary) for summary in reversed(recent_summaries)]

    def get_memory_statistics(self) -> Dict:
        """メモリ統計を取得"""
        total_memories = sum(len(memories) for memories in self.short_term_memories.values())

        return {
            "total_agents": len(self.short_term_memories),
            "total_memories": total_memories,
            "total_summaries": len(self.log_summaries),
            "memory_retention_hours": self.memory_retention_hours,
            "summary_interval_seconds": self.summary_interval,
        }
