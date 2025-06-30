"""
共通インターフェース

パッケージ間の循環参照を避けるための共通インターフェース定義
"""

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional


class ITerminalController(ABC):
    """ターミナルコントローラのインターフェース"""

    @abstractmethod
    async def start_monitoring(self) -> bool:
        """監視開始"""
        pass

    @abstractmethod
    async def stop_monitoring(self) -> bool:
        """監視停止"""
        pass

    @abstractmethod
    async def get_output(self) -> str:
        """出力取得"""
        pass

    @abstractmethod
    def add_output_callback(self, callback: Callable[[str], None]) -> None:
        """出力コールバック追加"""
        pass


class ILogProcessor(ABC):
    """ログプロセッサのインターフェース"""

    @abstractmethod
    async def process_log_entry(self, entry: Dict[str, Any]) -> None:
        """ログエントリの処理"""
        pass

    @abstractmethod
    async def search_logs(self, query: str, **kwargs) -> List[Dict[str, Any]]:
        """ログ検索"""
        pass


class IAgentManager(ABC):
    """エージェント管理のインターフェース"""

    @abstractmethod
    async def start_agent(self, agent_id: str) -> bool:
        """エージェント開始"""
        pass

    @abstractmethod
    async def stop_agent(self, agent_id: str) -> bool:
        """エージェント停止"""
        pass

    @abstractmethod
    async def send_message(self, agent_id: str, message: Dict[str, Any]) -> Any:
        """メッセージ送信"""
        pass
