"""
agent/agent_orchestrator.py

Core agent loop using Groq's tool-calling API.

Features:
  - Multi-turn conversation with full message history
  - Tool execution mapped to application layer functions
  - Human-in-the-loop enforcement for 'initiate_payment'
  - Informative system prompt with user context
"""

import json
import logging
import asyncio
from typing import Callable, Awaitable

from agent.tool_definitions import TOOLS, HUMAN_CONFIRMATION_REQUIRED
from agent.llm_client import chat_completion

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────
# System Prompt
# ──────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """\
You are AirBook Assistant — an AI flight booking agent for the AirBook Platform.

## Strict Rules (follow these exactly)

1. NEVER call search_flights without knowing BOTH origin AND destination from the user.
   - If the user asks to "list flights" or "show flights" without specifying a route,
     call get_available_routes first to show available routes, then ask which route they want.

2. NEVER call search_flights without a date.
   - If the user hasn't given a date, use today's date: {today}.

3. Call tools in this EXACT sequence for a booking:
   search_flights → create_booking → reserve_flight → [confirm payment with user] → initiate_payment → simulate_payment_outcome

4. NEVER call initiate_payment without explicit user confirmation ("yes"/"confirm").

5. After initiate_payment succeeds, ALWAYS call simulate_payment_outcome with result=SUCCESS
   in the same turn (unless user says to fail it).

6. Be concise. One sentence per action.

