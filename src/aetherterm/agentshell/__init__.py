"""Butterfly with AI - ラッパープログラム

このパッケージは、既存のBashターミナルセッションに対して
非侵入型のAI連携機能を提供します。

主な機能:
- ターミナル出力のリアルタイム監視
- セッション管理とオペレーション識別
- AI サービスとの非同期通信
- 既存のBash動作への影響を最小化

新しいアーキテクチャ:
- PTY層: 低レベルターミナル通信
- Domain層: ドメインモデルとビジネスルール
- Service層: ビジネスロジックとアプリケーションサービス
- Controller層: UIとビジネスロジックの橋渡し
"""

__version__ = "0.2.0"
__author__ = "AetherTerm Team"


def __getattr__(name: str):
    """Lazy imports to avoid pulling in heavy dependencies (opentelemetry etc.)
    when only lightweight submodules like pty.pty_chain are needed."""
    if name == "WrapperConfig":
        from .config import WrapperConfig
        return WrapperConfig
    if name in ("WrapperApplication", "get_application"):
        from .containers import WrapperApplication, get_application
        return WrapperApplication if name == "WrapperApplication" else get_application
    if name == "WrapperMain":
        from .main import WrapperMain
        return WrapperMain
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "WrapperApplication",
    "WrapperConfig",
    "WrapperMain",
    "get_application",
]
