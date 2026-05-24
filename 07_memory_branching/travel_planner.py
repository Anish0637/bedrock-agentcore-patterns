"""
Pattern 7 — Memory Branching for Multi-Agent Travel Planner
=============================================================
A Strands Agent Graph with three agents, each using an isolated
AgentCore Memory branch to prevent context pollution during parallel
execution:

  travel_agent        → main branch     (orchestrator)
  flight_booking_agent → flight_agent_memory branch
  hotel_booking_agent  → hotel_agent_memory branch

Usage:
    python memory_setup.py          # create shared memory resource (pattern 6)
    python travel_planner.py        # run the travel planner graph
"""

import os
import logging
from uuid import uuid4
from datetime import datetime
from dotenv import load_dotenv

from strands import Agent, tool
from strands.multiagent import GraphBuilder
from bedrock_agentcore.memory import MemoryClient

from branch_memory_hook import ShortTermMemoryHook

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)

REGION = os.getenv("AWS_DEFAULT_REGION", "us-west-2")
MODEL_ID = os.getenv("MODEL_ID", "us.anthropic.claude-3-7-sonnet-20250219-v1:0")
MEMORY_ID = os.getenv("MEMORY_ID")
ACTOR_ID = os.getenv("ACTOR_ID", "traveler-001")
SESSION_ID = os.getenv("SESSION_ID", f"trip-{uuid4().hex[:8]}")

# ── Singleton hooks (reused across invocations) ────────────────────────────────
_travel_hook: ShortTermMemoryHook | None = None
_flight_hook: ShortTermMemoryHook | None = None
_hotel_hook: ShortTermMemoryHook | None = None


def _get_hook(branch: str) -> ShortTermMemoryHook:
    return ShortTermMemoryHook(memory_id=MEMORY_ID, region_name=REGION, branch_name=branch)


# ── Prompts ────────────────────────────────────────────────────────────────────

TRAVEL_COORDINATOR_PROMPT = f"""You are a Travel Coordinator AI assistant.
Your job is to help users plan complete trips.
Today is {datetime.utcnow().strftime('%Y-%m-%d')}.

You delegate tasks to:
• flight_booking_agent  — for all flight-related queries
• hotel_booking_agent   — for all accommodation queries

Always confirm the full trip plan at the end with a summary.
Be concise and structured."""

FLIGHT_BOOKING_PROMPT = """You are a Flight Booking specialist.
You handle all flight searches, airline recommendations, seat preferences, and pricing.
Always ask for origin, destination, travel date, and passenger count if not provided.
Return structured flight options with price estimates."""

HOTEL_BOOKING_PROMPT = """You are a Hotel Booking specialist.
You handle all accommodation searches, hotel recommendations, room types, and pricing.
Always ask for destination, check-in/out dates, and guest count if not provided.
Return structured hotel options with price estimates and amenities."""


# ── Sub-agent tools (coordinator delegates to these) ──────────────────────────

@tool
def search_flights(origin: str, destination: str, date: str, passengers: int = 1) -> str:
    """Search for available flights between two cities.

    Args:
        origin: Departure city or airport code.
        destination: Arrival city or airport code.
        date: Travel date (YYYY-MM-DD).
        passengers: Number of passengers.
    """
    # Stub — wire to a real flights API in production (Amadeus, Skyscanner, etc.)
    return (
        f"✈️  Flights from {origin} to {destination} on {date} for {passengers} passenger(s):\n"
        f"  • AA 123 — Departs 08:00, Arrives 12:30 — $350/person — Economy\n"
        f"  • UA 456 — Departs 14:00, Arrives 18:45 — $295/person — Economy\n"
        f"  • DL 789 — Departs 19:00, Arrives 23:15 — $410/person — Business"
    )


@tool
def search_hotels(city: str, check_in: str, check_out: str, guests: int = 1) -> str:
    """Search for available hotels in a city.

    Args:
        city: Destination city.
        check_in: Check-in date (YYYY-MM-DD).
        check_out: Check-out date (YYYY-MM-DD).
        guests: Number of guests.
    """
    return (
        f"🏨 Hotels in {city} from {check_in} to {check_out} for {guests} guest(s):\n"
        f"  • The Grand Hotel — ⭐⭐⭐⭐⭐ — $280/night — Free breakfast\n"
        f"  • City Center Inn — ⭐⭐⭐⭐  — $150/night — Free WiFi, Pool\n"
        f"  • Budget Stay       — ⭐⭐⭐   — $80/night  — Free WiFi"
    )


# ── Agent factories ────────────────────────────────────────────────────────────

def travel_coordinator_agent() -> Agent:
    global _travel_hook
    if _travel_hook is None:
        _travel_hook = _get_hook("main")
    return Agent(
        name="TravelCoordinator",
        model=MODEL_ID,
        system_prompt=TRAVEL_COORDINATOR_PROMPT,
        hooks=[_travel_hook],
        state={"actor_id": ACTOR_ID, "session_id": SESSION_ID},
    )


def flight_booking_agent() -> Agent:
    global _flight_hook
    if _flight_hook is None:
        _flight_hook = _get_hook("flight_agent_memory")
    return Agent(
        name="FlightBookingAgent",
        model=MODEL_ID,
        system_prompt=FLIGHT_BOOKING_PROMPT,
        tools=[search_flights],
        hooks=[_flight_hook],
        state={"actor_id": ACTOR_ID, "session_id": SESSION_ID},
    )


def hotel_booking_agent() -> Agent:
    global _hotel_hook
    if _hotel_hook is None:
        _hotel_hook = _get_hook("hotel_agent_memory")
    return Agent(
        name="HotelBookingAgent",
        model=MODEL_ID,
        system_prompt=HOTEL_BOOKING_PROMPT,
        tools=[search_hotels],
        hooks=[_hotel_hook],
        state={"actor_id": ACTOR_ID, "session_id": SESSION_ID},
    )


# ── Build and run the graph ────────────────────────────────────────────────────

def build_graph():
    builder = GraphBuilder()
    builder.add_node(travel_coordinator_agent(), "travel_agent")
    builder.add_node(flight_booking_agent(), "flight_booking_agent")
    builder.add_node(hotel_booking_agent(), "hotel_booking_agent")

    builder.add_edge("travel_agent", "flight_booking_agent")
    builder.add_edge("travel_agent", "hotel_booking_agent")

    builder.set_entry_point("travel_agent")
    builder.set_execution_timeout(600)

    return builder.build()


if __name__ == "__main__":
    if not MEMORY_ID:
        print("⚠️  MEMORY_ID not set. Run: python ../06_memory/memory_setup.py")
    else:
        print("🌍 Travel Planning Multi-Agent System (type 'quit' to exit)\n")
        print(f"   Session ID : {SESSION_ID}")
        print(f"   Actor ID   : {ACTOR_ID}\n")

        graph = build_graph()

        while True:
            user_input = input("You: ").strip()
            if user_input.lower() in ("quit", "exit", "q"):
                print("Safe travels!")
                break
            if not user_input:
                continue
            result = graph.run(user_input)
            print(f"\n🤖 Travel Planner:\n{result}\n")
