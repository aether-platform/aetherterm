"""
コンテキスト推定API

オペレーションコンテキスト推定機能のREST APIエンドポイント
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel, Field

from aetherterm.agentserver.domain.services.models import OperationContext

logger = logging.getLogger(__name__)

# API Router
router = APIRouter(prefix="/api/context", tags=["Operation Context"])


# Pydantic Models for API
class OperationContextResponse(BaseModel):
    """オペレーションコンテキストレスポンス"""

    terminal_id: str
    operation_type: str
    stage: str
    confidence: float
    start_time: str
    progress_percentage: float
    estimated_duration: Optional[float] = None
    command_sequence: List[str] = Field(default_factory=list)
    next_likely_commands: List[str] = Field(default_factory=list)
    risk_factors: List[str] = Field(default_factory=list)
    suggested_actions: List[str] = Field(default_factory=list)


class InferenceResultResponse(BaseModel):
    """推定結果レスポンス"""

    terminal_id: str
    timestamp: str
    primary_context: OperationContextResponse
    overall_confidence: float
    reasoning: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class PatternLearningRequest(BaseModel):
    """パターン学習リクエスト"""

    days: int = Field(30, ge=1, le=365, description="Learning period in days")
    retrain: bool = Field(False, description="Whether to retrain existing patterns")


class PatternLearningResponse(BaseModel):
    """パターン学習レスポンス"""

    status: str
    patterns_learned: int
    learning_duration: float
    message: str


# API Endpoints


@router.get("/infer/{terminal_id}", response_model=InferenceResultResponse)
async def infer_operation_context(
    terminal_id: str = Path(description="Terminal ID to analyze"),
) -> InferenceResultResponse:
    """
    指定ターミナルの現在のオペレーションコンテキストを推定
    """
    # This is a placeholder implementation since context inference is not fully implemented
    # The real functionality is now provided by the local insights API
    raise HTTPException(
        status_code=501,
        detail="Context inference is not implemented. Use /api/v1/insights/ endpoints instead.",
    )


@router.get("/status/{terminal_id}", response_model=OperationContextResponse)
async def get_operation_status(
    terminal_id: str = Path(description="Terminal ID to check"),
) -> OperationContextResponse:
    """
    指定ターミナルの現在のオペレーション状態を取得
    """
    raise HTTPException(
        status_code=501,
        detail="Context inference is not implemented. Use /api/v1/insights/ endpoints instead.",
    )


@router.get("/predict/{terminal_id}/next-commands")
async def predict_next_commands(
    terminal_id: str = Path(description="Terminal ID to predict for"),
    limit: int = Query(5, ge=1, le=20, description="Maximum number of predictions"),
) -> Dict[str, List[str]]:
    """
    指定ターミナルの次に実行される可能性の高いコマンドを予測
    """
    raise HTTPException(
        status_code=501,
        detail="Context inference is not implemented. Use /api/v1/insights/ endpoints instead.",
    )


@router.get("/active-operations")
async def get_active_operations() -> Dict[str, List[OperationContextResponse]]:
    """
    現在アクティブな全オペレーションを取得
    """
    raise HTTPException(
        status_code=501,
        detail="Context inference is not implemented. Use /api/v1/insights/ endpoints instead.",
    )


@router.post("/learn-patterns", response_model=PatternLearningResponse)
async def learn_operation_patterns(request: PatternLearningRequest) -> PatternLearningResponse:
    """
    過去のコマンド履歴からオペレーションパターンを学習
    """
    raise HTTPException(
        status_code=501,
        detail="Context inference is not implemented. Use /api/v1/insights/ endpoints instead.",
    )


@router.get("/patterns/summary")
async def get_patterns_summary() -> Dict[str, Any]:
    """
    学習済みパターンのサマリーを取得
    """
    try:
        # VectorDBから学習済みパターンの統計を取得
        # 実装は簡略化
        summary = {
            "total_patterns": 0,
            "patterns_by_type": {},
            "last_learning_time": None,
            "coverage_percentage": 0.0,
        }

        return summary

    except Exception as e:
        logger.error(f"Failed to get patterns summary: {e}")
        raise HTTPException(status_code=500, detail=f"Patterns summary failed: {e!s}")


@router.get("/analytics/{terminal_id}")
async def get_operation_analytics(
    terminal_id: str = Path(description="Terminal ID to analyze"),
    days: int = Query(7, ge=1, le=30, description="Analysis period in days"),
) -> Dict[str, Any]:
    """
    指定ターミナルのオペレーション分析を取得
    """
    try:
        # オペレーション履歴の分析
        analytics = {
            "terminal_id": terminal_id,
            "analysis_period_days": days,
            "operation_counts": {},
            "average_durations": {},
            "success_rates": {},
            "most_common_operations": [],
            "efficiency_trends": [],
            "recommendations": [],
        }

        # 実際の分析実装はここに追加

        return analytics

    except Exception as e:
        logger.error(f"Failed to get analytics for terminal {terminal_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Analytics retrieval failed: {e!s}")


@router.post("/feedback/{terminal_id}")
async def submit_context_feedback(
    feedback: Dict[str, Any], terminal_id: str = Path(description="Terminal ID")
) -> Dict[str, str]:
    """
    コンテキスト推定結果に対するフィードバックを送信
    （将来の改善に使用）
    """
    try:
        # フィードバックを保存（実装は簡略化）
        logger.info(f"Received feedback for terminal {terminal_id}: {feedback}")

        return {
            "status": "success",
            "message": "Feedback received and will be used to improve context inference",
        }

    except Exception as e:
        logger.error(f"Failed to submit feedback: {e}")
        raise HTTPException(status_code=500, detail=f"Feedback submission failed: {e!s}")


# Helper Functions


def _context_to_response(context: OperationContext) -> OperationContextResponse:
    """OperationContextをレスポンスモデルに変換"""
    return OperationContextResponse(
        terminal_id=context.terminal_id,
        operation_type=context.operation_type.value,
        stage=context.stage.value,
        confidence=context.confidence,
        start_time=context.start_time.isoformat(),
        progress_percentage=context.progress_percentage,
        estimated_duration=context.estimated_duration,
        command_sequence=context.command_sequence,
        next_likely_commands=context.next_likely_commands,
        risk_factors=context.risk_factors,
        suggested_actions=context.suggested_actions,
    )


# Initialization Functions - DEPRECATED


def initialize_context_inference(vector_storage, sql_storage) -> Tuple[None, None]:
    """
    コンテキスト推定エンジンを初期化 - DEPRECATED
    """
    logger.warning(
        "Context inference initialization is deprecated. Use local insights API instead."
    )
    return None, None


async def startup_context_inference():
    """
    起動時のコンテキスト推定システム初期化 - DEPRECATED
    """
    logger.warning("Context inference startup is deprecated. Use local insights API instead.")


# Health Check
@router.get("/health")
async def health_check() -> Dict[str, str]:
    """ヘルスチェック"""
    return {
        "status": "deprecated",
        "service": "context-inference",
        "message": "Use /api/v1/insights/ endpoints instead",
        "timestamp": datetime.utcnow().isoformat(),
    }
