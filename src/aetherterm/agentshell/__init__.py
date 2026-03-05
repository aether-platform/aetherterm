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

from .config import WrapperConfig
from .containers import WrapperApplication, get_application
from .main import WrapperMain

__all__ = [
    "WrapperApplication",
    "WrapperConfig",
    "WrapperMain",
    "get_application",
]
