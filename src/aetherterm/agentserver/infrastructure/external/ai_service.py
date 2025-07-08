"""
AI Service - Infrastructure Layer

Simplified AI service for chat and log search functionality only.
Supports multiple providers: mock, anthropic, lmstudio.
"""

import asyncio
import logging
import re
import aiohttp
import json
import os
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from .claude_usage_tracker import ClaudeUsageTracker

log = logging.getLogger("aetherterm.infrastructure.ai")


@dataclass
class UsageCost:
    """Usage cost information."""

    input_tokens: int
    output_tokens: int
    total_tokens: int
    input_cost: float
    output_cost: float
    total_cost: float
    timestamp: str
    model: str
    provider: str


class ClaudeCostTracker:
    """Cost tracker that reads from Claude CLI usage database."""

    def __init__(self):
        self.claude_db_path = os.path.expanduser("~/.claude/usage.db")

    def get_usage_stats(self, days: int = 30) -> Dict[str, Any]:
        """Get Claude usage statistics from the last N days."""
        if not os.path.exists(self.claude_db_path):
            return {
                "total_cost": 0.0,
                "total_tokens": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "requests": 0,
                "period_days": days,
                "available": False,
                "message": "Claude CLI usage database not found",
            }

        try:
            conn = sqlite3.connect(self.claude_db_path)
            cursor = conn.cursor()

            # Get usage from the last N days
            since_date = (datetime.now() - timedelta(days=days)).isoformat()

            # Query usage data
            cursor.execute(
                """
                SELECT 
                    SUM(input_tokens) as total_input,
                    SUM(output_tokens) as total_output,
                    SUM(input_tokens + output_tokens) as total_tokens,
                    COUNT(*) as requests,
                    SUM(cost) as total_cost
                FROM usage 
                WHERE timestamp >= ?
            """,
                (since_date,),
            )

            result = cursor.fetchone()
            conn.close()

            if result and result[0] is not None:
                return {
                    "total_cost": round(result[4] or 0.0, 4),
                    "total_tokens": result[2] or 0,
                    "input_tokens": result[0] or 0,
                    "output_tokens": result[1] or 0,
                    "requests": result[3] or 0,
                    "period_days": days,
                    "available": True,
                    "average_cost_per_request": round(
                        (result[4] or 0.0) / max(result[3] or 1, 1), 4
                    ),
                    "cost_per_1k_tokens": round(
                        (result[4] or 0.0) / max((result[2] or 1) / 1000, 0.001), 4
                    ),
                }
            else:
                return {
                    "total_cost": 0.0,
                    "total_tokens": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "requests": 0,
                    "period_days": days,
                    "available": True,
                    "message": f"No usage data found for the last {days} days",
                }

        except Exception as e:
            log.error(f"Error reading Claude usage database: {e}")
            return {
                "total_cost": 0.0,
                "total_tokens": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "requests": 0,
                "period_days": days,
                "available": False,
                "error": str(e),
            }

    def get_daily_breakdown(self, days: int = 7) -> List[Dict[str, Any]]:
        """Get daily usage breakdown for the last N days."""
        if not os.path.exists(self.claude_db_path):
            return []

        try:
            conn = sqlite3.connect(self.claude_db_path)
            cursor = conn.cursor()

            since_date = (datetime.now() - timedelta(days=days)).isoformat()

            cursor.execute(
                """
                SELECT 
                    DATE(timestamp) as date,
                    SUM(input_tokens) as input_tokens,
                    SUM(output_tokens) as output_tokens,
                    COUNT(*) as requests,
                    SUM(cost) as cost
                FROM usage 
                WHERE timestamp >= ?
                GROUP BY DATE(timestamp)
                ORDER BY date DESC
            """,
                (since_date,),
            )

            results = cursor.fetchall()
            conn.close()

            daily_stats = []
            for row in results:
                daily_stats.append(
                    {
                        "date": row[0],
                        "input_tokens": row[1] or 0,
                        "output_tokens": row[2] or 0,
                        "total_tokens": (row[1] or 0) + (row[2] or 0),
                        "requests": row[3] or 0,
                        "cost": round(row[4] or 0.0, 4),
                    }
                )

            return daily_stats

        except Exception as e:
            log.error(f"Error reading daily breakdown: {e}")
            return []

    def get_model_breakdown(self, days: int = 30) -> List[Dict[str, Any]]:
        """Get usage breakdown by model."""
        if not os.path.exists(self.claude_db_path):
            return []

        try:
            conn = sqlite3.connect(self.claude_db_path)
            cursor = conn.cursor()

            since_date = (datetime.now() - timedelta(days=days)).isoformat()

            cursor.execute(
                """
                SELECT 
                    model,
                    SUM(input_tokens) as input_tokens,
                    SUM(output_tokens) as output_tokens,
                    COUNT(*) as requests,
                    SUM(cost) as cost
                FROM usage 
                WHERE timestamp >= ?
                GROUP BY model
                ORDER BY cost DESC
            """,
                (since_date,),
            )

            results = cursor.fetchall()
            conn.close()

            model_stats = []
            for row in results:
                model_stats.append(
                    {
                        "model": row[0] or "unknown",
                        "input_tokens": row[1] or 0,
                        "output_tokens": row[2] or 0,
                        "total_tokens": (row[1] or 0) + (row[2] or 0),
                        "requests": row[3] or 0,
                        "cost": round(row[4] or 0.0, 4),
                    }
                )

            return model_stats

        except Exception as e:
            log.error(f"Error reading model breakdown: {e}")
            return []


