"""Agent management handlers."""

import asyncio
import logging
from uuid import uuid4
from .base import sio_instance, socket_error_handler

log = logging.getLogger("aetherterm.socket_handlers")


def _build_agent_command(agent_type: str, agent_config: dict) -> str:
    """
    MainAgentの指示に基づいて起動コマンドを構築

    Args:
        agent_type: エージェントタイプ (developer, reviewer, tester, architect, researcher)
        agent_config: エージェント設定

    Returns:
        起動コマンド文字列
    """
    agent_id = agent_config.get("agent_id", f"{agent_type}_agent")
    working_dir = agent_config.get("working_directory", ".")
    requester_agent_id = agent_config.get("requester_agent_id")
    startup_method = agent_config.get("startup_method", "claude_cli")
    custom_startup_command = agent_config.get("custom_startup_command")
    custom_env_vars = agent_config.get("custom_environment_vars", {})

    # 共通の環境変数設定
    base_env_vars = [
        f"AGENT_ID={agent_id}",
        f"AGENT_TYPE={agent_type}",
        "AGENT_ROLE=sub_agent",
        "AETHERTERM_SERVER=ws://localhost:57575",
    ]

    # 要求元エージェントがある場合は追加
    if requester_agent_id:
        base_env_vars.append(f"PARENT_AGENT_ID={requester_agent_id}")
        base_env_vars.append("AGENT_HIERARCHY=sub")
    else:
        base_env_vars.append("AGENT_HIERARCHY=main")

    # MainAgentが指定したカスタム環境変数を追加
    for key, value in custom_env_vars.items():
        base_env_vars.append(f"{key}={value}")

    env_vars_str = " ".join(base_env_vars)

    # MainAgentがカスタム起動コマンドを指定している場合
    if custom_startup_command:
        # プレースホルダーを置換
        command = custom_startup_command.format(
            agent_id=agent_id,
            agent_type=agent_type,
            working_directory=working_dir,
            parent_agent_id=requester_agent_id or "",
        )
        return f"cd {working_dir} && {env_vars_str} {command}"

    # 起動メソッド別のコマンド構築
    if startup_method == "docker":
        # Dockerコンテナでエージェントを起動
        docker_image = agent_config.get("docker_image", f"aether-agent-{agent_type}:latest")
        return f"cd {working_dir} && {env_vars_str} docker run --rm -v $(pwd):/workspace -e AGENT_ID={agent_id} -e AGENT_TYPE={agent_type} {docker_image}"

    if startup_method == "custom_script":
        # カスタムスクリプトで起動
        script_path = agent_config.get("script_path", f"./scripts/start-{agent_type}-agent.sh")
        return f"cd {working_dir} && {env_vars_str} {script_path} {agent_id}"

    # startup_method == "claude_cli" or default
    # エージェントタイプ別のClaude CLIコマンド構築
    if agent_type == "developer":
        return f"cd {working_dir} && {env_vars_str} claude --name {agent_id} --role developer --sub-agent"
    if agent_type == "reviewer":
        return f"cd {working_dir} && {env_vars_str} claude --name {agent_id} --role reviewer --mode review --sub-agent"
    if agent_type == "tester":
        return f"cd {working_dir} && {env_vars_str} claude --name {agent_id} --role tester --mode test --sub-agent"
    if agent_type == "architect":
        return f"cd {working_dir} && {env_vars_str} claude --name {agent_id} --role architect --mode design --sub-agent"
    if agent_type == "researcher":
        return f"cd {working_dir} && {env_vars_str} claude --name {agent_id} --role researcher --mode analyze --sub-agent"
    return f"cd {working_dir} && {env_vars_str} claude --name {agent_id} --sub-agent"


