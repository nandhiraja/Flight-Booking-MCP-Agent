"""
agent/tool_definitions.py

Groq-compatible tool schemas for the Booking Platform Agent.
These are the tools the LLM can call — each maps to an application layer function.
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_available_routes",
            "description": (
                "Returns all available flight routes and their typical prices. "
                "Call this when the user asks to 'list flights', 'show routes', or 'what flights are available' "
                "WITHOUT specifying a specific origin and destination. "
                "Do NOT call search_flights before calling this."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "search_flights",
            "description": (
                "Search for available flights between two airports on a specific date. "
                "Returns a list of flights with prices and seat availability."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "origin": {
                        "type": "string",
                        "description": "IATA 3-letter departure airport code, e.g. 'DEL'.",
                    },
                    "destination": {
                        "type": "string",
                        "description": "IATA 3-letter arrival airport code, e.g. 'BOM'.",
                    },
                    "date": {
                        "type": "string",
                        "description": "Travel date in ISO format YYYY-MM-DD.",
                    },
                },
                "required": ["origin", "destination", "date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_booking",
            "description": (
                "Create a new booking record for a user and flight. "
                "Does NOT reserve seats yet — call reserve_flight next."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "Platform user ID (e.g. 'USR-001').",
                    },
                    "flight_id": {
                        "type": "string",
                        "description": "Flight ID from search_flights result.",
                    },
                    "seat_count": {
                        "type": "integer",
                        "description": "Number of seats to book (>= 1).",
                    },
                    "price_per_seat": {
                        "type": "string",
                        "description": "Price per seat as a decimal string (from search results).",
                    },
                    "currency": {
                        "type": "string",
                        "description": "Currency code, e.g. 'INR'.",
                    },
                },
                "required": ["user_id", "flight_id", "seat_count", "price_per_seat", "currency"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reserve_flight",
            "description": (
                "Reserve seats on the airline for an existing booking. "
                "Booking must be in CREATED state. Returns a 10-minute seat hold."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "booking_id": {
                        "type": "string",
                        "description": "The booking ID to reserve seats for.",
                    },
                },
                "required": ["booking_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_saved_payment_methods",
            "description": "Return saved payment methods for a user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "Platform user ID.",
                    },
                },
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "initiate_payment",
            "description": (
                "⚠️ REQUIRES USER CONFIRMATION BEFORE CALLING. "
                "Initiates payment for a booking. "
                "Booking must be in SEAT_RESERVED state. "
                "Always show the user the amount and card before calling this tool."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "booking_id": {
                        "type": "string",
                        "description": "The booking ID to pay for.",
                    },
                    "payment_token": {
                        "type": "string",
                        "description": "Saved payment token (for auto-pay mode). Omit for redirect mode.",
                    },
                },
                "required": ["booking_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_booking_status",
            "description": "Get the current status and details of a booking.",
            "parameters": {
                "type": "object",
                "properties": {
                    "booking_id": {
                        "type": "string",
                        "description": "The booking ID to query.",
                    },
                },
                "required": ["booking_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_booking",
            "description": "Cancel a booking that is in SEAT_RESERVED state.",
            "parameters": {
                "type": "object",
                "properties": {
                    "booking_id": {
                        "type": "string",
                        "description": "The booking ID to cancel.",
                    },
                },
                "required": ["booking_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_user_bookings",
            "description": "List all bookings for a specific user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "Platform user ID.",
                    },
                },
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reconcile_payment",
            "description": (
                "Check payment status with the gateway and attempt to confirm "
                "the booking if payment succeeded but webhook was missed."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "booking_id": {
                        "type": "string",
                        "description": "The booking ID to reconcile.",
                    },
                },
                "required": ["booking_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "simulate_payment_outcome",
            "description": (
                "[DEVELOPER TOOL] Simulate the user completing or failing a payment. "
                "Only use this in a test/demo context after initiate_payment has been called."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "payment_id": {
                        "type": "string",
                        "description": "The payment_id returned by initiate_payment.",
                    },
                    "result": {
                        "type": "string",
                        "enum": ["SUCCESS", "FAILED"],
                        "description": "Simulated payment outcome.",
                    },
                },
                "required": ["payment_id", "result"],
            },
        },
    },
]

# Sentinel: tools that require human confirmation before execution
HUMAN_CONFIRMATION_REQUIRED = {"initiate_payment"}
