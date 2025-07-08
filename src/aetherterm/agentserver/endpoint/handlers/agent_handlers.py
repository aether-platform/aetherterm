"""
Agent WebSocket Handlers - Interface Layer

Agent communication and coordination handlers with Dependency Injection.
"""

import logging
from datetime import datetime
from uuid import uuid4
# from dependency_injector.wiring import inject, Provide

from aetherterm.agentserver.domain.services.agent_service import AgentService
# from aetherterm.agentserver.infrastructure.config.di_container import MainContainer

log = logging.getLogger("aetherterm.handlers.agent")


# @inject
async def agent_start_request(
    sid,
    data,
    sio_instance,
    # agent_service: AgentService = Provide[MainContainer.application.agent_service]
):
    """Handle agent startup request."""
    try:
        agent_id = data.get("agent_id") or f"agent_{uuid4().hex[:8]}"
        agent_type = data.get("agent_type", "claude")
        parent_agent_id = data.get("parent_agent_id")
        config = data.get("config", {})

        # Use injected agent service for agent startup
        # result = await agent_service.agent_start_request(
        #     sio_instance=sio_instance,
        #     agent_id=agent_id,
        #     agent_type=agent_type,
        #     parent_agent_id=parent_agent_id,
        #     config=config,
        # )
        result = {
            "agent_id": agent_id,
            "agent_type": agent_type,
            "parent_agent_id": parent_agent_id,
            "config": config,
            "disabled": "dependency injection temporarily disabled",
        }

        await sio_instance.emit("agent_start_response", result, room=sid)

    except Exception as e:
        log.error(f"Failed to start agent: {e}")
        await sio_instance.emit("error", {"message": str(e)}, room=sid)


async def agent_hello(sid, data, sio_instance):
    """Handle agent registration and initialization."""
    try:
        agent_id = data.get("agent_id")
        agent_type = data.get("agent_type", "unknown")
        capabilities = data.get("capabilities", [])

        log.info(f"Agent {agent_id} ({agent_type}) registered with capabilities: {capabilities}")

        # Broadcast agent joining announcement
        await sio_instance.emit(
            "agent_announcement",
            {
                "type": "agent_joined",
                "agent_id": agent_id,
                "agent_type": agent_type,
                "capabilities": capabilities,
                "announcement": f"Agent {agent_id} ({agent_type}) has joined the workspace.",
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

    except Exception as e:
        log.error(f"Error handling agent hello: {e}")
        await sio_instance.emit("error", {"message": f"Agent hello failed: {e!s}"}, room=sid)


# @inject
async def spec_upload(
    sid,
    data,
    sio_instance,
    # agent_service: AgentService = Provide[MainContainer.application.agent_service]
):
    """Handle specification document upload."""
    try:
        spec_id = data.get("spec_id") or f"spec_{uuid4().hex[:8]}"
        content = data.get("content", "")

        # Use injected agent service for spec upload
        # result = await agent_service.upload_spec(spec_id, content)
        result = {"spec_id": spec_id, "disabled": "dependency injection temporarily disabled"}

        await sio_instance.emit("spec_upload_response", result, room=sid)

    except Exception as e:
        log.error(f"Error handling spec upload: {e}")
        await sio_instance.emit("error", {"message": f"Spec upload failed: {e!s}"}, room=sid)


# @inject
async def spec_query(
    sid,
    data,
    sio_instance,
    # agent_service: AgentService = Provide[MainContainer.application.agent_service]
):
    """Handle specification document query."""
    try:
        spec_id = data.get("spec_id")
        query = data.get("query")

        # Use injected agent service for spec query
        # result = await agent_service.query_spec(spec_id, query)
        result = {
            "spec_id": spec_id,
            "query": query,
            "disabled": "dependency injection temporarily disabled",
        }

        await sio_instance.emit("spec_query_response", result, room=sid)

    except Exception as e:
        log.error(f"Error handling spec query: {e}")
        await sio_instance.emit("error", {"message": f"Spec query failed: {e!s}"}, room=sid)


async def control_message(sid, data, sio_instance):
    """Handle system control messages."""
    try:
        message_type = data.get("message_type", "unknown")
        target_agent_id = data.get("target_agent_id")
        control_data = data.get("data", {})

        log.info(f"Control message: {message_type} to {target_agent_id}")

        # Broadcast control message to target agent
        await sio_instance.emit(
            "control_message_broadcast",
            {
                "message_type": message_type,
                "target_agent_id": target_agent_id,
                "data": control_data,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

    except Exception as e:
        log.error(f"Error handling control message: {e}")
        await sio_instance.emit("error", {"message": f"Control message failed: {e!s}"}, room=sid)
