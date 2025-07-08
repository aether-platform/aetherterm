"""
ローカルインサイトAPI

短期記憶データを使ったリアルタイム分析結果を提供
AgentServer内で完結する軽量な分析機能
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# APIルーター
router = APIRouter(prefix="/api/v1/insights", tags=["local-insights"])


class SessionInsightRequest(BaseModel):
    """セッションインサイト要求"""

    session_id: str
    include_recommendations: bool = True


class InsightResponse(BaseModel):
    """インサイト応答"""

    insight_id: str
    type: str
    title: str
    description: str
    priority: str
    timestamp: str
    related_sessions: List[str]
    data: Dict


@router.get("/current")
async def get_current_insights(
    limit: int = Query(10, ge=1, le=50),
    priority: Optional[str] = Query(None, regex="^(low|medium|high|urgent)$"),
    insight_type: Optional[str] = Query(None),
):
    """
    現在のリアルタイムインサイトを取得

    Args:
        limit: 取得する最大インサイト数 (1-50)
        priority: 優先度でフィルター (low, medium, high, urgent)
        insight_type: インサイトタイプでフィルター (performance, anomaly, pattern, trend)

    Returns:
        現在のインサイト一覧
    """
    try:
        from aetherterm.agentserver.domain.entities.terminals.asyncio_terminal import (
            AsyncioTerminal,
        )

        if not AsyncioTerminal.local_analyzer:
            return JSONResponse(
                {"insights": [], "total_count": 0, "message": "Local analyzer not initialized"}
            )

        # 現在のインサイトを取得
        insights = AsyncioTerminal.local_analyzer.get_current_insights()

        # フィルタリング
        if priority:
            insights = [i for i in insights if i.get("priority") == priority]

        if insight_type:
            insights = [i for i in insights if i.get("type") == insight_type]

        # 制限数の適用
        insights = insights[:limit]

        return JSONResponse(
            {
                "insights": insights,
                "total_count": len(insights),
                "timestamp": datetime.utcnow().isoformat(),
                "filters_applied": {"priority": priority, "type": insight_type, "limit": limit},
            }
        )

    except Exception as e:
        logger.error(f"Error getting current insights: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get insights: {str(e)}")


@router.get("/patterns")
async def get_detected_patterns(
    limit: int = Query(10, ge=1, le=30),
    pattern_type: Optional[str] = Query(None),
    severity: Optional[str] = Query(None, regex="^(info|warning|error|critical)$"),
):
    """
    検出されたパターンを取得

    Args:
        limit: 取得する最大パターン数 (1-30)
        pattern_type: パターンタイプでフィルター
        severity: 重要度でフィルター

    Returns:
        検出されたパターン一覧
    """
    try:
        from aetherterm.agentserver.domain.entities.terminals.asyncio_terminal import (
            AsyncioTerminal,
        )

        if not AsyncioTerminal.local_analyzer:
            return JSONResponse(
                {"patterns": [], "total_count": 0, "message": "Local analyzer not initialized"}
            )

        # パターンを取得
        patterns = AsyncioTerminal.local_analyzer.get_detected_patterns()

        # フィルタリング
        if pattern_type:
            patterns = [p for p in patterns if p.get("type") == pattern_type]

        if severity:
            patterns = [p for p in patterns if p.get("severity") == severity]

        # 制限数の適用
        patterns = patterns[:limit]

        return JSONResponse(
            {
                "patterns": patterns,
                "total_count": len(patterns),
                "timestamp": datetime.utcnow().isoformat(),
                "filters_applied": {"type": pattern_type, "severity": severity, "limit": limit},
            }
        )

    except Exception as e:
        logger.error(f"Error getting detected patterns: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get patterns: {str(e)}")


@router.get("/session/{session_id}")
async def get_session_insights(session_id: str):
    """
    特定セッションのインサイトを取得

    Args:
        session_id: セッションID

    Returns:
        セッション固有のインサイトとサマリ
    """
    try:
        from aetherterm.agentserver.domain.entities.terminals.asyncio_terminal import (
            AsyncioTerminal,
        )

        if not AsyncioTerminal.local_analyzer:
            raise HTTPException(status_code=503, detail="Local analyzer not available")

        # セッションサマリを取得
        session_summary = AsyncioTerminal.local_analyzer.get_session_summary(session_id)

        if "error" in session_summary:
            raise HTTPException(status_code=404, detail=session_summary["error"])

        # セッション関連のインサイトをフィルター
        all_insights = AsyncioTerminal.local_analyzer.get_current_insights()
        session_insights = [
            insight for insight in all_insights if session_id in insight.get("sessions", [])
        ]

        return JSONResponse(
            {
                "session_summary": session_summary,
                "related_insights": session_insights,
                "insight_count": len(session_insights),
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting session insights for {session_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get session insights: {str(e)}")


@router.get("/agent/summary")
async def get_agent_summary():
    """
    エージェント全体のサマリとインサイトを取得

    Returns:
        エージェントの全体統計と分析結果
    """
    try:
        from aetherterm.agentserver.domain.entities.terminals.asyncio_terminal import (
            AsyncioTerminal,
        )

        if not AsyncioTerminal.local_analyzer:
            return JSONResponse(
                {
                    "agent_summary": {"message": "Local analyzer not initialized"},
                    "recent_insights": [],
                    "detected_patterns": [],
                    "recommendations": [],
                }
            )

        # エージェントサマリを取得
        agent_summary = AsyncioTerminal.local_analyzer.get_agent_summary()

        # 最近のインサイトとパターンを取得
        recent_insights = AsyncioTerminal.local_analyzer.get_current_insights()[:5]  # 最新5件
        detected_patterns = AsyncioTerminal.local_analyzer.get_detected_patterns()[:5]  # 最新5件

        # 推奨事項の生成
        recommendations = _generate_recommendations(
            agent_summary, recent_insights, detected_patterns
        )

        return JSONResponse(
            {
                "agent_summary": agent_summary,
                "recent_insights": recent_insights,
                "detected_patterns": detected_patterns,
                "recommendations": recommendations,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

    except Exception as e:
        logger.error(f"Error getting agent summary: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get agent summary: {str(e)}")


@router.get("/real-time/alerts")
async def get_real_time_alerts(
    severity: Optional[str] = Query(None, regex="^(medium|high|urgent)$"),
):
    """
    リアルタイムアラートを取得

    Args:
        severity: 重要度でフィルター (medium以上のみ表示)

    Returns:
        重要度の高いリアルタイムアラート
    """
    try:
        from aetherterm.agentserver.domain.entities.terminals.asyncio_terminal import (
            AsyncioTerminal,
        )

        if not AsyncioTerminal.local_analyzer:
            return JSONResponse(
                {"alerts": [], "alert_count": 0, "message": "Local analyzer not available"}
            )

        # 高優先度のインサイトをアラートとして取得
        all_insights = AsyncioTerminal.local_analyzer.get_current_insights()

        # 重要度フィルター
        min_priority_level = {"medium": 2, "high": 3, "urgent": 4}
        priority_values = {"low": 1, "medium": 2, "high": 3, "urgent": 4}

        min_level = min_priority_level.get(severity, 2)  # デフォルトはmedium以上

        alerts = [
            insight
            for insight in all_insights
            if priority_values.get(insight.get("priority", "low"), 1) >= min_level
        ]

        # 最新順でソート
        alerts.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        return JSONResponse(
            {
                "alerts": alerts[:10],  # 最大10件
                "alert_count": len(alerts),
                "severity_filter": severity or "medium+",
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

    except Exception as e:
        logger.error(f"Error getting real-time alerts: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get alerts: {str(e)}")


@router.post("/demo/generate_test_data")
async def generate_test_data():
    """
    デモ用のテストデータを生成して分析機能をテスト

    Returns:
        生成されたテストデータと即座の分析結果
    """
    try:
        from aetherterm.agentserver.domain.entities.terminals.asyncio_terminal import (
            AsyncioTerminal,
        )
        import time

        if not AsyncioTerminal.local_analyzer:
            return JSONResponse(
                {
                    "error": "Local analyzer not initialized",
                    "message": "まずAgentServerを起動してローカル分析器を初期化してください",
                },
                status_code=503,
            )

        analyzer = AsyncioTerminal.local_analyzer
        session_id = "demo_session"

        # テストコマンドを生成
        test_commands = [
            ("ls -la", 0, 0.1),
            ("git status", 0, 0.3),
            ("npm install", 1, 15.2),  # 遅いコマンド
            ("python test.py", 1, 0.5),  # エラーコマンド
            ("docker build .", 0, 8.7),
            ("python test.py", 1, 0.4),  # 再度エラー
            ("ls", 0, 0.05),
            ("git status", 0, 0.2),
            ("python test.py", 1, 0.3),  # 3回目のエラー
        ]

        # テストデータを記録
        for i, (command, exit_code, exec_time) in enumerate(test_commands):
            analyzer.record_command(session_id, command, exit_code, exec_time)
            time.sleep(0.1)  # 少し間隔を空ける

        # テストエラーを生成
        test_errors = [
            ("import_error", "ModuleNotFoundError: No module named 'requests'"),
            ("syntax_error", "SyntaxError: invalid syntax"),
            ("connection_error", "ConnectionError: Failed to connect to database"),
        ]

        for error_type, error_msg in test_errors:
            analyzer.record_error(session_id, error_type, error_msg)
            time.sleep(0.1)

        # テストパフォーマンス指標を生成
        test_metrics = [
            ("response_time", 120.5, "ms"),
            ("memory_usage", 45.2, "MB"),
            ("cpu_usage", 78.3, "%"),
            ("response_time", 2500.0, "ms"),  # 遅いレスポンス
            ("memory_usage", 89.7, "MB"),  # 高メモリ使用量
        ]

        for metric_name, value, unit in test_metrics:
            analyzer.record_performance(session_id, metric_name, value, unit)
            time.sleep(0.1)

        # ユーザーインタラクションを生成
        test_interactions = [
            ("terminal_input", "cd /project"),
            ("terminal_resize", "80x24"),
            ("file_edit", "editing main.py"),
            ("terminal_input", "vim config.json"),
        ]

        for interaction_type, details in test_interactions:
            analyzer.record_user_interaction(session_id, interaction_type, details)
            time.sleep(0.1)

        # 短時間待機して分析結果を取得
        time.sleep(1)

        # 結果を取得
        insights = analyzer.get_current_insights()
        patterns = analyzer.get_detected_patterns()
        session_summary = analyzer.get_session_summary(session_id)
        agent_summary = analyzer.get_agent_summary()

        return JSONResponse(
            {
                "success": True,
                "message": "テストデータが生成され、分析が実行されました",
                "test_data_generated": {
                    "commands": len(test_commands),
                    "errors": len(test_errors),
                    "metrics": len(test_metrics),
                    "interactions": len(test_interactions),
                },
                "analysis_results": {
                    "insights_count": len(insights),
                    "patterns_count": len(patterns),
                    "session_summary": session_summary,
                    "agent_summary": agent_summary,
                    "sample_insights": insights[:3] if insights else [],
                    "sample_patterns": patterns[:3] if patterns else [],
                },
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

    except Exception as e:
        logger.error(f"Error generating test data: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate test data: {str(e)}")


@router.get("/performance/metrics")
async def get_performance_metrics():
    """
    パフォーマンス関連のメトリクスとインサイトを取得

    Returns:
        パフォーマンス分析結果
    """
    try:
        from aetherterm.agentserver.domain.entities.terminals.asyncio_terminal import (
            AsyncioTerminal,
        )

        if not AsyncioTerminal.local_analyzer:
            return JSONResponse(
                {"performance_metrics": {}, "message": "Local analyzer not available"}
            )

        # パフォーマンス関連のインサイトを抽出
        all_insights = AsyncioTerminal.local_analyzer.get_current_insights()
        performance_insights = [
            insight for insight in all_insights if insight.get("type") == "performance"
        ]

        # エージェントサマリからパフォーマンス情報を取得
        agent_summary = AsyncioTerminal.local_analyzer.get_agent_summary()

        # パフォーマンス統計を計算
        performance_stats = {
            "slow_commands_detected": len(
                [i for i in performance_insights if "execution_time" in i.get("data", {})]
            ),
            "overall_error_rate": agent_summary.get("overall_error_rate", 0),
            "total_commands": agent_summary.get("total_commands", 0),
            "active_sessions": agent_summary.get("active_sessions", 0),
            "memory_utilization": {
                "commands": agent_summary.get("memory_usage", {}).get("commands", 0),
                "errors": agent_summary.get("memory_usage", {}).get("errors", 0),
                "metrics": agent_summary.get("memory_usage", {}).get("performance_metrics", 0),
            },
        }

        return JSONResponse(
            {
                "performance_metrics": performance_stats,
                "performance_insights": performance_insights,
                "insight_count": len(performance_insights),
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

    except Exception as e:
        logger.error(f"Error getting performance metrics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get performance metrics: {str(e)}")


def _generate_recommendations(
    agent_summary: Dict, insights: List[Dict], patterns: List[Dict]
) -> List[Dict]:
    """推奨事項を生成"""

    recommendations = []

    # エラー率に基づく推奨事項
    error_rate = agent_summary.get("overall_error_rate", 0)
    if error_rate > 20:
        recommendations.append(
            {
                "type": "error_reduction",
                "priority": "high",
                "title": "高エラー率の改善",
                "description": f"エラー率が{error_rate:.1f}%と高い状態です。コマンド実行環境の見直しを検討してください。",
                "suggested_actions": [
                    "頻発するエラーの根本原因調査",
                    "ユーザー向けガイダンスの改善",
                    "環境設定の最適化",
                ],
            }
        )
    elif error_rate > 10:
        recommendations.append(
            {
                "type": "error_monitoring",
                "priority": "medium",
                "title": "エラー率の監視",
                "description": f"エラー率が{error_rate:.1f}%です。継続的な監視を推奨します。",
                "suggested_actions": ["定期的なエラーパターンの確認", "ユーザートレーニングの実施"],
            }
        )

    # パフォーマンス関連の推奨事項
    performance_insights = [i for i in insights if i.get("type") == "performance"]
    if len(performance_insights) > 3:
        recommendations.append(
            {
                "type": "performance_optimization",
                "priority": "medium",
                "title": "パフォーマンス最適化",
                "description": f"{len(performance_insights)}件のパフォーマンス問題が検出されています。",
                "suggested_actions": [
                    "遅いコマンドの最適化",
                    "システムリソースの確認",
                    "不要なプロセスの停止",
                ],
            }
        )

    # パターンに基づく推奨事項
    frequent_patterns = [p for p in patterns if p.get("frequency", 0) > 5]
    if frequent_patterns:
        recommendations.append(
            {
                "type": "automation",
                "priority": "low",
                "title": "作業自動化の検討",
                "description": f"{len(frequent_patterns)}件の頻出パターンが検出されています。",
                "suggested_actions": [
                    "頻出コマンドのスクリプト化",
                    "エイリアスの設定",
                    "ワークフローの最適化",
                ],
            }
        )

    return recommendations


# 初期化関数
async def initialize_local_analyzer(agent_id: str):
    """ローカル分析機能を初期化"""
    try:
        from aetherterm.agentserver.domain.entities.terminals.asyncio_terminal import (
            AsyncioTerminal,
        )
        from aetherterm.agentserver.short_term_memory_local import LocalShortTermAnalyzer

        if AsyncioTerminal.local_analyzer is None:
            AsyncioTerminal.local_analyzer = LocalShortTermAnalyzer(agent_id)
            await AsyncioTerminal.local_analyzer.start()
            logger.info(f"Local short-term analyzer initialized for agent {agent_id}")

        return True

    except Exception as e:
        logger.error(f"Failed to initialize local analyzer: {e}")
        return False
