"""Stripe Meter Event reporter for Work-with-AI token usage.

Reports token consumption to Stripe's Billing Meter API for
graduated usage-based pricing.

Usage:
    meter = StripeMeter()

    # After each LLM call
    await meter.report(
        customer_id="cus_xxx",
        tokens=response.usage.total_tokens,
    )

    # Or as a LiteLLM callback
    litellm.callbacks = [meter.litellm_callback()]

Configure via environment variables:
    STRIPE_SECRET_KEY       — Stripe API key (required)
    STRIPE_METER_EVENT_NAME — Meter event name (default: work_with_ai_tokens)
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

log = logging.getLogger("aetherterm.stripe_meter")

STRIPE_METER_EVENT_NAME = os.environ.get(
    "STRIPE_METER_EVENT_NAME", "work_with_ai_tokens"
)


class StripeMeter:
    """Reports token usage to Stripe Billing Meter."""

    def __init__(
        self,
        api_key: str = "",
        event_name: str = STRIPE_METER_EVENT_NAME,
    ) -> None:
        self._api_key = api_key or os.environ.get("STRIPE_SECRET_KEY", "")
        self._event_name = event_name
        self._stripe: Any = None

    def _get_stripe(self) -> Any:
        if self._stripe is None:
            import stripe

            stripe.api_key = self._api_key
            self._stripe = stripe
        return self._stripe

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    def report_sync(self, customer_id: str, tokens: int) -> bool:
        """Report token usage synchronously.

        Args:
            customer_id: Stripe Customer ID (cus_xxx)
            tokens: Total tokens consumed

        Returns True on success.
        """
        if not self.enabled or tokens <= 0:
            return False

        # Convert to 1K token units (billing unit)
        units = max(1, tokens // 1000)

        try:
            stripe = self._get_stripe()
            stripe.billing.MeterEvent.create(
                event_name=self._event_name,
                payload={
                    "stripe_customer_id": customer_id,
                    "value": str(units),
                },
            )
            log.debug(
                "Reported %d tokens (%d units) for %s",
                tokens, units, customer_id,
            )
            return True
        except Exception as e:
            log.error("Stripe meter event failed: %s", e)
            return False

    async def report(self, customer_id: str, tokens: int) -> bool:
        """Report token usage (async wrapper)."""
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self.report_sync, customer_id, tokens
        )

    def litellm_callback(self) -> "StripeMeterLiteLLMCallback":
        """Create a LiteLLM-compatible callback instance."""
        return StripeMeterLiteLLMCallback(self)


class StripeMeterLiteLLMCallback:
    """LiteLLM Custom Callback that reports token usage to Stripe Meter.

    Usage:
        meter = StripeMeter()
        litellm.callbacks = [meter.litellm_callback()]

    The callback reads `stripe_customer_id` from the LiteLLM metadata:
        response = await litellm.acompletion(
            model="claude-sonnet-4-6",
            messages=[...],
            metadata={"stripe_customer_id": "cus_xxx"},
        )
    """

    def __init__(self, meter: StripeMeter) -> None:
        self._meter = meter

    def log_success_event(self, kwargs: dict, response_obj: Any, start_time: float, end_time: float) -> None:
        self._handle(kwargs, response_obj)

    async def async_log_success_event(self, kwargs: dict, response_obj: Any, start_time: float, end_time: float) -> None:
        self._handle(kwargs, response_obj)

    def _handle(self, kwargs: dict, response_obj: Any) -> None:
        metadata = kwargs.get("metadata") or kwargs.get("litellm_params", {}).get("metadata", {})
        customer_id = metadata.get("stripe_customer_id", "")
        if not customer_id:
            return

        usage = getattr(response_obj, "usage", None)
        if usage is None:
            return

        total_tokens = getattr(usage, "total_tokens", 0)
        if total_tokens > 0:
            self._meter.report_sync(customer_id, total_tokens)