@socket_error_handler("agent_error")
async def agent_start_request(sid, data):
    """
    エージェント起動要請を処理

    メッセージフォーマット:
    {
        "requester_agent_id": "claude_main_001",
        "agent_type": "tester",
        "agent_id": "claude_tester_002",
        "working_directory": "/workspace/project",
        "launch_mode": "agent",
        "startup_method": "claude_cli",
        "startup_command": "claude --name {agent_id} --role {agent_type} --sub-agent",
        "environment_vars": {},
        "config": {}
    }
    """
    try:
        agent_type = data.get("agent_type", "developer")
        agent_id = data.get("agent_id", f"{agent_type}_{uuid4().hex[:8]}")
        working_directory = data.get("working_directory", ".")
        requester_agent_id = data.get("requester_agent_id")
        launch_mode = data.get("launch_mode", "agent")
        startup_method = data.get("startup_method", "claude_cli")
        custom_startup_command = data.get("startup_command")
        custom_env_vars = data.get("environment_vars", {})
        agent_config_data = data.get("config", {})

        log.info(f"Agent start request - Type: {agent_type}, ID: {agent_id}, Requester: {requester_agent_id}")

        # 設定の構築
        agent_config = {
            "agent_id": agent_id,
            "agent_type": agent_type,
            "working_directory": working_directory,
            "requester_agent_id": requester_agent_id,
            "startup_method": startup_method,
            "custom_startup_command": custom_startup_command,
            "custom_environment_vars": custom_env_vars,
            "launch_mode": launch_mode,
            **agent_config_data,
        }

        # エージェント起動コマンドの構築
        agent_command = _build_agent_command(agent_type, agent_config)
        log.info(f"Generated agent command: {agent_command}")

        # エージェント機能とインストラクションの取得
        capabilities = _get_agent_capabilities(agent_type)
        instructions = _get_agent_instructions(agent_type, requester_agent_id)

        # 新しいターミナルセッションでエージェントを起動
        agent_session_id = f"agent_{agent_id}"

        # ターミナル作成データの構築
        terminal_data = {
            "session": agent_session_id,
            "tabId": f"agent_tab_{agent_id}",
            "subType": "agent",
            "cols": 120,
            "rows": 30,
            "user": "",
            "path": working_directory,
            "command": agent_command,
            "agent_config": agent_config,
            "capabilities": capabilities,
            "instructions": instructions,
        }

        # ターミナル作成サービスを使用してエージェントを起動
        from .terminal import create_terminal
        await create_terminal(sid, terminal_data)

        # 成功レスポンス
        response_data = {
            "status": "started",
            "agent_id": agent_id,
            "agent_type": agent_type,
            "session_id": agent_session_id,
            "capabilities": capabilities,
            "instructions": instructions,
            "command": agent_command,
        }

        await sio_instance.emit("agent_started", response_data, room=sid)
        log.info(f"Agent {agent_id} started successfully in session {agent_session_id}")

    except Exception as e:
        log.error(f"Error starting agent: {e}", exc_info=True)
        await sio_instance.emit(
            "agent_error",
            {"error": f"Failed to start agent: {str(e)}"},
            room=sid,
        )


@socket_error_handler("spec_error")
async def spec_upload(sid, data):
    """Handle specification upload for agent coordination."""
    try:
        spec_content = data.get("spec_content", "")
        spec_type = data.get("spec_type", "requirement")
        spec_id = data.get("spec_id", str(uuid4()))
        agent_id = data.get("agent_id", "")

        log.info(f"Spec upload - Type: {spec_type}, ID: {spec_id}, Agent: {agent_id}")

        # Save specification to memory or storage
        from aetherterm.agentserver.infrastructure.logging.log_analyzer import get_log_analyzer
        
        analyzer = await get_log_analyzer()
        if analyzer:
            await analyzer.store_specification(
                spec_id=spec_id,
                spec_type=spec_type,
                content=spec_content,
                agent_id=agent_id,
            )

        await sio_instance.emit(
            "spec_uploaded",
            {
                "status": "success",
                "spec_id": spec_id,
                "spec_type": spec_type,
                "message": "Specification uploaded successfully",
            },
            room=sid,
        )

    except Exception as e:
        log.error(f"Error uploading spec: {e}", exc_info=True)
        await sio_instance.emit("spec_error", {"error": str(e)}, room=sid)


@socket_error_handler("spec_error")
async def spec_query(sid, data):
    """Handle specification query requests."""
    try:
        query_type = data.get("query_type", "search")
        query_content = data.get("query_content", "")
        agent_id = data.get("agent_id", "")

        log.info(f"Spec query - Type: {query_type}, Agent: {agent_id}")

        # Query specifications from memory or storage
        from aetherterm.agentserver.infrastructure.logging.log_analyzer import get_log_analyzer
        
        analyzer = await get_log_analyzer()
        results = []
        
        if analyzer:
            results = await analyzer.query_specifications(
                query_type=query_type,
                query_content=query_content,
                agent_id=agent_id,
            )

        await sio_instance.emit(
            "spec_results",
            {
                "status": "success",
                "query_type": query_type,
                "results": results,
            },
            room=sid,
        )

    except Exception as e:
        log.error(f"Error querying specs: {e}", exc_info=True)
        await sio_instance.emit("spec_error", {"error": str(e)}, room=sid)


