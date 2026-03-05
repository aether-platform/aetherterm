"""LogAnalysisConfig - ログ分析設定

環境変数 + デフォルト値による設定管理
"""

import os
from dataclasses import dataclass


@dataclass
class LogAnalysisConfig:
    """ログ分析の設定"""

    # Buffer
    buffer_max_lines: int = 200
    buffer_max_interval_sec: int = 60
    buffer_min_lines: int = 10

    # LLM
    llm_model: str = "claude-sonnet-4-20250514"
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_max_concurrent: int = 3
    llm_timeout_sec: int = 30

    # Analysis
    analysis_mode: str = "both"  # "anomaly" / "summary" / "both"
    auto_block_on_critical: bool = True
    auto_block_on_high: bool = False

    # Compressor
    max_samples_per_pattern: int = 3

    @classmethod
    def from_env(cls) -> "LogAnalysisConfig":
        """環境変数から設定を読み込み"""
        return cls(
            buffer_max_lines=int(os.environ.get("LOG_BUFFER_MAX_LINES", "200")),
            buffer_max_interval_sec=int(os.environ.get("LOG_BUFFER_MAX_INTERVAL_SEC", "60")),
            buffer_min_lines=int(os.environ.get("LOG_BUFFER_MIN_LINES", "10")),
            llm_model=os.environ.get("LOG_LLM_MODEL", "claude-sonnet-4-20250514"),
            llm_api_key=os.environ.get("LOG_LLM_API_KEY", ""),
            llm_base_url=os.environ.get("LOG_LLM_BASE_URL", ""),
            llm_max_concurrent=int(os.environ.get("LOG_LLM_MAX_CONCURRENT", "3")),
            llm_timeout_sec=int(os.environ.get("LOG_LLM_TIMEOUT_SEC", "30")),
            analysis_mode=os.environ.get("LOG_ANALYSIS_MODE", "both"),
            auto_block_on_critical=os.environ.get(
                "LOG_AUTO_BLOCK_ON_CRITICAL", "true"
            ).lower() == "true",
            auto_block_on_high=os.environ.get(
                "LOG_AUTO_BLOCK_ON_HIGH", "false"
            ).lower() == "true",
            max_samples_per_pattern=int(os.environ.get("LOG_MAX_SAMPLES_PER_PATTERN", "3")),
        )
