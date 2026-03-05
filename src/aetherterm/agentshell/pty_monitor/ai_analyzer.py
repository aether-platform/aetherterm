"""
AI Analyzer

ログデータを解析して危険度を判定するAI解析機能。
ドメインサービス (CommandThreatAnalyzer) を活用しつつ、
より詳細な正規表現パターンとWebSocket通信によるAIサーバー連携を提供します。
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

import websockets

from ..domain.services.command_threat_analyzer import CommandThreatAnalyzer

logger = logging.getLogger(__name__)


class ThreatLevel(Enum):
    """脅威レベル"""

    SAFE = "safe"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class AnalysisResult:
    """解析結果"""

    threat_level: ThreatLevel
    confidence: float
    detected_keywords: List[str]
    message: str
    should_block: bool


class AIAnalyzer:
    """AI解析クラス

    ドメインサービス CommandThreatAnalyzer と連携し、
    正規表現パターンマッチングとAIサーバー解析を統合します。
    """

    def __init__(
        self,
        ai_server_url: str = "ws://localhost:8765",
        threat_analyzer: Optional[CommandThreatAnalyzer] = None,
    ):
        """
        初期化

        Args:
            ai_server_url: AIサーバーのWebSocket URL
            threat_analyzer: ドメイン脅威解析サービス（省略時は内部で生成）
        """
        self.ai_server_url = ai_server_url
        self.websocket = None
        self.connected = False
        self._threat_analyzer = threat_analyzer or CommandThreatAnalyzer()

        # 正規表現ベースの詳細パターン（ドメインサービスの文字列マッチを補完）
        self.critical_patterns = {
            # システム破壊系
            r"rm\s+-rf\s+/": "システム全体削除の危険性",
            r"dd\s+if=/dev/zero": "ディスク破壊の危険性",
            r"mkfs\.\w+": "ファイルシステム破壊の危険性",
            r"fdisk.*delete": "パーティション削除の危険性",
            # セキュリティ系
            r"chmod\s+777\s+/": "ルートディレクトリの権限変更",
            r"chown\s+.*:\s*/": "ルートディレクトリの所有者変更",
            r"sudo\s+su\s+-": "root権限昇格",
            r"passwd\s+root": "root パスワード変更",
            # ネットワーク系
            r"nc\s+.*-e\s+/bin/sh": "リバースシェル接続",
            r"wget.*\|\s*sh": "不明スクリプトの実行",
            r"curl.*\|\s*bash": "不明スクリプトの実行",
            # データ漏洩系
            r"scp\s+.*@.*:": "外部へのファイル転送",
            r"rsync.*@.*:": "外部へのデータ同期",
            r"tar.*\|\s*ssh": "データのリモート転送",
        }

        self.high_patterns = {
            r"sudo\s+.*": "管理者権限での実行",
            r"systemctl\s+(stop|disable)": "システムサービス停止",
            r"iptables\s+-F": "ファイアウォール設定削除",
            r"crontab\s+-r": "cron設定削除",
            r"history\s+-c": "コマンド履歴削除",
        }

        self.medium_patterns = {
            r"ps\s+aux\s*\|\s*grep": "プロセス監視",
            r"netstat\s+-.*": "ネットワーク状態確認",
            r"lsof\s+-i": "ネットワーク接続確認",
            r"find\s+/.*-name": "ファイル検索",
        }

    async def connect_to_ai_server(self) -> bool:
        """
        AIサーバーに接続

        Returns:
            接続成功の場合True
        """
        try:
            self.websocket = await websockets.connect(self.ai_server_url)
            self.connected = True
            logger.info(f"Connected to AI server: {self.ai_server_url}")
            return True
        except Exception as e:
            logger.warning(f"Failed to connect to AI server: {e}")
            self.connected = False
            return False

    async def disconnect_from_ai_server(self):
        """AIサーバーから切断"""
        if self.websocket:
            try:
                await self.websocket.close()
            except Exception as e:
                logger.error(f"Error disconnecting from AI server: {e}")
            finally:
                self.websocket = None
                self.connected = False

    async def analyze_log_line(self, log_line: str) -> AnalysisResult:
        """
        ログ行を解析

        Args:
            log_line: 解析するログ行

        Returns:
            解析結果
        """
        # まず簡易キーワード解析を実行
        local_result = self._analyze_with_keywords(log_line)

        # AIサーバーが利用可能な場合はAI解析も実行
        if self.connected and self.websocket:
            try:
                ai_result = await self._analyze_with_ai_server(log_line)
                # AI解析結果と簡易解析結果を統合
                return self._merge_results(local_result, ai_result)
            except Exception as e:
                logger.error(f"AI server analysis failed: {e}")

        return local_result

    def _analyze_with_keywords(self, log_line: str) -> AnalysisResult:
        """
        キーワードベースの解析。
        ドメインサービスの文字列マッチと正規表現パターンを組み合わせます。

        Args:
            log_line: 解析するログ行

        Returns:
            解析結果
        """
        detected_keywords = []
        threat_level = ThreatLevel.SAFE
        message = "安全なログです"

        # 1. ドメインサービスによる文字列マッチ解析
        domain_result = self._threat_analyzer.analyze(log_line)
        if domain_result.detected_keywords:
            detected_keywords.extend(domain_result.detected_keywords)
            threat_level = ThreatLevel(domain_result.threat_level.value)
            message = domain_result.message

        # 2. 正規表現パターンによる詳細解析（ドメインサービスで検出できなかった場合）
        if threat_level == ThreatLevel.SAFE:
            # CRITICAL レベルチェック
            for pattern, description in self.critical_patterns.items():
                if re.search(pattern, log_line, re.IGNORECASE):
                    detected_keywords.append(f"{pattern}: {description}")
                    threat_level = ThreatLevel.CRITICAL
                    message = f"CRITICAL: {description}"
                    break

        if threat_level == ThreatLevel.SAFE:
            # HIGH レベルチェック
            for pattern, description in self.high_patterns.items():
                if re.search(pattern, log_line, re.IGNORECASE):
                    detected_keywords.append(f"{pattern}: {description}")
                    threat_level = ThreatLevel.HIGH
                    message = f"HIGH: {description}"
                    break

        if threat_level == ThreatLevel.SAFE:
            # MEDIUM レベルチェック
            for pattern, description in self.medium_patterns.items():
                if re.search(pattern, log_line, re.IGNORECASE):
                    detected_keywords.append(f"{pattern}: {description}")
                    threat_level = ThreatLevel.MEDIUM
                    message = f"MEDIUM: {description}"
                    break

        # 信頼度計算
        confidence = (
            0.9
            if threat_level == ThreatLevel.CRITICAL
            else 0.8
            if threat_level == ThreatLevel.HIGH
            else 0.6
            if threat_level == ThreatLevel.MEDIUM
            else 0.1
        )

        # ブロック判定（CRITICAL または HIGH の場合）
        should_block = threat_level in [ThreatLevel.CRITICAL, ThreatLevel.HIGH]

        return AnalysisResult(
            threat_level=threat_level,
            confidence=confidence,
            detected_keywords=detected_keywords,
            message=message,
            should_block=should_block,
        )

    async def _analyze_with_ai_server(self, log_line: str) -> AnalysisResult:
        """
        AIサーバーによる解析

        Args:
            log_line: 解析するログ行

        Returns:
            解析結果
        """
        if not self.websocket:
            raise Exception("Not connected to AI server")

        # AIサーバーにリクエスト送信
        request = {
            "action": "analyze",
            "data": {"log_line": log_line, "timestamp": asyncio.get_event_loop().time()},
        }

        await self.websocket.send(json.dumps(request))

        # レスポンス受信
        response_text = await self.websocket.recv()
        response = json.loads(response_text)

        if response.get("status") != "success":
            raise Exception(f"AI server error: {response.get('error', 'Unknown error')}")

        data = response.get("data", {})

        return AnalysisResult(
            threat_level=ThreatLevel(data.get("threat_level", "safe")),
            confidence=data.get("confidence", 0.5),
            detected_keywords=data.get("detected_keywords", []),
            message=data.get("message", "AI analysis completed"),
            should_block=data.get("should_block", False),
        )

    def _merge_results(
        self, local_result: AnalysisResult, ai_result: AnalysisResult
    ) -> AnalysisResult:
        """
        簡易解析結果とAI解析結果を統合

        Args:
            local_result: 簡易解析結果
            ai_result: AI解析結果

        Returns:
            統合された解析結果
        """
        # より高い脅威レベルを採用
        threat_levels = [
            ThreatLevel.SAFE,
            ThreatLevel.LOW,
            ThreatLevel.MEDIUM,
            ThreatLevel.HIGH,
            ThreatLevel.CRITICAL,
        ]
        local_index = threat_levels.index(local_result.threat_level)
        ai_index = threat_levels.index(ai_result.threat_level)

        final_threat_level = threat_levels[max(local_index, ai_index)]

        # 信頼度は平均値
        final_confidence = (local_result.confidence + ai_result.confidence) / 2

        # キーワードは統合
        final_keywords = local_result.detected_keywords + ai_result.detected_keywords

        # メッセージは高い脅威レベルのものを採用
        final_message = local_result.message if local_index >= ai_index else ai_result.message

        # ブロック判定はいずれかがTrueならTrue
        final_should_block = local_result.should_block or ai_result.should_block

        return AnalysisResult(
            threat_level=final_threat_level,
            confidence=final_confidence,
            detected_keywords=final_keywords,
            message=final_message,
            should_block=final_should_block,
        )

    async def __aenter__(self):
        """非同期コンテキストマネージャー対応"""
        await self.connect_to_ai_server()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """非同期コンテキストマネージャー対応"""
        await self.disconnect_from_ai_server()
