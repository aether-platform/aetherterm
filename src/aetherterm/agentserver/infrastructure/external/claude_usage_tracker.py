"""
Claude Usage Tracker - ccusage-inspired local JSONL parser with pandas

Reads Claude CLI usage data from local JSONL files for real-time cost tracking.
Based on https://github.com/ryoppippi/ccusage patterns.
"""

import asyncio
import json
import logging
import os
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("aetherterm.infrastructure.claude_usage")

# Claude model pricing (per million tokens)
CLAUDE_PRICING = {
    "claude-3-opus-20240229": {"input": 15.0, "output": 75.0},
    "claude-3-sonnet-20240229": {"input": 3.0, "output": 15.0},
    "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
    "claude-3-5-sonnet-20241022": {"input": 3.0, "output": 15.0},
    "claude-3-5-haiku-20241022": {"input": 1.0, "output": 5.0},
    # Default fallback pricing
    "default": {"input": 3.0, "output": 15.0},
}


class ClaudeUsageTracker:
    """Enhanced Claude usage tracker with ccusage-inspired features using pandas."""

    def __init__(self):
        self.claude_dir = Path.home() / ".claude"
        self.projects_dir = self.claude_dir / "projects"
        self._cache_df = None
        self._cache_timestamp = None
        self._cache_duration = 60  # Cache for 60 seconds

    def _make_tz_aware(self, dt: datetime, df: pd.DataFrame) -> pd.Timestamp:
        """Convert datetime to timezone-aware if DataFrame uses timezone-aware timestamps."""
        if not df.empty and "timestamp" in df.columns and df["timestamp"].dt.tz is not None:
            return pd.Timestamp(dt).tz_localize("UTC")
        return pd.Timestamp(dt)

    def _find_jsonl_files(self) -> List[Path]:
        """Find all JSONL files in Claude projects directory."""
        if not self.projects_dir.exists():
            return []

        jsonl_files = []
        for project_dir in self.projects_dir.iterdir():
            if project_dir.is_dir():
                jsonl_files.extend(project_dir.glob("*.jsonl"))
        return sorted(jsonl_files, key=lambda f: f.stat().st_mtime, reverse=True)

    def _load_jsonl_to_df(self, since_date: datetime) -> pd.DataFrame:
        """Load JSONL files into a pandas DataFrame."""
        jsonl_files = self._find_jsonl_files()
        if not jsonl_files:
            return pd.DataFrame()

        all_records = []

        for file_path in jsonl_files:
            try:
                with open(file_path, "r") as f:
                    for line in f:
                        try:
                            data = json.loads(line.strip())
                            # Check for usage in message object (Claude CLI format)
                            message = data.get("message", {})
                            usage = message.get("usage")

                            if usage:
                                record = {
                                    "timestamp": pd.to_datetime(
                                        data.get("timestamp", datetime.now().isoformat())
                                    ),
                                    "model": message.get("model", "unknown"),
                                    "input_tokens": usage.get("input_tokens", 0),
                                    "output_tokens": usage.get("output_tokens", 0),
                                    "cache_creation_tokens": usage.get(
                                        "cache_creation_input_tokens", 0
                                    ),
                                    "cache_read_tokens": usage.get("cache_read_input_tokens", 0),
                                    "project": file_path.parent.name,
                                    "conversation_id": data.get("sessionId"),
                                    "message_id": message.get("id"),
                                }
                                all_records.append(record)
                        except (json.JSONDecodeError, KeyError) as e:
                            log.debug(f"Failed to parse JSONL line: {e}")
            except Exception as e:
                log.error(f"Error reading {file_path}: {e}")

        if not all_records:
            return pd.DataFrame()

        df = pd.DataFrame(all_records)
        # Convert since_date to timezone-aware for comparison
        since_date_tz = self._make_tz_aware(since_date, df)
        df = df[df["timestamp"] >= since_date_tz]

        # Calculate costs
        df["cost"] = df.apply(self._calculate_cost_row, axis=1)

        return df

    def _calculate_cost_row(self, row) -> float:
        """Calculate cost for a DataFrame row."""
        model = row["model"]
        pricing = CLAUDE_PRICING.get(model, CLAUDE_PRICING["default"])

        # Cache creation costs same as input, cache read is 10% of input cost
        input_cost = (
            (row["input_tokens"] + row["cache_creation_tokens"]) * pricing["input"]
        ) / 1_000_000
        cache_read_cost = (row["cache_read_tokens"] * pricing["input"] * 0.1) / 1_000_000
        output_cost = (row["output_tokens"] * pricing["output"]) / 1_000_000

        return input_cost + cache_read_cost + output_cost

    def get_usage_stats(self, days: int = 30) -> Dict[str, Any]:
        """Get usage statistics with caching."""
        # Check cache
        now = datetime.now()
        if (
            self._cache_timestamp
            and (now - self._cache_timestamp).seconds < self._cache_duration
            and self._cache_df is not None
        ):
            df = self._cache_df
        else:
            # Load fresh data
            since_date = now - timedelta(days=days)
            df = self._load_jsonl_to_df(since_date)
            self._cache_df = df
            self._cache_timestamp = now

        if df.empty:
            return {
                "available": False,
                "message": "No Claude usage data found",
                "total_cost": 0.0,
                "requests": 0,
            }

        # Filter by days
        since_date = now - timedelta(days=days)
        # Convert to timezone-aware for comparison
        since_date_tz = self._make_tz_aware(since_date, df)
        df_filtered = df[df["timestamp"] >= since_date_tz]

        # Calculate aggregates
        total_cost = df_filtered["cost"].sum()
        total_input = df_filtered["input_tokens"].sum()
        total_output = df_filtered["output_tokens"].sum()
        total_tokens = total_input + total_output
        requests = len(df_filtered)

        result = {
            "available": True,
            "total_cost": round(float(total_cost), 4),
            "total_tokens": int(total_tokens),
            "input_tokens": int(total_input),
            "output_tokens": int(total_output),
            "requests": requests,
            "period_days": days,
            "average_cost_per_request": round(float(total_cost / max(requests, 1)), 4),
            "cost_per_1k_tokens": round(float(total_cost / max(total_tokens / 1000, 0.001)), 4),
        }

        return result

    def get_daily_breakdown(self, days: int = 7) -> List[Dict[str, Any]]:
        """Get daily cost breakdown using pandas."""
        now = datetime.now()
        since_date = now - timedelta(days=days)

        # Use cached data if available
        if self._cache_df is not None and self._cache_timestamp:
            df = self._cache_df
        else:
            df = self._load_jsonl_to_df(since_date)

        if df.empty:
            return []

        # Filter and group by date
        # Convert to timezone-aware for comparison
        since_date_tz = self._make_tz_aware(since_date, df)
        df_filtered = df[df["timestamp"] >= since_date_tz].copy()
        df_filtered["date"] = df_filtered["timestamp"].dt.date

        daily_stats = (
            df_filtered.groupby("date")
            .agg(
                {
                    "cost": "sum",
                    "message_id": "count",
                    "input_tokens": "sum",
                    "output_tokens": "sum",
                    "cache_creation_tokens": "sum",
                    "cache_read_tokens": "sum",
                }
            )
            .reset_index()
        )

        daily_stats.columns = [
            "date",
            "cost",
            "requests",
            "input_tokens",
            "output_tokens",
            "cache_creation_tokens",
            "cache_read_tokens",
        ]
        daily_stats["tokens"] = daily_stats["input_tokens"] + daily_stats["output_tokens"]

        # Convert to list of dicts
        result = []
        for _, row in daily_stats.iterrows():
            result.append(
                {
                    "date": row["date"].isoformat(),
                    "cost": round(float(row["cost"]), 4),
                    "requests": int(row["requests"]),
                    "tokens": int(row["tokens"]),
                    "input_tokens": int(row["input_tokens"]),
                    "output_tokens": int(row["output_tokens"]),
                    "cache_creation_tokens": int(row["cache_creation_tokens"]),
                    "cache_read_tokens": int(row["cache_read_tokens"]),
                }
            )

        return sorted(result, key=lambda x: x["date"], reverse=True)

    def get_hourly_breakdown(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get hourly cost breakdown using pandas."""
        now = datetime.now()
        since_date = now - timedelta(hours=hours)

        # Load recent data
        df = self._load_jsonl_to_df(since_date)

        if df.empty:
            return []

        # Filter and group by hour
        since_date_tz = self._make_tz_aware(since_date, df)
        df_filtered = df[df["timestamp"] >= since_date_tz].copy()
        df_filtered["hour"] = df_filtered["timestamp"].dt.floor("H")

        hourly_stats = (
            df_filtered.groupby("hour")
            .agg(
                {
                    "cost": "sum",
                    "message_id": "count",
                    "input_tokens": "sum",
                    "output_tokens": "sum",
                }
            )
            .reset_index()
        )

        hourly_stats.columns = ["hour", "cost", "requests", "input_tokens", "output_tokens"]

        # Convert to list of dicts
        result = []
        for _, row in hourly_stats.iterrows():
            result.append(
                {
                    "hour": row["hour"].isoformat(),
                    "cost": round(float(row["cost"]), 4),
                    "requests": int(row["requests"]),
                    "input_tokens": int(row["input_tokens"]),
                    "output_tokens": int(row["output_tokens"]),
                }
            )

        return sorted(result, key=lambda x: x["hour"])

    def get_monthly_breakdown(self, months: int = 12) -> List[Dict[str, Any]]:
        """Get monthly cost breakdown using pandas."""
        now = datetime.now()
        since_date = now - timedelta(days=months * 30)

        # Load data
        df = self._load_jsonl_to_df(since_date)

        if df.empty:
            return []

        # Filter and group by month
        since_date_tz = self._make_tz_aware(since_date, df)
        df_filtered = df[df["timestamp"] >= since_date_tz].copy()
        df_filtered["month"] = df_filtered["timestamp"].dt.to_period("M")

        monthly_stats = (
            df_filtered.groupby("month")
            .agg(
                {
                    "cost": "sum",
                    "message_id": "count",
                    "input_tokens": "sum",
                    "output_tokens": "sum",
                }
            )
            .reset_index()
        )

        # Convert to list of dicts
        result = []
        for _, row in monthly_stats.iterrows():
            result.append(
                {
                    "month": str(row["month"]),
                    "cost": round(float(row["cost"]), 4),
                    "requests": int(row["message_id"]),
                    "input_tokens": int(row["input_tokens"]),
                    "output_tokens": int(row["output_tokens"]),
                }
            )

        return sorted(result, key=lambda x: x["month"], reverse=True)

    def get_session_blocks(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get 5-hour billing blocks using pandas."""
        now = datetime.now()
        since_date = now - timedelta(hours=hours)

        # Use cached data if available
        if self._cache_df is not None and self._cache_timestamp:
            df = self._cache_df
        else:
            df = self._load_jsonl_to_df(since_date)

        if df.empty:
            return []

        # Filter and create 5-hour blocks
        since_date_tz = self._make_tz_aware(since_date, df)
        df_filtered = df[df["timestamp"] >= since_date_tz].copy()
        df_filtered["block"] = df_filtered["timestamp"].dt.floor("5H")

        block_stats = (
            df_filtered.groupby("block")
            .agg({"cost": "sum", "message_id": "count", "timestamp": ["min", "max"]})
            .reset_index()
        )

        # Flatten column names
        block_stats.columns = ["block_start", "cost", "requests", "start_time", "end_time"]

        # Convert to list of dicts
        result = []
        for _, row in block_stats.iterrows():
            result.append(
                {
                    "block_start": row["block_start"].isoformat(),
                    "cost": round(float(row["cost"]), 4),
                    "requests": int(row["requests"]),
                    "duration_hours": 5,
                    "active": True,
                }
            )

        return sorted(result, key=lambda x: x["block_start"], reverse=True)

    def get_burn_rate(self) -> Dict[str, Any]:
        """Calculate current burn rate and projections using pandas."""
        now = datetime.now()
        one_hour_ago = now - timedelta(hours=1)

        # Load recent data
        df = self._load_jsonl_to_df(one_hour_ago)

        if df.empty:
            return {
                "available": True,
                "hourly_rate": 0.0,
                "daily_projection": 0.0,
                "monthly_projection": 0.0,
                "last_update": now.isoformat(),
            }

        # Calculate hourly cost
        hourly_cost = df["cost"].sum()

        # Calculate rates for different time windows
        time_windows = []
        for hours, label in [(1, "1h"), (6, "6h"), (24, "24h")]:
            window_start = now - timedelta(hours=hours)
            window_start_tz = self._make_tz_aware(window_start, df)
            window_df = df[df["timestamp"] >= window_start_tz]
            if not window_df.empty:
                window_cost = window_df["cost"].sum()
                window_rate = window_cost / hours
                time_windows.append(
                    {
                        "window": label,
                        "cost": round(float(window_cost), 4),
                        "rate_per_hour": round(float(window_rate), 4),
                    }
                )

        return {
            "available": True,
            "hourly_rate": round(float(hourly_cost), 4),
            "daily_projection": round(float(hourly_cost * 24), 2),
            "monthly_projection": round(float(hourly_cost * 24 * 30), 2),
            "time_windows": time_windows,
            "last_update": now.isoformat(),
        }

    def get_model_breakdown(self, days: int = 30) -> List[Dict[str, Any]]:
        """Get cost breakdown by model using pandas."""
        now = datetime.now()
        since_date = now - timedelta(days=days)

        # Use cached data if available
        if self._cache_df is not None and self._cache_timestamp:
            df = self._cache_df
        else:
            df = self._load_jsonl_to_df(since_date)

        if df.empty:
            return []

        # Filter and group by model
        since_date_tz = self._make_tz_aware(since_date, df)
        df_filtered = df[df["timestamp"] >= since_date_tz]

        model_stats = (
            df_filtered.groupby("model")
            .agg(
                {
                    "cost": "sum",
                    "message_id": "count",
                    "input_tokens": "sum",
                    "output_tokens": "sum",
                }
            )
            .reset_index()
        )

        total_cost = model_stats["cost"].sum()

        # Convert to list of dicts
        result = []
        for _, row in model_stats.iterrows():
            tokens = row["input_tokens"] + row["output_tokens"]
            result.append(
                {
                    "model": row["model"],
                    "cost": round(float(row["cost"]), 4),
                    "requests": int(row["message_id"]),
                    "tokens": int(tokens),
                    "percentage": round(float(row["cost"] / total_cost * 100), 1)
                    if total_cost > 0
                    else 0,
                }
            )

        return sorted(result, key=lambda x: x["cost"], reverse=True)

    def export_data(self, days: int = 30, format: str = "json") -> Dict[str, Any]:
        """Export usage data in different formats."""
        now = datetime.now()
        since_date = now - timedelta(days=days)

        # Load data
        df = self._load_jsonl_to_df(since_date)

        if df.empty:
            return {"error": "No data to export"}

        since_date_tz = self._make_tz_aware(since_date, df)
        df_filtered = df[df["timestamp"] >= since_date_tz]

        if format == "json":
            return {
                "data": df_filtered.to_dict(orient="records"),
                "summary": self.get_usage_stats(days),
            }
        elif format == "csv":
            csv_data = df_filtered.to_csv(index=False)
            return {"csv": csv_data}
        else:
            return {"error": f"Unsupported format: {format}"}