class AIService:
    """Simplified AI service for chat and log search."""

    def __init__(
        self,
        provider: str = "mock",
        api_key: Optional[str] = None,
        model: str = "claude-3-5-sonnet",
        lmstudio_url: str = "http://localhost:1234",
    ):
        self.provider = provider
        self.api_key = api_key
        self.model = model
        self.lmstudio_url = lmstudio_url
        self._cached_lmstudio_model = None

        # Initialize cost tracking
        self.claude_cost_tracker = ClaudeCostTracker()
        self.claude_usage_tracker = ClaudeUsageTracker()

        # Session usage tracking (for non-Claude providers)
        self.session_usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "requests": 0,
            "estimated_cost": 0.0,
        }

    @property
    def provider_name(self) -> str:
        """Get the provider name."""
        return self.provider

    def get_model_info(self) -> Dict[str, Any]:
        """Get model information."""
        model_name = self.model

        # For LMStudio, try to get the actual loaded model
        if self.provider == "lmstudio" and self._cached_lmstudio_model is None:
            try:
                import requests

                response = requests.get(f"{self.lmstudio_url}/v1/models", timeout=2)
                if response.status_code == 200:
                    models = response.json().get("data", [])
                    if models:
                        # Get the first model (usually the loaded one)
                        self._cached_lmstudio_model = models[0].get("id", "unknown")
                        model_name = self._cached_lmstudio_model
            except Exception as e:
                log.debug(f"Failed to fetch LMStudio model info: {e}")
        elif self.provider == "lmstudio" and self._cached_lmstudio_model:
            model_name = self._cached_lmstudio_model

        return {
            "model": model_name,
            "provider": self.provider,
            "url": self.lmstudio_url if self.provider == "lmstudio" else None,
        }

    async def check_connection(self) -> bool:
        """Check if connection to AI service is working."""
        return await self.is_available()

    async def is_available(self) -> bool:
        """Check if AI service is available."""
        if self.provider == "mock":
            return True
        if self.provider == "anthropic":
            return bool(self.api_key)
        if self.provider == "lmstudio":
            try:
                async with aiohttp.ClientSession() as session:
                    # Use /v1/models endpoint for health check since LMStudio doesn't have /health
                    async with session.get(
                        f"{self.lmstudio_url}/v1/models", timeout=aiohttp.ClientTimeout(total=5)
                    ) as response:
                        return response.status == 200
            except Exception as e:
                log.warning(f"LMStudio health check failed: {e}")
                return False
        return False

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        terminal_context: Optional[Dict[str, Any]] = None,
        stream: bool = False,
    ):
        """Generate chat completion for terminal assistance."""
        if self.provider == "mock":
            # Mock response for testing
            last_message = messages[-1].get("content", "") if messages else ""

            # Provide contextual responses based on the message
            if "error" in last_message.lower():
                response = "I can help you troubleshoot this error. Can you provide more details about what you were trying to do?"
            elif "command" in last_message.lower():
                response = "I can help you with terminal commands. What specific task are you trying to accomplish?"
            elif "log" in last_message.lower():
                response = "I can help you analyze logs. You can use the log search feature to find specific entries."
            else:
                response = f"I understand you're asking about: {last_message[:50]}... How can I assist you with your terminal work?"

            # Track usage for mock provider
            self._track_usage(last_message, response)

            if stream:
                for chunk in response.split():
                    yield chunk + " "
                    await asyncio.sleep(0.05)
            else:
                yield response
        elif self.provider == "lmstudio":
            # LMStudio implementation
            async for chunk in self._lmstudio_completion(messages, terminal_context, stream):
                yield chunk
        else:
            # Real implementation would call external API
            raise NotImplementedError(f"Provider {self.provider} not implemented")

    async def search_logs(
        self, query: str, logs: List[Dict[str, Any]], limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Search logs using AI-enhanced matching."""
        if not query or not logs:
            return []

        # Simple implementation - can be enhanced with actual AI
        query_lower = query.lower()
        matched_logs = []

        for log_entry in logs:
            content = log_entry.get("content", "").lower()
            category = log_entry.get("category", "").lower()

            # Basic fuzzy matching
            if (
                query_lower in content
                or query_lower in category
                or any(word in content for word in query_lower.split())
            ):
                # Calculate relevance score
                score = 0
                if query_lower in content:
                    score += 10
                if query_lower in category:
                    score += 5

                log_entry_with_score = {**log_entry, "relevance_score": score}
                matched_logs.append(log_entry_with_score)

        # Sort by relevance and return top results
        matched_logs.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        return matched_logs[:limit]

    async def suggest_search_terms(self, partial_query: str) -> List[str]:
        """Suggest search terms based on partial input."""
        # Simple suggestions - can be enhanced with AI
        common_terms = [
            "error",
            "warning",
            "info",
            "success",
            "failed",
            "completed",
            "connection",
            "timeout",
            "permission",
            "not found",
            "syntax",
            "command",
            "process",
            "system",
            "network",
            "database",
        ]

        if not partial_query:
            return common_terms[:5]

        query_lower = partial_query.lower()
        suggestions = [
            term for term in common_terms if query_lower in term or term.startswith(query_lower)
        ]

        return suggestions[:5]

    async def _lmstudio_completion(
        self,
        messages: List[Dict[str, str]],
        terminal_context: Optional[Dict[str, Any]] = None,
        stream: bool = False,
    ):
        """Handle LMStudio API completion."""
        input_text = ""
        output_text = ""

        try:
            # Prepare system prompt with terminal context
            system_prompt = "You are a helpful terminal assistant that helps users with command-line tasks, troubleshooting, and system administration."
            if terminal_context:
                context_info = []
                if "current_directory" in terminal_context:
                    context_info.append(
                        f"Current directory: {terminal_context['current_directory']}"
                    )
                if "recent_commands" in terminal_context:
                    context_info.append(
                        f"Recent commands: {', '.join(terminal_context['recent_commands'][-3:])}"
                    )
                if context_info:
                    system_prompt += f"\n\nContext: {'; '.join(context_info)}"

            # Convert messages to LMStudio format and collect input text for tracking
            formatted_messages = [{"role": "system", "content": system_prompt}]
            for msg in messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role == "user":
                    input_text += content + " "
                formatted_messages.append({"role": role, "content": content})

            # Prepare request payload
            payload = {
                "model": self.model if self.model else "default",
                "messages": formatted_messages,
                "temperature": 0.7,
                "max_tokens": 1000,
                "stream": stream,
            }

            async with aiohttp.ClientSession() as session:
                url = f"{self.lmstudio_url}/v1/chat/completions"

                async with session.post(
                    url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        log.error(f"LMStudio API error: {response.status} - {error_text}")
                        yield "Sorry, I'm having trouble connecting to the AI service right now."
                        return

                    if stream:
                        # Handle streaming response
                        async for line in response.content:
                            line = line.decode("utf-8").strip()
                            if line.startswith("data: "):
                                data = line[6:]  # Remove 'data: ' prefix
                                if data == "[DONE]":
                                    break
                                try:
                                    chunk_data = json.loads(data)
                                    delta = chunk_data.get("choices", [{}])[0].get("delta", {})
                                    if "content" in delta:
                                        chunk_content = delta["content"]
                                        output_text += chunk_content
                                        yield chunk_content
                                except json.JSONDecodeError:
                                    continue

                        # Track usage after streaming is complete
                        if input_text or output_text:
                            self._track_usage(input_text.strip(), output_text)
                    else:
                        # Handle non-streaming response
                        result = await response.json()
                        content = (
                            result.get("choices", [{}])[0].get("message", {}).get("content", "")
                        )
                        if content:
                            output_text = content
                            self._track_usage(input_text.strip(), output_text)
                            yield content
                        else:
                            error_msg = "I couldn't generate a response. Please try again."
                            self._track_usage(input_text.strip(), error_msg)
                            yield error_msg

        except asyncio.TimeoutError:
            log.error("LMStudio API timeout")
            yield "The AI service is taking too long to respond. Please try again."
        except Exception as e:
            log.error(f"LMStudio API error: {e}")
            yield f"Error communicating with AI service: {str(e)}"

    def get_cost_stats(self, days: int = 30) -> Dict[str, Any]:
        """Get AI usage cost statistics."""
        log.info(f"get_cost_stats called with provider={self.provider}, days={days}")

        # Check if Claude usage data is available (regardless of current provider)
        # This allows us to show Claude costs even when using a different provider
        try:
            # Try to get Claude usage data (now sync)
            claude_stats = self.claude_usage_tracker.get_usage_stats(days)

            log.info(
                f"Claude stats retrieved: available={claude_stats.get('available')}, requests={claude_stats.get('requests')}"
            )
            if claude_stats.get("available", False) and claude_stats.get("requests", 0) > 0:
                claude_stats["provider"] = "claude"
                claude_stats["current_provider"] = self.provider
                return claude_stats
        except Exception as e:
            log.error(f"Failed to get Claude usage data: {e}", exc_info=True)

        # Fall back to SQLite database if provider is claude
        if self.provider == "claude":
            # Use Claude CLI database for accurate costs
            stats = self.claude_cost_tracker.get_usage_stats(days)
            stats["provider"] = "claude"
            return stats
        else:
            # For other providers, use session tracking and estimates
            # Note: These are estimates, actual costs may vary
            provider_costs = {
                "lmstudio": {"input": 0.0, "output": 0.0},  # Local, no cost
                "mock": {"input": 0.0, "output": 0.0},  # Mock, no cost
                "anthropic": {"input": 0.003, "output": 0.015},  # Example rates per 1K tokens
                "gemini": {"input": 0.000125, "output": 0.000375},  # Example Gemini rates
            }

            rates = provider_costs.get(self.provider, {"input": 0.0, "output": 0.0})

            estimated_cost = (self.session_usage["input_tokens"] / 1000) * rates["input"] + (
                self.session_usage["output_tokens"] / 1000
            ) * rates["output"]

            return {
                "total_cost": round(estimated_cost, 4),
                "total_tokens": self.session_usage["input_tokens"]
                + self.session_usage["output_tokens"],
                "input_tokens": self.session_usage["input_tokens"],
                "output_tokens": self.session_usage["output_tokens"],
                "requests": self.session_usage["requests"],
                "period_days": days,
                "available": True,
                "provider": self.provider,
                "note": "Estimated costs - actual costs may vary",
                "session_only": True,
            }

    def get_daily_breakdown(self, days: int = 7) -> List[Dict[str, Any]]:
        """Get daily cost breakdown."""
        # Check if Claude usage data is available (regardless of current provider)
        try:
            claude_daily = self.claude_usage_tracker.get_daily_breakdown(days)
            if claude_daily:
                return claude_daily
        except Exception as e:
            log.debug(f"Failed to get Claude daily breakdown: {e}")

        # Fall back to SQLite
        if self.provider == "claude":
            return self.claude_cost_tracker.get_daily_breakdown(days)
        else:
            # For other providers, return empty or estimated session data
            return []

    def get_model_breakdown(self, days: int = 30) -> List[Dict[str, Any]]:
        """Get cost breakdown by model."""
        # Check if Claude usage data is available (regardless of current provider)
        try:
            claude_models = self.claude_usage_tracker.get_model_breakdown(days)
            if claude_models:
                return claude_models
        except Exception as e:
            log.debug(f"Failed to get Claude model breakdown: {e}")

        # Fall back to SQLite
        if self.provider == "claude":
            return self.claude_cost_tracker.get_model_breakdown(days)
        else:
            if self.session_usage["requests"] > 0:
                cost_stats = self.get_cost_stats(days)
                return [
                    {
                        "model": self.model,
                        "input_tokens": self.session_usage["input_tokens"],
                        "output_tokens": self.session_usage["output_tokens"],
                        "total_tokens": self.session_usage["input_tokens"]
                        + self.session_usage["output_tokens"],
                        "requests": self.session_usage["requests"],
                        "cost": cost_stats["total_cost"],
                    }
                ]
            return []

    def _estimate_token_count(self, text: str) -> int:
        """Rough estimation of token count (4 chars ≈ 1 token)."""
        return max(1, len(text) // 4)

    def _track_usage(self, input_text: str, output_text: str):
        """Track usage for non-Claude providers."""
        if self.provider != "claude":
            input_tokens = self._estimate_token_count(input_text)
            output_tokens = self._estimate_token_count(output_text)

            self.session_usage["input_tokens"] += input_tokens
            self.session_usage["output_tokens"] += output_tokens
            self.session_usage["requests"] += 1
