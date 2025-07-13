"""
Agent Routes - Agent Management API

Provides REST API endpoints for agent startup and management.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from aetherterm.agentserver.domain.entities.terminals.asyncio_terminal import AsyncioTerminal

# Initialize router
router = APIRouter()
log = logging.getLogger("aetherterm.routes.agent")


# Agent Management Models
class AgentStartRequest(BaseModel):
    """Agent startup request model"""

    requester_agent_id: str
    agent_type: str  # developer, reviewer, tester, architect, researcher
    agent_id: Optional[str] = None
    working_directory: Optional[str] = "."
    launch_mode: str = "agent"
    startup_method: str = "claude_cli"  # claude_cli, docker, custom_script
    startup_command: Optional[str] = None  # MainAgentが指定するカスタムコマンド
    environment_vars: Dict[str, str] = {}  # 追加環境変数
    config: Dict[str, Any] = {}


class AgentStartResponse(BaseModel):
    """Agent startup response model"""

    session_id: str
    agent_id: str
    agent_type: str
    status: str  # started, failed
    working_directory: str
    startup_command: Optional[str] = None
    error: Optional[str] = None


async def _create_agent_terminal_via_rest(
    session_id: str,
    agent_id: str,
    agent_type: str,
    working_directory: str,
    launch_mode: str,
    agent_config: dict,
    requester_agent_id: str,
    startup_command: str,
) -> bool:
    """
    REST API経由でエージェント用ターミナルを作成する専用関数

    Returns:
        bool: ターミナル作成の成功・失敗
    """
    try:
        import asyncio

        from aetherterm.agentserver import utils
        from aetherterm.agentserver.interfaces.web.socket_handlers import sio_instance

        if not sio_instance:
            log.error("Socket.IO instance not available")
            return False

        # REST API用の仮想接続情報を作成
        virtual_environ = {
            "REMOTE_ADDR": "127.0.0.1",
            "HTTP_USER_AGENT": f"AetherTerm-RestAPI/{agent_type}",
            "HTTP_X_REMOTE_USER": f"agent_{agent_id}",
            "REQUEST_METHOD": "POST",
            "PATH_INFO": "/api/v1/agents/start",
        }

        socket = utils.ConnectionInfo(virtual_environ)

        # ターミナルインスタンスを作成
        terminal_instance = AsyncioTerminal(
            user=None,  # エージェント用なのでユーザーはNone
            path=working_directory,
            session=session_id,
            socket=socket,
            uri=f"http://127.0.0.1:57575/?session={session_id}",
            render_string=None,
            broadcast=lambda s, m: _rest_api_broadcast(s, m),
            login=False,  # エージェント用なのでログイン不要
            pam_profile="",
        )

        # エージェント設定を保存
        terminal_instance.agent_config = {
            "launch_mode": launch_mode,
            "agent_type": agent_type,
            "agent_config": agent_config,
            "requester_agent_id": requester_agent_id,
            "startup_command": startup_command,
            "agent_hierarchy": "sub" if requester_agent_id else "main",
            "parent_agent_id": requester_agent_id,
            "created_via": "rest_api",
        }

        # REST API専用のクライアントセットを初期化
        terminal_instance.client_sids = set()

        # PTYを開始
        await terminal_instance.start_pty()
        log.info(f"REST API: PTY started successfully for session {session_id}")

        # エージェント自動起動
        if startup_command and launch_mode == "agent":
            await asyncio.sleep(1)  # PTY初期化待ち
            await terminal_instance.write(startup_command + "\n")

            # MainAgentに通知
            if requester_agent_id and sio_instance:
                await sio_instance.emit(
                    "agent_message",
                    {
                        "message_type": "agent_start_response",
                        "requester_agent_id": requester_agent_id,
                        "session_id": session_id,
                        "agent_type": agent_type,
                        "agent_id": agent_id,
                        "status": "started",
                        "launch_mode": launch_mode,
                        "hierarchy": "sub",
                        "parent_agent_id": requester_agent_id,
                        "working_directory": working_directory,
                        "created_via": "rest_api",
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                )

            log.info(f"REST API: Agent {agent_type}:{agent_id} started successfully")

        return True

    except Exception as e:
        log.error(f"REST API terminal creation failed: {e}")
        return False


def _rest_api_broadcast(session_id: str, message: str):
    """
    REST API経由で作成されたターミナル用のブロードキャスト関数
    WebSocketクライアントがいない場合でも動作する
    """
    try:
        import asyncio

        from aetherterm.agentserver.interfaces.web.socket_handlers import sio_instance

        # 通常のブロードキャストロジックを実行（WebSocketクライアント向け）
        terminal = AsyncioTerminal.sessions.get(session_id)
        if terminal and hasattr(terminal, "client_sids") and terminal.client_sids:
            # WebSocketクライアントがいる場合は通常通りブロードキャスト
            for client_sid in list(terminal.client_sids):
                if sio_instance:
                    asyncio.create_task(
                        sio_instance.emit(
                            "terminal_output",
                            {"session": session_id, "data": message},
                            room=client_sid,
                        )
                    )

        # REST API用のログ記録（デバッグ用）
        if message and len(message.strip()) > 0:
            log.debug(f"REST API Terminal {session_id}: {message.strip()[:100]}")

    except Exception as e:
        log.error(f"REST API broadcast error: {e}")


@router.post("/api/v1/agents/start", response_model=AgentStartResponse)
async def start_agent(request: AgentStartRequest):
    """
    P0 緊急対応: エージェント動的起動API

    MainAgentが他のSubAgentを起動するためのREST APIエンドポイント
    """
    try:
        from aetherterm.agentserver.interfaces.web.socket_handlers import (
            _build_agent_command,
            sio_instance,
        )

        # Generate session and agent IDs
        session_id = str(uuid4())
        agent_id = request.agent_id or f"{request.agent_type}_{str(uuid4())[:8]}"

        # Build agent configuration with MainAgent's startup instructions
        agent_config = {
            "agent_type": request.agent_type,
            "agent_id": agent_id,
            "working_directory": request.working_directory,
            "startup_method": request.startup_method,
            "custom_startup_command": request.startup_command,
            "custom_environment_vars": request.environment_vars,
            "requester_agent_id": request.requester_agent_id,
            **request.config,
        }

        # Build startup command
        startup_command = _build_agent_command(request.agent_type, agent_config)

        log.info(
            f"REST API agent start: {request.agent_type}:{agent_id} for {request.requester_agent_id}"
        )

        # REST API経由でも実際にターミナルを作成する
        if sio_instance:
            try:
                # Socket.IOインスタンスが利用可能な場合、実際にターミナルを作成
                terminal_created = await _create_agent_terminal_via_rest(
                    session_id=session_id,
                    agent_id=agent_id,
                    agent_type=request.agent_type,
                    working_directory=request.working_directory,
                    launch_mode=request.launch_mode,
                    agent_config=agent_config,
                    requester_agent_id=request.requester_agent_id,
                    startup_command=startup_command,
                )

                if terminal_created:
                    # ターミナル作成が成功した場合
                    return AgentStartResponse(
                        session_id=session_id,
                        agent_id=agent_id,
                        agent_type=request.agent_type,
                        status="started",  # 実際に起動した
                        working_directory=request.working_directory,
                        startup_command=startup_command,
                    )
                # ターミナル作成に失敗した場合
                return AgentStartResponse(
                    session_id=session_id,
                    agent_id=agent_id,
                    agent_type=request.agent_type,
                    status="failed",
                    working_directory=request.working_directory,
                    startup_command=startup_command,
                    error="Terminal creation failed",
                )
            except Exception as terminal_error:
                log.error(f"Terminal creation failed: {terminal_error}")
                # エラーが発生した場合でも起動情報は返す
                return AgentStartResponse(
                    session_id=session_id,
                    agent_id=agent_id,
                    agent_type=request.agent_type,
                    status="ready",  # 起動準備完了（手動でWebSocket接続が必要）
                    working_directory=request.working_directory,
                    startup_command=startup_command,
                    error=f"Auto-terminal creation failed: {terminal_error!s}",
                )
        else:
            # Socket.IOインスタンスが利用できない場合、起動情報のみを返す
            return AgentStartResponse(
                session_id=session_id,
                agent_id=agent_id,
                agent_type=request.agent_type,
                status="ready",  # 起動準備完了（WebSocket接続が必要）
                working_directory=request.working_directory,
                startup_command=startup_command,
                error="Socket.IO not available - manual WebSocket connection required",
            )

    except Exception as e:
        log.error(f"Error in agent start API: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Agent startup failed",
                "message": str(e),
                "requester_agent_id": request.requester_agent_id,
            },
        )


@router.get("/api/v1/agents/status")
async def get_agents_status():
    """
    アクティブなエージェントの状態を取得
    """
    try:
        agents = []
        for session_id, terminal in AsyncioTerminal.sessions.items():
            if hasattr(terminal, "agent_config") and terminal.agent_config:
                agent_config = terminal.agent_config
                agents.append(
                    {
                        "session_id": session_id,
                        "agent_id": agent_config.get("agent_config", {}).get("agent_id"),
                        "agent_type": agent_config.get("agent_type"),
                        "status": "ready" if not terminal.closed else "closed",
                        "working_directory": agent_config.get("agent_config", {}).get(
                            "working_directory"
                        ),
                        "launch_mode": agent_config.get("launch_mode"),
                        "requester_agent_id": agent_config.get("requester_agent_id"),
                    }
                )

        return JSONResponse({"agents": agents, "total_agents": len(agents)})

    except Exception as e:
        log.error(f"Error getting agents status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get agents status: {e!s}")
