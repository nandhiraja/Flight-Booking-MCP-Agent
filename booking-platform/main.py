"""
main.py  –  Booking Platform CLI Entry Point

Startup sequence:
  1. Connect persistent MCP clients (airline + payment vendors)
  2. Register the main asyncio loop with webhook + expiry job
  3. Start webhook HTTP server (background thread)
  4. Start booking expiry job (background thread)
  5. Run interactive CLI loop
"""

import sys
import os
import asyncio
import logging

# Ensure booking-platform root is on the path
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)],
)
logger = logging.getLogger("booking.main")


BANNER = """
╔══════════════════════════════════════════════════════╗
║           AirBook – Flight Booking Agent             ║
║          Powered by Groq LLaMA-3.3-70b               ║
╠══════════════════════════════════════════════════════╣
║  Users available:                                    ║
║    USR-001  Alice  (auto-pay, card **** 4242)        ║
║    USR-002  Bob    (manual pay, no saved card)       ║
╠══════════════════════════════════════════════════════╣
║  Type your request below. Commands:                  ║
║    /clear   – Clear conversation history             ║
║    /quit    – Exit                                   ║
╚══════════════════════════════════════════════════════╝
"""


async def _ask_user(prompt: str) -> str:
    """Async-friendly stdin reader for the human-in-the-loop gate."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: input(prompt))


async def main() -> None:
    logger.info("=== AirBook Booking Platform – Starting Up ===")

    # 1. Connect MCP clients
    from infrastructure.airline_client import airline_client
    from infrastructure.payment_client import payment_client

    logger.info("Connecting to Airline Vendor MCP …")
    await airline_client.connect()

    logger.info("Connecting to Payment Gateway MCP …")
    await payment_client.connect()

    # 2. Share the main event loop with background threads
    loop = asyncio.get_event_loop()
    from webhooks.payment_webhook_handler import set_event_loop as wh_set_loop, start_webhook_server
    from jobs.booking_expiry_job import set_event_loop as job_set_loop, start_expiry_job

    wh_set_loop(loop)
    job_set_loop(loop)

    # 3. Start webhook server
    start_webhook_server()
    logger.info("Webhook server started.")

    # 4. Start expiry job
    stop_expiry = start_expiry_job()
    logger.info("Booking expiry job started.")

    # 5. Create the agent
    from agent.agent_orchestrator import AgentOrchestrator
    agent = AgentOrchestrator(ask_user=_ask_user)

    print(BANNER)

    try:
        while True:
            try:
                user_input = await _ask_user("\nYou: ")
            except (EOFError, KeyboardInterrupt):
                break

            if not user_input.strip():
                continue

            if user_input.strip().lower() == "/quit":
                print("Goodbye! ✈️")
                break

            if user_input.strip().lower() == "/clear":
                agent.clear_history()
                print("[ Conversation cleared ]")
                continue

            print("\nAssistant: ", end="", flush=True)
            try:
                reply = await agent.run_turn(user_input)
                print(reply)
            except Exception as e:
                logger.exception("Agent error")
                print(f"\n[ Error: {e} ]")

    finally:
        stop_expiry.set()
        await airline_client.close()
        await payment_client.close()
        logger.info("Shutdown complete.")


if __name__ == "__main__":
    asyncio.run(main())
