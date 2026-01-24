"""
Agent Communication Service - Application Layer

Manages agent communication and coordination.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import uuid4

log = logging.getLogger("aetherterm.application.agent")
class AgentService:
    """Manages agent communication and coordination."""

    def __init__(self):
        self.active_agents: Dict[str, Dict[str, Any]] = {}
        self.spec_documents: Dict[str, str] = {}

    async def send_agent_message(
        self,
        sio_instance,
        message_type: str,
        from_agent_id: str,
        to_agent_id: Optional[str] = None,
        content: str = "",
        data: Optional[Dict[str, Any]] = None,
        priority: str = "medium",
        timeout: Optional[int] = None,
    ) -> str:
        """Send unified agent message."""
        try:
            message_id = str(uuid4())

            message = {
                "message_type": message_type,
                "message_id": message_id,
                "from_agent_id": from_agent_id,
                "to_agent_id": to_agent_id,
                "content": content,
                "data": data or {},
                "priority": priority,
                "timeout": timeout,
                "timestamp": datetime.utcnow().isoformat(),
            }

            await sio_instance.emit("agent_message", message)
            return message_id

        except Exception as e:
            log.error(f"Failed to send agent message: {e}")
            raise

    async def agent_start_request(
        self,
        sio_instance,
        agent_id: str,
        agent_type: str = "claude",
        parent_agent_id: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Handle agent startup request."""
        try:
            startup_command = f"claude --name {agent_id}"
            if parent_agent_id:
                startup_command += f" --parent {parent_agent_id} --sub-agent"

            self.active_agents[agent_id] = {
                "agent_id": agent_id,
                "agent_type": agent_type,
                "parent_agent_id": parent_agent_id,
                "started_at": datetime.utcnow().isoformat(),
                "status": "starting",
                "config": config or {},
            }

            await self.send_agent_message(
                sio_instance=sio_instance,
                message_type="agent_start_response",
                from_agent_id="agentserver",
                to_agent_id=agent_id,
                content=f"Agent {agent_id} startup initiated",
                data={"startup_command": startup_command},
            )

            return {"status": "success", "agent_id": agent_id, "startup_command": startup_command}

        except Exception as e:
            log.error(f"Failed to start agent {agent_id}: {e}")
            return {"status": "error", "agent_id": agent_id, "error": str(e)}

    async def upload_spec(self, spec_id: str, content: str) -> Dict[str, Any]:
        """Upload specification document."""
        try:
            self.spec_documents[spec_id] = content
            return {"status": "success", "spec_id": spec_id, "size": len(content)}
        except Exception as e:
            return {"status": "error", "spec_id": spec_id, "error": str(e)}

    async def query_spec(self, spec_id: str, query: Optional[str] = None) -> Dict[str, Any]:
        """Query specification document."""
        try:
            if spec_id not in self.spec_documents:
                return {"status": "not_found", "spec_id": spec_id}

            content = self.spec_documents[spec_id]

            if query:
                matching_lines = [
                    line for line in content.split("\n") if query.lower() in line.lower()
                ]
                result_content = "\n".join(matching_lines[:10])
            else:
                result_content = content

            return {"status": "success", "spec_id": spec_id, "content": result_content}
        except Exception as e:
            return {"status": "error", "spec_id": spec_id, "error": str(e)}
