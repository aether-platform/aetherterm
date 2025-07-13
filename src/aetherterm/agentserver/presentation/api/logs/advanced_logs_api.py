"""
Advanced Logs API - Log Processing Manager Integration

Provides advanced log processing capabilities using LogProcessingManager.
"""

import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from aetherterm.langchain.config.storage_config import StorageConfig
from aetherterm.logprocessing.log_processing_manager import LogProcessingManager

logger = logging.getLogger(__name__)

# Initialize router
router = APIRouter()

# Global log processing manager
log_processing_manager: Optional[LogProcessingManager] = None


# Pydantic Models
class TerminalRequest(BaseModel):
    terminal_id: str
    log_file_path: str


class SimulateOutputRequest(BaseModel):
    terminal_id: str
    output: str
    level: str = "INFO"
    timestamp: Optional[str] = None


class StressTestRequest(BaseModel):
    test_size: int = 1000


@router.post("/initialize")
async def initialize_log_processing():
    """ログ処理システムを初期化"""
    global log_processing_manager

    try:
        if log_processing_manager is not None:
            return {
                "status": "already_initialized",
                "message": "Log processing already initialized",
            }

        # ストレージ設定を初期化
        storage_config = StorageConfig()

        # LogProcessingManagerを初期化
        log_processing_manager = LogProcessingManager(
            redis_storage=storage_config.redis_storage,
            vector_storage=storage_config.vector_storage,
            sql_storage=storage_config.sql_storage,
        )

        # 初期化を実行
        await log_processing_manager.initialize()

        return {"status": "success", "message": "Log processing system initialized successfully"}

    except Exception as e:
        logger.error(f"Failed to initialize log processing: {e}")
        raise HTTPException(status_code=500, detail=f"Initialization failed: {e!s}")


@router.post("/start-monitoring")
async def start_monitoring(request: TerminalRequest):
    """指定ターミナルのログ監視を開始"""
    global log_processing_manager

    if log_processing_manager is None:
        raise HTTPException(status_code=400, detail="Log processing system not initialized")

    try:
        # ターミナル監視を開始
        await log_processing_manager.start_terminal_monitoring(
            terminal_id=request.terminal_id, log_file_path=request.log_file_path
        )

        return {
            "status": "success",
            "message": f"Started monitoring terminal {request.terminal_id}",
            "terminal_id": request.terminal_id,
            "log_file_path": request.log_file_path,
        }

    except Exception as e:
        logger.error(f"Failed to start monitoring for {request.terminal_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start monitoring: {e!s}")


@router.post("/stop-monitoring/{terminal_id}")
async def stop_monitoring(terminal_id: str):
    """指定ターミナルのログ監視を停止"""
    global log_processing_manager

    if log_processing_manager is None:
        raise HTTPException(status_code=400, detail="Log processing system not initialized")

    try:
        await log_processing_manager.stop_terminal_monitoring(terminal_id)

        return {
            "status": "success",
            "message": f"Stopped monitoring terminal {terminal_id}",
            "terminal_id": terminal_id,
        }

    except Exception as e:
        logger.error(f"Failed to stop monitoring for {terminal_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to stop monitoring: {e!s}")


@router.get("/search")
async def search_logs(
    q: str = Query(description="検索クエリ"),
    limit: int = Query(10, ge=1, le=100, description="結果数制限"),
    terminal_id: Optional[str] = Query(None, description="ターミナルIDフィルター"),
    log_level: Optional[str] = Query(None, description="ログレベルフィルター"),
    data_source: Optional[str] = Query(None, description="データソースフィルター"),
):
    """ログ検索API"""
    global log_processing_manager

    if log_processing_manager is None:
        raise HTTPException(status_code=400, detail="Log processing system not initialized")

    try:
        # モック検索結果（実際の実装では vector_storage.search() を使用）
        mock_results = [
            {
                "id": "log_001",
                "terminal_id": "terminal_123",
                "timestamp": "2025-01-29T10:30:00Z",
                "content": "Application started successfully",
                "error_level": "INFO",
                "similarity_score": 0.95,
                "data_source": "redis",
            },
            {
                "id": "log_002",
                "terminal_id": "terminal_456",
                "timestamp": "2025-01-29T10:35:00Z",
                "content": "Connection timeout error occurred",
                "error_level": "ERROR",
                "similarity_score": 0.88,
                "data_source": "file",
            },
        ]

        # フィルタリング適用
        filtered_results = mock_results

        if terminal_id:
            filtered_results = [
                result for result in filtered_results if result.get("terminal_id") == terminal_id
            ]

        if log_level:
            filtered_results = [
                result for result in filtered_results if result.get("error_level") == log_level
            ]

        # 制限適用
        filtered_results = filtered_results[:limit]

        return {
            "query": q,
            "filters": {
                "terminal_id": terminal_id,
                "log_level": log_level,
                "data_source": data_source,
            },
            "results": filtered_results,
            "total_results": len(filtered_results),
            "search_time": 100,  # Mock value
        }

    except Exception as e:
        logger.error(f"Search failed for query '{q}': {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {e!s}")


@router.post("/simulate-output")
async def simulate_output(request: SimulateOutputRequest):
    """テスト用のターミナル出力をシミュレート"""
    global log_processing_manager

    if log_processing_manager is None:
        raise HTTPException(status_code=400, detail="Log processing system not initialized")

    try:
        # Redisに直接ログエントリを作成
        redis_storage = log_processing_manager.redis_storage

        timestamp = request.timestamp or datetime.utcnow().isoformat()
        log_entry = {
            "terminal_id": request.terminal_id,
            "timestamp": timestamp,
            "raw_output": request.output,
            "size": len(request.output),
            "line_count": request.output.count("\n") + 1,
            "simulated": True,
            "level": request.level,
        }

        # Redisキー生成
        import time

        log_key = f"terminal_logs:{request.terminal_id}:{int(time.time() * 1000)}"

        # Redis保存
        await redis_storage.set_with_ttl(key=log_key, value=json.dumps(log_entry), ttl_seconds=3600)

        # ターミナル別ログリストに追加
        list_key = f"terminal_logs:list:{request.terminal_id}"
        await redis_storage.list_push(list_key, log_key)
        await redis_storage.expire(list_key, 3600)

        return {
            "status": "success",
            "message": f"Simulated output for terminal {request.terminal_id}",
        }

    except Exception as e:
        logger.error(f"Failed to simulate output for {request.terminal_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to simulate output: {e!s}")


@router.post("/test-error-patterns")
async def test_error_patterns():
    """エラーパターンテスト"""
    try:
        # モックエラーパターンを生成
        error_patterns = [
            "FileNotFoundError: [Errno 2] No such file or directory",
            "PermissionError: [Errno 13] Permission denied",
            "ConnectionError: Failed to establish connection",
            "TypeError: 'NoneType' object is not subscriptable",
            "ValueError: invalid literal for int() with base 10",
        ]

        for i, pattern in enumerate(error_patterns):
            await simulate_output(
                SimulateOutputRequest(
                    terminal_id=f"test-terminal-{i % 3}", output=pattern, level="ERROR"
                )
            )

        return {
            "status": "success",
            "patterns_detected": len(error_patterns),
            "message": "Error pattern test completed",
        }

    except Exception as e:
        logger.error(f"Error pattern test failed: {e}")
        raise HTTPException(status_code=500, detail=f"Error pattern test failed: {e!s}")
