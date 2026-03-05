"""Linuxコマンドアナライザーエージェント

リアルタイムでLinuxコマンドを解析し、安全性チェックと
改善提案を行うエージェントです。
"""

import logging
import re
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from ...common.agent_protocol import (
    AgentCapability,
    AgentStatus,
    InterventionData,
    InterventionType,
    ProgressData,
    TaskData,
)
from .base import AgentInterface

logger = logging.getLogger(__name__)


class CommandRisk(str, Enum):
    """コマンドのリスクレベル"""

    SAFE = "safe"
    CAUTION = "caution"
    DANGEROUS = "dangerous"
    CRITICAL = "critical"


class CommandTaskType(str, Enum):
    """コマンド解析タスクタイプ"""

    ANALYZE = "analyze_command"
    CHECK_SAFETY = "check_safety"
    SUGGEST_IMPROVEMENT = "suggest_improvement"
    STREAM_ANALYSIS = "stream_analysis"
    BATCH_ANALYSIS = "batch_analysis"


class CommandAnalyzerAgent(AgentInterface):
    """Linuxコマンドアナライザーエージェント

    コマンドの解析、安全性チェック、改善提案を行います。
    LangChainのメモリ機能と連携して、コンテキストを考慮した
    判定を実現します。
    """

    def __init__(self, agent_id: str):
        """初期化

        Args:
            agent_id: エージェントID
        """
        super().__init__(agent_id)
        self._status = AgentStatus.IDLE
        self._current_task: Optional[TaskData] = None

        # コマンド履歴
        self._command_history: List[Dict[str, Any]] = []
        self._max_history = 1000

        # パターン定義
        self._patterns = {
            "file_ops": re.compile(r"\b(rm|mv|cp|touch|mkdir|chmod|chown|ln|dd)\b"),
            "network": re.compile(r"\b(curl|wget|nc|ncat|ssh|scp|rsync|iptables|nmap|telnet)\b"),
            "system": re.compile(
                r"\b(systemctl|service|kill|killall|reboot|shutdown|init|mount|umount)\b"
            ),
            "package": re.compile(r"\b(apt|apt-get|yum|dnf|snap|pip|npm|gem|cargo)\b"),
            "dangerous": re.compile(r"\b(rm\s+-rf|dd\s+if=.*of=/dev/[sh]d|mkfs|fdisk|parted)\b"),
            "pipe": re.compile(r"\|"),
            "redirect": re.compile(r"[<>]"),
            "background": re.compile(r"&\s*$"),
            "sudo": re.compile(r"^sudo\s+"),
        }

        # 安全性ルール
        self._safety_rules = {
            "no_root_delete": re.compile(r"rm\s+.*(-rf|-fr).*\s+/\s*($|\s)"),
            "no_format": re.compile(r"(mkfs|format|fdisk.*-l)"),
            "no_dd_system": re.compile(r"dd.*of=/dev/(sda|hda|nvme0n1)\s*($|\s)"),
            "protect_system": re.compile(r"/(etc|bin|sbin|usr|boot|sys|proc)/"),
            "no_fork_bomb": re.compile(r":\(\)\{:\|:&\};:"),
            "no_dev_null_overwrite": re.compile(r">\s*/dev/(null|zero|random)"),
        }

        # コールバック
        self._progress_callback: Optional[Callable[[ProgressData], None]] = None
        self._intervention_callback: Optional[Callable[[InterventionData], Any]] = None

        # ストリーム処理用
        self._stream_active = False
        self._stream_buffer = []

    async def initialize(self) -> bool:
        """エージェントを初期化"""
        try:
            logger.info(f"コマンドアナライザーエージェント {self.agent_id} を初期化中...")

            # 初期パターンのコンパイルテスト
            test_command = "ls -la"
            self._parse_command(test_command)

            self._status = AgentStatus.READY
            logger.info(f"コマンドアナライザーエージェント {self.agent_id} の初期化が完了しました")
            return True

        except Exception as e:
            logger.error(f"コマンドアナライザーエージェントの初期化に失敗しました: {e}")
            self._status = AgentStatus.ERROR
            return False

    async def shutdown(self) -> None:
        """エージェントをシャットダウン"""
        logger.info(f"コマンドアナライザーエージェント {self.agent_id} をシャットダウン中...")

        # ストリーム処理を停止
        self._stream_active = False

        self._status = AgentStatus.IDLE
        logger.info(
            f"コマンドアナライザーエージェント {self.agent_id} のシャットダウンが完了しました"
        )

    def get_capabilities(self) -> List[AgentCapability]:
        """エージェントの能力を取得"""
        return [
            AgentCapability.ANALYSIS,
            AgentCapability.MONITORING,
            AgentCapability.SECURITY_CHECK,
        ]

    def get_status(self) -> AgentStatus:
        """現在のステータスを取得"""
        return self._status

    async def execute_task(self, task: TaskData) -> Dict[str, Any]:
        """タスクを実行

        Args:
            task: 実行するタスク

        Returns:
            Dict[str, Any]: 実行結果
        """
        self._current_task = task
        self._status = AgentStatus.BUSY

        try:
            task_type = CommandTaskType(task.task_type)

            if task_type == CommandTaskType.ANALYZE:
                result = await self._analyze_command(task)
            elif task_type == CommandTaskType.CHECK_SAFETY:
                result = await self._check_safety(task)
            elif task_type == CommandTaskType.SUGGEST_IMPROVEMENT:
                result = await self._suggest_improvement(task)
            elif task_type == CommandTaskType.STREAM_ANALYSIS:
                result = await self._start_stream_analysis(task)
            elif task_type == CommandTaskType.BATCH_ANALYSIS:
                result = await self._batch_analysis(task)
            else:
                raise ValueError(f"未対応のタスクタイプ: {task_type}")

            self._status = AgentStatus.READY
            return result

        except Exception as e:
            logger.error(f"タスク実行中にエラーが発生しました: {e}")
            self._status = AgentStatus.ERROR
            raise

        finally:
            self._current_task = None

    async def cancel_task(self) -> bool:
        """現在のタスクをキャンセル"""
        if not self._current_task:
            return False

        logger.info(f"タスク {self._current_task.task_id} をキャンセル中...")

        # ストリーム処理を停止
        self._stream_active = False

        self._current_task = None
        self._status = AgentStatus.READY
        return True

    def set_progress_callback(self, callback: Callable[[ProgressData], None]) -> None:
        """進捗通知コールバックを設定"""
        self._progress_callback = callback

    def set_intervention_callback(self, callback: Callable[[InterventionData], Any]) -> None:
        """ユーザー介入コールバックを設定"""
        self._intervention_callback = callback

    async def analyze_command_stream(self, command: str) -> Dict[str, Any]:
        """コマンドをストリームで解析（外部から直接呼び出し可能）

        Args:
            command: 解析するコマンド

        Returns:
            Dict[str, Any]: 解析結果
        """
        analysis = self._analyze_single_command(command)
        safety = self._check_command_safety(command, analysis)
        improvement = self._suggest_command_improvement(command, analysis, safety)

        # 履歴に追加
        result = {
            "command": command,
            "analysis": analysis,
            "safety": safety,
            "improvement": improvement,
            "timestamp": datetime.now().isoformat(),
        }

        self._add_to_history(result)

        # 危険なコマンドの場合は介入を要求
        if safety["risk_level"] in [CommandRisk.DANGEROUS, CommandRisk.CRITICAL]:
            if self._intervention_callback:
                intervention = InterventionData(
                    type=InterventionType.APPROVAL,
                    message=f"危険なコマンドが検出されました: {command}\n実行を許可しますか？",
                    context={
                        "command": command,
                        "risk_level": safety["risk_level"],
                        "issues": safety["issues"],
                    },
                )

                response = await self._intervention_callback(intervention)
                result["user_approval"] = response == "approved"

        return result

    # プライベートメソッド

    async def _analyze_command(self, task: TaskData) -> Dict[str, Any]:
        """コマンドを解析"""
        command = task.parameters.get("command", "")
        if not command:
            return {"status": "error", "message": "コマンドが指定されていません"}

        analysis = self._analyze_single_command(command)

        return {
            "status": "success",
            "command": command,
            "analysis": analysis,
            "context": self._get_command_context(command),
        }

    async def _check_safety(self, task: TaskData) -> Dict[str, Any]:
        """安全性をチェック"""
        command = task.parameters.get("command", "")
        analysis = task.parameters.get("analysis", {})

        if not command:
            return {"status": "error", "message": "コマンドが指定されていません"}

        if not analysis:
            analysis = self._analyze_single_command(command)

        safety = self._check_command_safety(command, analysis)

        return {
            "status": "success",
            "command": command,
            "safety": safety,
            "recommendation": self._get_safety_recommendation(safety),
        }

    async def _suggest_improvement(self, task: TaskData) -> Dict[str, Any]:
        """改善提案を生成"""
        command = task.parameters.get("command", "")
        analysis = task.parameters.get("analysis", {})
        safety = task.parameters.get("safety", {})

        if not command:
            return {"status": "error", "message": "コマンドが指定されていません"}

        if not analysis:
            analysis = self._analyze_single_command(command)

        if not safety:
            safety = self._check_command_safety(command, analysis)

        improvement = self._suggest_command_improvement(command, analysis, safety)

        return {"status": "success", "command": command, "improvement": improvement}

    async def _start_stream_analysis(self, task: TaskData) -> Dict[str, Any]:
        """ストリーム解析を開始"""
        self._stream_active = True
        self._stream_buffer = []

        logger.info("コマンドストリーム解析を開始しました")

        return {
            "status": "success",
            "message": "ストリーム解析を開始しました",
            "stream_id": str(uuid4()),
        }

    async def _batch_analysis(self, task: TaskData) -> Dict[str, Any]:
        """バッチ解析を実行"""
        commands = task.parameters.get("commands", [])
        if not commands:
            return {"status": "error", "message": "コマンドが指定されていません"}

        results = []
        for i, command in enumerate(commands):
            await self._notify_progress(
                i / len(commands), f"コマンド {i + 1}/{len(commands)} を解析中..."
            )

            result = await self.analyze_command_stream(command)
            results.append(result)

        await self._notify_progress(1.0, "バッチ解析が完了しました")

        # 統計情報を生成
        stats = self._generate_batch_stats(results)

        return {
            "status": "success",
            "total_commands": len(commands),
            "results": results,
            "statistics": stats,
        }

    def _analyze_single_command(self, command: str) -> Dict[str, Any]:
        """単一コマンドを解析"""
        return {
            "components": self._parse_command(command),
            "categories": self._categorize_command(command),
            "flags": {
                "has_pipe": bool(self._patterns["pipe"].search(command)),
                "has_redirect": bool(self._patterns["redirect"].search(command)),
                "has_background": bool(self._patterns["background"].search(command)),
                "is_sudo": bool(self._patterns["sudo"].match(command)),
            },
            "complexity": self._calculate_complexity(command),
        }

    def _parse_command(self, command: str) -> List[Dict[str, str]]:
        """コマンドを要素に分解"""
        components = []

        # sudo処理
        is_sudo = bool(self._patterns["sudo"].match(command))
        if is_sudo:
            components.append({"type": "privilege", "value": "sudo"})
            command = self._patterns["sudo"].sub("", command).strip()

        # パイプで分割
        if "|" in command:
            pipe_parts = command.split("|")
            for i, part in enumerate(pipe_parts):
                part = part.strip()
                if part:
                    cmd_parts = part.split()
                    if cmd_parts:
                        components.append(
                            {
                                "type": f"pipe_{i}",
                                "command": cmd_parts[0],
                                "args": " ".join(cmd_parts[1:]) if len(cmd_parts) > 1 else "",
                            }
                        )
        else:
            # 単一コマンド
            parts = command.split()
            if parts:
                components.append(
                    {
                        "type": "main",
                        "command": parts[0],
                        "args": " ".join(parts[1:]) if len(parts) > 1 else "",
                    }
                )

        return components

    def _categorize_command(self, command: str) -> List[str]:
        """コマンドをカテゴリ分類"""
        categories = []

        for category, pattern in [
            ("file_operation", self._patterns["file_ops"]),
            ("network", self._patterns["network"]),
            ("system_control", self._patterns["system"]),
            ("package_management", self._patterns["package"]),
        ]:
            if pattern.search(command):
                categories.append(category)

        if self._patterns["dangerous"].search(command):
            categories.append("potentially_dangerous")

        return categories if categories else ["general"]

    def _calculate_complexity(self, command: str) -> int:
        """コマンドの複雑度を計算（0-10）"""
        complexity = 1

        # 基本的な複雑度
        if len(command) > 50:
            complexity += 1
        if len(command) > 100:
            complexity += 1

        # パイプの数
        pipe_count = command.count("|")
        complexity += min(pipe_count * 2, 4)

        # リダイレクト
        if self._patterns["redirect"].search(command):
            complexity += 1

        # sudo
        if self._patterns["sudo"].match(command):
            complexity += 1

        # 危険なパターン
        if self._patterns["dangerous"].search(command):
            complexity += 2

        return min(complexity, 10)

    def _check_command_safety(self, command: str, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """コマンドの安全性をチェック"""
        issues = []
        risk_level = CommandRisk.SAFE

        # 危険なパターンをチェック
        for rule_name, pattern in self._safety_rules.items():
            if pattern.search(command):
                if rule_name == "no_root_delete":
                    issues.append("ルートディレクトリの削除は非常に危険です")
                    risk_level = CommandRisk.CRITICAL
                elif rule_name == "no_format":
                    issues.append("ディスクのフォーマット操作を検出しました")
                    risk_level = CommandRisk.CRITICAL
                elif rule_name == "no_dd_system":
                    issues.append("システムディスクへの直接書き込みは危険です")
                    risk_level = CommandRisk.CRITICAL
                elif rule_name == "protect_system":
                    if any(op in command for op in ["rm", "dd", ">"]):
                        issues.append("システムディレクトリへの破壊的操作を検出しました")
                        risk_level = (
                            CommandRisk.DANGEROUS
                            if risk_level != CommandRisk.CRITICAL
                            else risk_level
                        )
                elif rule_name == "no_fork_bomb":
                    issues.append("フォーク爆弾を検出しました")
                    risk_level = CommandRisk.CRITICAL

        # カテゴリベースのチェック
        if "potentially_dangerous" in analysis.get("categories", []):
            if risk_level == CommandRisk.SAFE:
                risk_level = CommandRisk.CAUTION

        # sudoチェック
        if analysis.get("flags", {}).get("is_sudo") and risk_level == CommandRisk.SAFE:
            risk_level = CommandRisk.CAUTION

        # コンテキストベースのチェック
        context_issues = self._check_context_safety(command)
        issues.extend(context_issues)

        return {
            "risk_level": risk_level,
            "is_safe": risk_level in [CommandRisk.SAFE, CommandRisk.CAUTION],
            "issues": issues,
            "requires_confirmation": risk_level in [CommandRisk.DANGEROUS, CommandRisk.CRITICAL],
        }

    def _suggest_command_improvement(
        self, command: str, analysis: Dict[str, Any], safety: Dict[str, Any]
    ) -> Dict[str, Any]:
        """コマンドの改善提案を生成"""
        suggestions = []
        improved_command = command

        # 危険なrmコマンドの改善
        if "rm -rf" in command and "rm -rfi" not in command:
            improved_command = improved_command.replace("rm -rf", "rm -rfi")
            suggestions.append("対話的確認オプション(-i)を追加しました")

        # sudoコマンドへのコメント追加
        if analysis.get("flags", {}).get("is_sudo") and "#" not in command:
            improved_command = f"{improved_command} # TODO: sudo使用理由を記載"
            suggestions.append("sudo使用理由をコメントで記載することを推奨")

        # バックアップの提案
        if any(op in command for op in ["rm", "mv", "dd"]) and "/home/" in command:
            suggestions.append("重要なファイルの場合は事前にバックアップを作成してください")

        # dry-runオプションの提案
        if "rsync" in command and "--dry-run" not in command:
            suggestions.append("--dry-runオプションで事前確認することを推奨")

        # タイムアウトの提案
        if any(cmd in command for cmd in ["curl", "wget"]) and "--timeout" not in command:
            suggestions.append("--timeoutオプションでタイムアウトを設定することを推奨")

        return {
            "improved_command": improved_command if improved_command != command else None,
            "suggestions": suggestions,
            "has_improvements": len(suggestions) > 0 or improved_command != command,
        }

    def _check_context_safety(self, command: str) -> List[str]:
        """コンテキストベースの安全性チェック"""
        issues = []

        # 最近の履歴をチェック
        if len(self._command_history) > 0:
            last_command = self._command_history[-1]

            # cd後のrm
            if "cd" in last_command.get("command", "") and "rm" in command:
                issues.append("ディレクトリ移動直後の削除操作です。現在位置を確認してください")

            # 連続した危険操作
            if last_command.get("safety", {}).get("risk_level") in [
                CommandRisk.DANGEROUS,
                CommandRisk.CRITICAL,
            ]:
                if any(op in command for op in ["rm", "dd", "mkfs"]):
                    issues.append("連続した危険な操作を検出しました")

        return issues

    def _get_command_context(self, command: str) -> Dict[str, Any]:
        """コマンドの実行コンテキストを取得"""
        # 類似コマンドを検索
        similar_commands = []
        for hist in self._command_history[-20:]:  # 最近20件から検索
            if self._is_similar_command(command, hist.get("command", "")):
                similar_commands.append(hist)

        return {
            "recent_commands": self._command_history[-5:],
            "similar_commands": similar_commands,
            "session_stats": self._get_session_stats(),
        }

    def _is_similar_command(self, cmd1: str, cmd2: str) -> bool:
        """コマンドの類似性を判定"""
        # 簡易的な類似性判定
        parts1 = set(cmd1.split())
        parts2 = set(cmd2.split())

        if not parts1 or not parts2:
            return False

        # 共通部分の割合
        common = parts1.intersection(parts2)
        similarity = len(common) / max(len(parts1), len(parts2))

        return similarity > 0.5

    def _get_safety_recommendation(self, safety: Dict[str, Any]) -> str:
        """安全性に基づく推奨事項を生成"""
        risk_level = safety.get("risk_level", CommandRisk.SAFE)

        if risk_level == CommandRisk.CRITICAL:
            return "このコマンドは非常に危険です。実行前に必ず確認し、可能であれば代替手段を検討してください。"
        if risk_level == CommandRisk.DANGEROUS:
            return "このコマンドは危険な可能性があります。実行前に内容を十分に確認してください。"
        if risk_level == CommandRisk.CAUTION:
            return "このコマンドは注意が必要です。意図した動作か確認してください。"
        return "このコマンドは安全と判定されました。"

    def _add_to_history(self, result: Dict[str, Any]) -> None:
        """履歴に追加"""
        self._command_history.append(result)

        # 履歴サイズ制限
        if len(self._command_history) > self._max_history:
            self._command_history = self._command_history[-self._max_history :]

    def _get_session_stats(self) -> Dict[str, Any]:
        """セッション統計を取得"""
        if not self._command_history:
            return {"total_commands": 0, "risk_distribution": {}, "category_distribution": {}}

        # リスク分布
        risk_counts = {}
        category_counts = {}

        for hist in self._command_history:
            # リスクレベル
            risk = hist.get("safety", {}).get("risk_level", CommandRisk.SAFE)
            risk_counts[risk] = risk_counts.get(risk, 0) + 1

            # カテゴリ
            categories = hist.get("analysis", {}).get("categories", [])
            for cat in categories:
                category_counts[cat] = category_counts.get(cat, 0) + 1

        return {
            "total_commands": len(self._command_history),
            "risk_distribution": risk_counts,
            "category_distribution": category_counts,
        }

    def _generate_batch_stats(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """バッチ処理の統計を生成"""
        total = len(results)
        safe_count = sum(1 for r in results if r.get("safety", {}).get("is_safe", True))

        risk_counts = {}
        for result in results:
            risk = result.get("safety", {}).get("risk_level", CommandRisk.SAFE)
            risk_counts[risk] = risk_counts.get(risk, 0) + 1

        return {
            "total_analyzed": total,
            "safe_commands": safe_count,
            "unsafe_commands": total - safe_count,
            "risk_distribution": risk_counts,
            "safety_rate": safe_count / total if total > 0 else 0,
        }

    async def _notify_progress(self, percentage: float, message: str) -> None:
        """進捗を通知"""
        if self._progress_callback and self._current_task:
            progress_data = ProgressData(
                task_id=self._current_task.task_id,
                percentage=percentage,
                message=message,
                details={},
            )
            self._progress_callback(progress_data)
