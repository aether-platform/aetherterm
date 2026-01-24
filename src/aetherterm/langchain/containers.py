"""
LangChain統合用DIコンテナ
"""

import asyncio
import logging

from dependency_injector import containers, providers

from .config.langchain_config import LangChainConfig
from .config.memory_config import MemoryConfig
from .config.storage_config import StorageConfig
from .memory.conversation_memory import ConversationMemoryManager
from .memory.hierarchical_memory import HierarchicalMemoryManager
from .memory.session_memory import SessionMemoryManager
from .storage.redis_adapter import RedisStorageAdapter
from .storage.sql_adapter import SQLStorageAdapter
from .storage.vector_adapter import VectorStoreAdapter

logger = logging.getLogger(__name__)
class LangChainContainer(containers.DeclarativeContainer):
    """LangChain統合用DIコンテナ"""

    # 設定プロバイダー
    langchain_config = providers.Singleton(LangChainConfig.from_env)
    memory_config = providers.Singleton(MemoryConfig)
    storage_config = providers.Singleton(StorageConfig)

    # ストレージアダプタープロバイダー
    redis_storage_adapter = providers.Singleton(RedisStorageAdapter, config=storage_config)

    sql_storage_adapter = providers.Singleton(SQLStorageAdapter, config=storage_config)

    vector_storage_adapter = providers.Singleton(VectorStoreAdapter, config=storage_config)

    # 階層化メモリマネージャープロバイダー
    hierarchical_memory_manager = providers.Singleton(
        HierarchicalMemoryManager,
        langchain_config=langchain_config,
        memory_config=memory_config,
        redis_storage=redis_storage_adapter,
        sql_storage=sql_storage_adapter,
        vector_storage=vector_storage_adapter,
    )

    # 会話メモリマネージャープロバイダー
    conversation_memory_manager = providers.Singleton(
        ConversationMemoryManager,
        langchain_config=langchain_config,
        memory_config=memory_config,
        hierarchical_memory_manager=hierarchical_memory_manager,
    )

    # セッションメモリマネージャープロバイダー
    session_memory_manager = providers.Singleton(
        SessionMemoryManager,
        langchain_config=langchain_config,
        memory_config=memory_config,
        hierarchical_memory_manager=hierarchical_memory_manager,
    )

    # コンテナの初期化とシャットダウンフック
    @classmethod
    def init_resources(cls):
        """コンテナリソースの初期化"""
        container = cls()

        # ここで必要な初期化処理を呼び出す
        # 例: hierarchical_memory_managerのinitialize
        async def _init():
            await container.hierarchical_memory_manager().initialize()
            logger.info("LangChainContainerリソースが初期化されました。")

        # 非同期処理を同期的に実行するためのハック
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        loop.run_until_complete(_init())

    @classmethod
    def shutdown_resources(cls):
        """コンテナリソースのシャットダウン"""
        container = cls()

        # ここで必要なシャットダウン処理を呼び出す
        # 例: hierarchical_memory_managerのshutdown
        async def _shutdown():
            await container.hierarchical_memory_manager().shutdown()
            logger.info("LangChainContainerリソースがシャットダウンされました。")

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        loop.run_until_complete(_shutdown())

    def __enter__(self):
        """コンテキストマネージャーの開始"""
        self.init_resources()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """コンテキストマネージャーの終了"""
        self.shutdown_resources()
