"""
オペレーションコンテキスト推定システム

VectorDBとSQLを活用して、ターミナルでの作業パターンを学習し、
現在実行中のオペレーションを推定するシステム。
"""

from .models import (
    OperationType,
    OperationStage,
    OperationContext,
    OperationPattern,
    ContextInferenceResult,
    TeamOperationContext
)

from .pattern_learner import OperationPatternLearner
from .inference_engine import OperationContextInferenceEngine
from .api import router as context_api_router, initialize_context_inference

__all__ = [
    # Models
    "OperationType",
    "OperationStage", 
    "OperationContext",
    "OperationPattern",
    "ContextInferenceResult",
    "TeamOperationContext",
    
    # Core Classes
    "OperationPatternLearner",
    "OperationContextInferenceEngine",
    
    # API
    "context_api_router",
    "initialize_context_inference"
]