def _get_agent_capabilities(agent_type: str) -> list:
    """Get capabilities for a specific agent type."""
    capabilities_map = {
        "developer": [
            "code_generation",
            "debugging",
            "refactoring",
            "documentation",
            "version_control",
            "dependency_management",
        ],
        "reviewer": [
            "code_review",
            "security_analysis",
            "performance_analysis",
            "style_checking",
            "best_practices",
            "quality_assessment",
        ],
        "tester": [
            "unit_testing",
            "integration_testing",
            "test_automation",
            "coverage_analysis",
            "performance_testing",
            "security_testing",
        ],
        "architect": [
            "system_design",
            "architecture_review",
            "pattern_recommendation",
            "scalability_analysis",
            "technology_selection",
            "documentation_design",
        ],
        "researcher": [
            "code_analysis",
            "pattern_discovery",
            "technology_research",
            "best_practice_analysis",
            "trend_analysis",
            "documentation_research",
        ],
    }
    return capabilities_map.get(agent_type, ["general_assistance"])


def _get_agent_instructions(agent_type: str, parent_agent_id: str = None) -> dict:
    """Get instructions for a specific agent type."""
    base_instructions = {
        "developer": {
            "role": "Senior Software Developer",
            "primary_tasks": [
                "Write clean, maintainable code",
                "Implement features according to specifications",
                "Debug and fix issues",
                "Create comprehensive documentation",
            ],
            "guidelines": [
                "Follow coding standards and best practices",
                "Write unit tests for new functionality",
                "Use meaningful variable and function names",
                "Comment complex logic clearly",
            ],
        },
        "reviewer": {
            "role": "Code Review Specialist",
            "primary_tasks": [
                "Review code for quality and correctness",
                "Identify security vulnerabilities",
                "Check adherence to coding standards",
                "Provide constructive feedback",
            ],
            "guidelines": [
                "Focus on code quality and maintainability",
                "Check for potential bugs and edge cases",
                "Ensure proper error handling",
                "Verify test coverage",
            ],
        },
        "tester": {
            "role": "Quality Assurance Engineer",
            "primary_tasks": [
                "Design and implement comprehensive tests",
                "Verify functionality meets requirements",
                "Identify edge cases and potential failures",
                "Ensure adequate test coverage",
            ],
            "guidelines": [
                "Create both unit and integration tests",
                "Test error conditions and edge cases",
                "Maintain test documentation",
                "Automate testing where possible",
            ],
        },
        "architect": {
            "role": "Software Architect",
            "primary_tasks": [
                "Design system architecture",
                "Define technical standards",
                "Review architectural decisions",
                "Guide technology choices",
            ],
            "guidelines": [
                "Consider scalability and maintainability",
                "Balance technical debt and feature delivery",
                "Document architectural decisions",
                "Ensure security and performance",
            ],
        },
        "researcher": {
            "role": "Technical Researcher",
            "primary_tasks": [
                "Analyze codebases and patterns",
                "Research best practices",
                "Investigate new technologies",
                "Document findings and recommendations",
            ],
            "guidelines": [
                "Provide evidence-based recommendations",
                "Consider multiple perspectives",
                "Document research methodology",
                "Focus on practical applications",
            ],
        },
    }

    instructions = base_instructions.get(agent_type, {
        "role": "General Assistant",
        "primary_tasks": ["Assist with general development tasks"],
        "guidelines": ["Follow best practices", "Communicate clearly"],
    })

    # Add parent agent context if provided
    if parent_agent_id:
        instructions["coordination"] = {
            "parent_agent": parent_agent_id,
            "communication": "Report progress and issues to parent agent",
            "hierarchy": "Follow parent agent's guidance and priorities",
        }

    return instructions


@socket_error_handler("agent_error")
async def agent_hello(sid, data):
    """Handle agent hello/registration messages."""
    try:
        agent_id = data.get("agent_id")
        agent_type = data.get("agent_type")
        parent_agent_id = data.get("parent_agent_id")
        capabilities = data.get("capabilities", [])

        log.info(f"Agent hello - ID: {agent_id}, Type: {agent_type}, Parent: {parent_agent_id}")

        # Register agent in the system
        from aetherterm.agentserver.domain.services.agent_service import get_agent_service
        
        agent_service = get_agent_service()
        await agent_service.register_agent(
            agent_id=agent_id,
            agent_type=agent_type,
            parent_agent_id=parent_agent_id,
            capabilities=capabilities,
            connection_id=sid,
        )

        # Send welcome response with system information
        response = {
            "status": "registered",
            "agent_id": agent_id,
            "system_info": {
                "aetherterm_server": "ws://localhost:57575",
                "logging_enabled": True,
                "coordination_enabled": True,
            },
            "instructions": _get_agent_instructions(agent_type, parent_agent_id),
        }

        await sio_instance.emit("agent_welcome", response, room=sid)
        log.info(f"Agent {agent_id} registered successfully")

    except Exception as e:
        log.error(f"Error in agent hello: {e}", exc_info=True)
        await sio_instance.emit("agent_error", {"error": str(e)}, room=sid)