"""
AIエージェント統合モジュール

このモジュールは、様々なAIエージェント（OpenHands等）との
統合インターフェースを提供します。
"""

from .base import AgentInterface, AgentCapability, AgentTask, AgentResult
from .openhands import OpenHandsAgent
from .langchain_agent import LangChainAgent
from .command_analyzer import CommandAnalyzerAgent, LLMAnalysisConfig
from .manager import AgentManager

__all__ = [
    "AgentInterface",
    "AgentCapability",
    "AgentTask",
    "AgentResult",
    "OpenHandsAgent",
    "LangChainAgent",
    "CommandAnalyzerAgent",
    "LLMAnalysisConfig",
    "AgentManager",
]