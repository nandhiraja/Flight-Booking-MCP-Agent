"""
infrastructure/payment_client.py

Persistent async MCP client for the Mock Payment Gateway.
"""

import sys
import json
import logging
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

import config

logger = logging.getLogger(__name__)


class PaymentGatewayClient:
    """Long-lived MCP client for the Mock Payment Gateway."""

    def __init__(self) -> None:
        self._session: ClientSession | None = None
        self._stack: AsyncExitStack | None = None

    async def connect(self) -> None:
        self._stack = AsyncExitStack()
        server_params = StdioServerParameters(
            command=sys.executable,
            args=[str(config.PAYMENT_GATEWAY_SERVER)],
        )
        read, write = await self._stack.enter_async_context(
            stdio_client(server_params)
        )
        self._session = await self._stack.enter_async_context(
            ClientSession(read, write)
        )
        await self._session.initialize()
        logger.info("PaymentGatewayClient connected.")

    async def close(self) -> None:
        if self._stack:
            await self._stack.aclose()
            logger.info("PaymentGatewayClient disconnected.")

    async def _call(self, tool: str, args: dict) -> dict:
        if self._session is None:
            raise RuntimeError("PaymentGatewayClient not connected. Call connect() first.")
        result = await self._session.call_tool(tool, args)
        if result.content:
            return json.loads(result.content[0].text)
        return {}

    async def create_payment(
        self,
        merchant_reference: str,
        amount: str,
        currency: str,
        callback_url: str,
    ) -> dict:
        return await self._call("create_payment", {
            "merchant_reference": merchant_reference,
            "amount": amount,
            "currency": currency,
            "callback_url": callback_url,
        })

    async def simulate_payment_result(self, payment_id: str, result: str) -> dict:
        return await self._call("simulate_payment_result", {
            "payment_id": payment_id,
            "result": result,
        })

    async def get_payment_status(self, payment_id: str) -> dict:
        return await self._call("get_payment_status", {
            "payment_id": payment_id,
        })


# ── Singleton ─────────────────────────────────────────────────────
payment_client = PaymentGatewayClient()
