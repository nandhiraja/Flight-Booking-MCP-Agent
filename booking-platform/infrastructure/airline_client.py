"""
infrastructure/airline_client.py

Persistent async MCP client for the Mock Airline Vendor.

Maintains a single subprocess + session for the lifetime of the
booking platform.  Each call reuses the same connection —
vendor's in-memory state is preserved across calls.
"""

import sys
import json
import logging
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

import config

logger = logging.getLogger(__name__)


class AirlineVendorClient:
    """Long-lived MCP client for the Mock Airline Vendor."""

    def __init__(self) -> None:
        self._session: ClientSession | None = None
        self._stack: AsyncExitStack | None = None

    # ── Lifecycle ─────────────────────────────────────────────────

    async def connect(self) -> None:
        """Start vendor subprocess and open a persistent MCP session."""
        self._stack = AsyncExitStack()
        server_params = StdioServerParameters(
            command=sys.executable,
            args=[str(config.AIRLINE_VENDOR_SERVER)],
        )
        read, write = await self._stack.enter_async_context(
            stdio_client(server_params)
        )
        self._session = await self._stack.enter_async_context(
            ClientSession(read, write)
        )
        await self._session.initialize()
        logger.info("AirlineVendorClient connected.")

    async def close(self) -> None:
        if self._stack:
            await self._stack.aclose()
            logger.info("AirlineVendorClient disconnected.")

    # ── Internal ──────────────────────────────────────────────────

    async def _call(self, tool: str, args: dict) -> dict:
        if self._session is None:
            raise RuntimeError("AirlineVendorClient not connected. Call connect() first.")
        result = await self._session.call_tool(tool, args)
        if result.content:
            return json.loads(result.content[0].text)
        return {}

    # ── Public API ────────────────────────────────────────────────

    async def search_flights(self, origin: str, destination: str, date: str) -> dict:
        return await self._call("search_flights", {
            "origin": origin,
            "destination": destination,
            "date": date,
        })

    async def reserve_seats(
        self, flight_id: str, seat_count: int, client_reference: str
    ) -> dict:
        return await self._call("reserve_seats", {
            "flight_id": flight_id,
            "seat_count": seat_count,
            "client_reference": client_reference,
        })

    async def confirm_reservation(self, reservation_id: str) -> dict:
        return await self._call("confirm_reservation", {
            "reservation_id": reservation_id,
        })

    async def cancel_reservation(self, reservation_id: str) -> dict:
        return await self._call("cancel_reservation", {
            "reservation_id": reservation_id,
        })

    async def get_reservation_status(self, reservation_id: str) -> dict:
        return await self._call("get_reservation_status", {
            "reservation_id": reservation_id,
        })


# ── Singleton ─────────────────────────────────────────────────────
airline_client = AirlineVendorClient()
