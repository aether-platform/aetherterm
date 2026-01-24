"""
オペレーションパターン学習エンジン

過去のコマンド履歴からオペレーションパターンを学習し、
ベクトル化してVectorDBに保存する。
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from aetherterm.langchain.storage.sql_adapter import SQLStorageAdapter
from aetherterm.langchain.storage.vector_adapter import VectorStorageAdapter

from .models import OperationPattern, OperationType

logger = logging.getLogger(__name__)
class OperationPatternLearner:
    """オペレーションパターン学習エンジン"""

    def __init__(self, vector_storage: VectorStorageAdapter, sql_storage: SQLStorageAdapter):
        self.vector_storage = vector_storage
        self.sql_storage = sql_storage
        self.logger = logger

        # パターン認識設定
        self.min_sequence_length = 3
        self.max_sequence_length = 20
        self.min_pattern_frequency = 3
        self.similarity_threshold = 0.8

        # 既知のオペレーションパターン定義
        self.predefined_patterns = {
            OperationType.DEPLOYMENT: {
                "keywords": ["deploy", "build", "release", "production", "staging"],
                "command_patterns": [
                    ["git", "pull"],
                    ["npm", "install"],
                    ["npm", "run", "build"],
                    ["docker", "build"],
                    ["pm2", "restart"],
                ],
            },
            OperationType.DEBUGGING: {
                "keywords": ["debug", "error", "bug", "issue", "problem"],
                "command_patterns": [
                    ["tail", "-f"],
                    ["grep", "ERROR"],
                    ["ps", "aux"],
                    ["netstat", "-tlnp"],
                    ["journalctl", "-f"],
                ],
            },
            OperationType.DEVELOPMENT: {
                "keywords": ["develop", "feature", "code", "implement"],
                "command_patterns": [
                    ["git", "checkout", "-b"],
                    ["npm", "test"],
                    ["git", "add"],
                    ["git", "commit"],
                    ["git", "push"],
                ],
            },
            OperationType.TESTING: {
                "keywords": ["test", "spec", "coverage", "verify"],
                "command_patterns": [
                    ["npm", "test"],
                    ["pytest"],
                    ["jest"],
                    ["coverage", "run"],
                    ["npm", "run", "test"],
                ],
            },
        }

    async def learn_patterns_from_history(self, days: int = 30) -> List[OperationPattern]:
        """
        過去の履歴からオペレーションパターンを学習

        Args:
            days: 学習対象の期間（日数）

        Returns:
            学習されたパターンのリスト
        """
        try:
            self.logger.info(f"Learning patterns from last {days} days...")

            # 過去のコマンド履歴を取得
            command_sessions = await self._get_command_sessions(days)

            # セッションをオペレーションタイプ別に分類
            classified_sessions = await self._classify_sessions(command_sessions)

            # パターンを抽出
            learned_patterns = []
            for operation_type, sessions in classified_sessions.items():
                patterns = await self._extract_patterns_from_sessions(operation_type, sessions)
                learned_patterns.extend(patterns)

            # パターンをベクトル化してVectorDBに保存
            await self._store_patterns(learned_patterns)

            self.logger.info(f"Learned {len(learned_patterns)} operation patterns")
            return learned_patterns

        except Exception as e:
            self.logger.error(f"Failed to learn patterns: {e}")
            return []

    async def _get_command_sessions(self, days: int) -> List[Dict]:
        """過去のコマンドセッションを取得"""
        try:
            # SQLから過去のコマンド履歴を取得
            query = f"""
            SELECT 
                terminal_id,
                session_id,
                timestamp,
                command,
                output_text,
                error_level,
                metadata
            FROM terminal_logs 
            WHERE log_type = 'COMMAND' 
            AND timestamp > datetime('now', '-{days} days')
            ORDER BY terminal_id, timestamp
            """

            results = await self.sql_storage.fetch_all(query, [])

            # セッション別にグループ化
            sessions = {}
            for row in results:
                session_key = f"{row['terminal_id']}_{row.get('session_id', 'default')}"
                if session_key not in sessions:
                    sessions[session_key] = []
                sessions[session_key].append(row)

            return list(sessions.values())

        except Exception as e:
            self.logger.error(f"Failed to get command sessions: {e}")
            return []

    async def _classify_sessions(
        self, sessions: List[List[Dict]]
    ) -> Dict[OperationType, List[List[Dict]]]:
        """セッションをオペレーションタイプ別に分類"""
        classified = {op_type: [] for op_type in OperationType}

        for session in sessions:
            if len(session) < self.min_sequence_length:
                continue

            # セッションのオペレーションタイプを推定
            operation_type = await self._infer_session_operation_type(session)
            classified[operation_type].append(session)

        return classified

    async def _infer_session_operation_type(self, session: List[Dict]) -> OperationType:
        """セッションのオペレーションタイプを推定"""
        try:
            commands = [cmd["command"] for cmd in session]
            command_text = " ".join(commands).lower()

            # キーワードベースの分類
            scores = {}
            for op_type, pattern_def in self.predefined_patterns.items():
                score = 0

                # キーワードスコア
                for keyword in pattern_def["keywords"]:
                    if keyword in command_text:
                        score += 2

                # コマンドパターンスコア
                for pattern in pattern_def["command_patterns"]:
                    for cmd in commands:
                        if all(p in cmd for p in pattern):
                            score += 3

                scores[op_type] = score

            # 最高スコアのオペレーションタイプを返す
            if scores:
                best_type = max(scores.items(), key=lambda x: x[1])
                if best_type[1] > 0:
                    return best_type[0]

            return OperationType.UNKNOWN

        except Exception as e:
            self.logger.error(f"Failed to infer operation type: {e}")
            return OperationType.UNKNOWN

    async def _extract_patterns_from_sessions(
        self, operation_type: OperationType, sessions: List[List[Dict]]
    ) -> List[OperationPattern]:
        """セッションからパターンを抽出"""
        patterns = []

        try:
            # 頻出コマンドシーケンスを抽出
            command_sequences = []
            for session in sessions:
                commands = [cmd["command"] for cmd in session]

                # スライディングウィンドウでシーケンスを抽出
                for i in range(len(commands) - self.min_sequence_length + 1):
                    for length in range(
                        self.min_sequence_length,
                        min(self.max_sequence_length, len(commands) - i) + 1,
                    ):
                        sequence = commands[i : i + length]
                        command_sequences.append(sequence)

            # 頻度分析
            sequence_counts = {}
            for seq in command_sequences:
                seq_key = " → ".join(seq)
                sequence_counts[seq_key] = sequence_counts.get(seq_key, 0) + 1

            # 頻出パターンを抽出
            for seq_key, count in sequence_counts.items():
                if count >= self.min_pattern_frequency:
                    pattern = await self._create_operation_pattern(
                        operation_type, seq_key.split(" → "), count, sessions
                    )
                    if pattern:
                        patterns.append(pattern)

            self.logger.info(f"Extracted {len(patterns)} patterns for {operation_type.value}")
            return patterns

        except Exception as e:
            self.logger.error(f"Failed to extract patterns: {e}")
            return []

    async def _create_operation_pattern(
        self,
        operation_type: OperationType,
        command_sequence: List[str],
        frequency: int,
        sessions: List[List[Dict]],
    ) -> Optional[OperationPattern]:
        """オペレーションパターンを作成"""
        try:
            # 成功/失敗指標を分析
            success_indicators, failure_indicators = await self._analyze_indicators(
                command_sequence, sessions
            )

            # 平均実行時間を計算
            durations = []
            for session in sessions:
                session_commands = [cmd["command"] for cmd in session]
                if self._sequence_in_session(command_sequence, session_commands):
                    session_duration = self._calculate_session_duration(session)
                    if session_duration:
                        durations.append(session_duration)

            avg_duration = sum(durations) / len(durations) if durations else 0
            success_rate = len([d for d in durations if d > 0]) / len(durations) if durations else 0

            # パターンID生成
            pattern_id = f"{operation_type.value}_{hash(' '.join(command_sequence)) % 10000:04d}"

            pattern = OperationPattern(
                pattern_id=pattern_id,
                operation_type=operation_type,
                name=f"{operation_type.value.title()} Pattern",
                description=f"Common {operation_type.value} sequence: {' → '.join(command_sequence[:3])}...",
                command_sequence=command_sequence,
                success_indicators=success_indicators,
                failure_indicators=failure_indicators,
                frequency=frequency,
                success_rate=success_rate,
                average_duration=avg_duration,
                typical_triggers=[],
                dependencies=[],
                environment={},
            )

            return pattern

        except Exception as e:
            self.logger.error(f"Failed to create pattern: {e}")
            return None

    async def _analyze_indicators(
        self, command_sequence: List[str], sessions: List[List[Dict]]
    ) -> Tuple[List[str], List[str]]:
        """成功/失敗指標を分析"""
        success_outputs = []
        failure_outputs = []

        for session in sessions:
            session_commands = [cmd["command"] for cmd in session]
            if self._sequence_in_session(command_sequence, session_commands):
                for cmd in session:
                    if cmd["error_level"] == "ERROR":
                        failure_outputs.append(cmd["output_text"][:100])
                    elif cmd["error_level"] == "INFO":
                        success_outputs.append(cmd["output_text"][:100])

        # 頻出する成功/失敗パターンを抽出
        success_indicators = self._extract_common_phrases(success_outputs)
        failure_indicators = self._extract_common_phrases(failure_outputs)

        return success_indicators, failure_indicators

    def _sequence_in_session(self, sequence: List[str], session_commands: List[str]) -> bool:
        """シーケンスがセッション内に含まれているかチェック"""
        for i in range(len(session_commands) - len(sequence) + 1):
            if session_commands[i : i + len(sequence)] == sequence:
                return True
        return False

    def _calculate_session_duration(self, session: List[Dict]) -> Optional[float]:
        """セッションの実行時間を計算"""
        try:
            if len(session) < 2:
                return None

            start_time = datetime.fromisoformat(session[0]["timestamp"])
            end_time = datetime.fromisoformat(session[-1]["timestamp"])
            duration = (end_time - start_time).total_seconds()

            return duration if duration > 0 else None

        except Exception:
            return None

    def _extract_common_phrases(self, texts: List[str]) -> List[str]:
        """テキストから頻出フレーズを抽出"""
        if not texts:
            return []

        # 簡単な実装：よく出現する単語/フレーズを抽出
        words = []
        for text in texts:
            words.extend(text.lower().split())

        word_counts = {}
        for word in words:
            if len(word) > 3:  # 短い単語は除外
                word_counts[word] = word_counts.get(word, 0) + 1

        # 頻出上位を返す
        common_words = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        return [word for word, count in common_words if count > 1]

    async def _store_patterns(self, patterns: List[OperationPattern]) -> None:
        """パターンをVectorDBに保存"""
        try:
            for pattern in patterns:
                # パターンをテキスト化
                pattern_text = self._pattern_to_text(pattern)

                # ベクトル化
                embedding = await self.vector_storage.generate_embedding(pattern_text)
                pattern.embedding = embedding

                # メタデータ準備
                metadata = {
                    "pattern_id": pattern.pattern_id,
                    "operation_type": pattern.operation_type.value,
                    "frequency": pattern.frequency,
                    "success_rate": pattern.success_rate,
                    "average_duration": pattern.average_duration,
                    "command_count": len(pattern.command_sequence),
                    "created_at": pattern.created_at.isoformat(),
                    "pattern_type": "learned_operation",
                }

                # VectorDBに保存
                await self.vector_storage.store_embedding(
                    content_id=pattern.pattern_id,
                    content=pattern_text,
                    embedding=embedding,
                    metadata=metadata,
                )

            self.logger.info(f"Stored {len(patterns)} patterns in VectorDB")

        except Exception as e:
            self.logger.error(f"Failed to store patterns: {e}")

    def _pattern_to_text(self, pattern: OperationPattern) -> str:
        """パターンをテキスト表現に変換"""
        text_parts = [
            f"Operation: {pattern.operation_type.value}",
            f"Commands: {' → '.join(pattern.command_sequence)}",
            f"Description: {pattern.description}",
        ]

        if pattern.success_indicators:
            text_parts.append(f"Success indicators: {', '.join(pattern.success_indicators)}")

        if pattern.failure_indicators:
            text_parts.append(f"Failure indicators: {', '.join(pattern.failure_indicators)}")

        return " | ".join(text_parts)
