"""AetherTerm LangChain統合パッケージ

このパッケージは、AetherTermプロジェクトにLangChainを統合し、
以下の機能を提供します：

- 階層化メモリ管理（短期・中期・長期メモリ）
- 3層ログ要約システム（リアルタイム・セッション・日次）
- 高度な検索・問い合わせ（RAGパイプライン）
"""

from .config.langchain_config import LangChainConfig
from .containers import LangChainContainer

__version__ = "0.1.0"
__all__ = ["LangChainConfig", "LangChainContainer"]
