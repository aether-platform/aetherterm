"""
Dependency Injection Container

AetherTermのコンポーネント間の依存関係を管理し、
コンパクトで保守可能なアーキテクチャを提供します。
"""

from dependency_injector import containers, providers
from dependency_injector.wiring import Provide, inject

from ..common.interfaces import ILogProcessor
from ..langchain.config.storage_config import StorageConfig
from ..logprocessing.log_processing_manager import LogProcessingManager


class ApplicationContainer(containers.DeclarativeContainer):
    """アプリケーション依存関係コンテナ"""

    # Configuration
    config = providers.Configuration()

    # Default configuration values
    config.motd.from_value("Welcome to AetherTerm")
    config.login.from_value(False)
    config.pam_profile.from_value("login")
    config.uri_root_path.from_value("")

    # Storage configuration
    storage_config = providers.Singleton(StorageConfig)

    # Core Services - interface-based dependency injection
    log_processing_manager = providers.Singleton(
        LogProcessingManager,
        storage_config=storage_config,
    )

    # インターフェースベースの依存関係
    log_processor = providers.Singleton(
        providers.Object(log_processing_manager.provided),
    )


class DIContainer:
    """シンプルなDIコンテナヘルパー"""

    _container = ApplicationContainer()

    @classmethod
    def configure(cls, **config_overrides):
        """設定をオーバーライド"""
        cls._container.config.from_dict(config_overrides)

    @classmethod
    def get_container(cls) -> ApplicationContainer:
        """コンテナインスタンスを取得"""
        return cls._container

    @classmethod
    @inject
    def get_log_processing_manager(
        cls,
        log_manager: LogProcessingManager = Provide[ApplicationContainer.log_processing_manager],
    ) -> LogProcessingManager:
        """LogProcessingManagerを取得"""
        return log_manager

    @classmethod
    @inject
    def get_log_processor(
        cls, processor: ILogProcessor = Provide[ApplicationContainer.log_processor]
    ) -> ILogProcessor:
        """LogProcessorインターフェースを取得"""
        return processor

    @classmethod
    def wire_modules(cls, modules: list):
        """モジュールにDIを適用"""
        cls._container.wire(modules=modules)


# グローバルコンテナインスタンス
container = DIContainer()