## Available Users
| ID      | Name  | Auto-Pay | Card       |
|---------|-------|----------|------------|
| USR-001 | Alice | Yes      | **** 4242  |
| USR-002 | Bob   | No       | None saved |
""".format(today=__import__('datetime').date.today().isoformat())


# ──────────────────────────────────────────────────────────────────
# Tool Executor
# ──────────────────────────────────────────────────────────────────

async def _execute_tool(tool_name: str, args: dict) -> dict:
    """Route a tool call to the correct application layer function."""

    if tool_name == "get_available_routes":
        # Returns static route table — no MCP or API calls needed
        return {
            "routes": [
                {"flight_id": "AI-101",  "origin": "DEL", "destination": "BOM", "price": "4500 INR", "seats": 10},
                {"flight_id": "AI-202",  "origin": "BOM", "destination": "DEL", "price": "4200 INR", "seats": 10},
                {"flight_id": "6E-305",  "origin": "DEL", "destination": "BLR", "price": "5200 INR", "seats": 10},
                {"flight_id": "SG-410",  "origin": "BLR", "destination": "HYD", "price": "2800 INR", "seats": 10},
                {"flight_id": "UK-512",  "origin": "HYD", "destination": "MAA", "price": "3100 INR", "seats": 10},
            ],
            "note": "Use search_flights(origin, destination, date) to get live availability for a specific route.",
        }

    elif tool_name == "search_flights":
        from application.flight_orchestrator import search_flights
        return await search_flights(**args)

    elif tool_name == "create_booking":
        from application.booking_service import create_booking
        return create_booking(**args)

    elif tool_name == "reserve_flight":
        from application.flight_orchestrator import reserve_flight
        return await reserve_flight(**args)

    elif tool_name == "get_saved_payment_methods":
        from infrastructure.repository import get_user_payment_methods
        methods = get_user_payment_methods(args["user_id"])
        return {"payment_methods": [m.to_dict() for m in methods]}

    elif tool_name == "initiate_payment":
        from application.payment_orchestrator import initiate_payment
        return await initiate_payment(**args)

    elif tool_name == "get_booking_status":
        from application.booking_service import get_booking
        return get_booking(**args)

    elif tool_name == "cancel_booking":
        from application.booking_service import cancel_booking
        from application.flight_orchestrator import reserve_flight
        from infrastructure.airline_client import airline_client
        from infrastructure.repository import get_lock, bookings
        # Cancel vendor reservation first (best-effort)
        with get_lock():
            booking = bookings.get(args["booking_id"])
        if booking and booking.reservation_id:
            await airline_client.cancel_reservation(booking.reservation_id)
        from application.booking_service import cancel_booking
        return cancel_booking(**args)

    elif tool_name == "list_user_bookings":
        from application.booking_service import list_user_bookings
        return {"bookings": list_user_bookings(**args)}

    elif tool_name == "reconcile_payment":
        from application.payment_orchestrator import reconcile_payment
        return await reconcile_payment(**args)

    elif tool_name == "simulate_payment_outcome":
        from infrastructure.payment_client import payment_client
        return await payment_client.simulate_payment_result(
            args["payment_id"], args["result"]
        )

    else:
        return {"error": "UNKNOWN_TOOL", "tool": tool_name}


# ──────────────────────────────────────────────────────────────────
# Agent Orchestrator
# ──────────────────────────────────────────────────────────────────

class AgentOrchestrator:
    """
    Manages the Groq tool-calling loop with human-in-the-loop enforcement.

    Args:
        ask_user: async callable that displays a prompt and returns user input string.
    """

    def __init__(self, ask_user: Callable[[str], Awaitable[str]]) -> None:
        self._ask_user = ask_user
        self._messages: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]

    async def run_turn(self, user_message: str, max_iterations: int = 6) -> str:
        """
        Process one user turn and return the final assistant text response.

        Runs the Groq tool-calling loop until the LLM produces a text reply
        or max_iterations is reached (prevents runaway API calls).
        """
        self._messages.append({"role": "user", "content": user_message})
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            response = await chat_completion(self._messages, TOOLS)
            msg = response.choices[0].message

            if msg.tool_calls:
                # Append assistant turn with tool calls
                self._messages.append({
                    "role": "assistant",
                    "content": msg.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in msg.tool_calls
                    ],
                })

                # Execute each tool call
                for tc in msg.tool_calls:
                    tool_name = tc.function.name
                    try:
                        args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        args = {}

                    # ── Human-in-the-loop guard ───────────────────
                    if tool_name in HUMAN_CONFIRMATION_REQUIRED:
                        booking_id = args.get("booking_id", "?")
                        # Fetch booking info for display
                        try:
                            from application.booking_service import get_booking
                            booking_info = get_booking(booking_id)
                            amount = booking_info.get("total_amount", "?")
                            currency = booking_info.get("currency", "")
                            pm_token = args.get("payment_token", "")
                            card_info = f"card token {pm_token}" if pm_token else "redirect payment link"
                            prompt = (
                                f"\n⚠️  PAYMENT CONFIRMATION REQUIRED\n"
                                f"   Booking : {booking_id}\n"
                                f"   Amount  : {amount} {currency}\n"
                                f"   Method  : {card_info}\n"
                                f"\n   Type 'yes' to confirm or anything else to cancel: "
                            )
                        except Exception:
                            prompt = f"\n⚠️  Confirm payment for booking {booking_id}? (yes/no): "

                        user_reply = await self._ask_user(prompt)

                        if user_reply.strip().lower() not in ("yes", "y"):
                            tool_result = {
                                "error": "USER_DECLINED",
                                "message": "User declined the payment. No charge made.",
                            }
                            logger.info("User declined payment for booking %s.", booking_id)
                        else:
                            tool_result = await _execute_tool(tool_name, args)
                    else:
                        tool_result = await _execute_tool(tool_name, args)

                    logger.debug("Tool %s → %s", tool_name, tool_result)

                    self._messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(tool_result, default=str),
                    })

            else:
                # LLM gave us a text response — end of turn
                final_text = msg.content or ""
                self._messages.append({"role": "assistant", "content": final_text})
                return final_text

        # Safety net: max iterations reached
        warning = "[Reached maximum tool calls for this turn. Please rephrase your request.]"
        self._messages.append({"role": "assistant", "content": warning})
        return warning

    def clear_history(self) -> None:
        """Reset conversation (keep system prompt)."""
        self._messages = [self._messages[0]]
