"""
Pattern 6 — MemoryHookProvider
================================
Automatically persists conversation turns and retrieves relevant
long-term memories using AgentCore Runtime lifecycle hooks.
"""

import logging
from bedrock_agentcore.memory import MemoryClient
from bedrock_agentcore.runtime.hooks import (
    HookProvider,
    HookRegistry,
    AgentInitializedEvent,
    MessageAddedEvent,
    AfterInvocationEvent,
)

logger = logging.getLogger(__name__)


class MemoryHookProvider(HookProvider):
    """
    Lifecycle hook that bridges AgentCore Runtime events with AgentCore Memory.

    Hooks registered:
      • AgentInitializedEvent  → load recent K turns + inject into system prompt
      • MessageAddedEvent      → retrieve relevant long-term memories, inject context
      • AfterInvocationEvent   → persist the completed user/assistant turn
    """

    def __init__(self, memory_client: MemoryClient, memory_id: str, k_turns: int = 5):
        self.client = memory_client
        self.memory_id = memory_id
        self.k_turns = k_turns

    # ── Load short-term context on init ──────────────────────────────────────

    def on_agent_initialized(self, event: AgentInitializedEvent):
        actor_id = event.agent.state.get("actor_id")
        session_id = event.agent.state.get("session_id")
        if not actor_id or not session_id:
            logger.warning("Missing actor_id or session_id in agent state")
            return

        try:
            recent_turns = self.client.get_last_k_turns(
                memory_id=self.memory_id,
                actor_id=actor_id,
                session_id=session_id,
                k=self.k_turns,
            )
            if recent_turns:
                lines = []
                for turn in recent_turns:
                    for msg in turn:
                        role = msg.get("role", "unknown").capitalize()
                        text = msg.get("content", {}).get("text", "")
                        if text:
                            lines.append(f"{role}: {text}")
                if lines:
                    context = "\n".join(lines)
                    event.agent.system_prompt += (
                        f"\n\nRecent conversation history:\n{context}"
                    )
                    logger.info("Injected %d turns into system prompt", len(recent_turns))

        except Exception as exc:
            logger.error("Failed to load short-term memory: %s", exc)

    # ── Retrieve long-term memories before processing user message ────────────

    def on_message_added(self, event: MessageAddedEvent):
        messages = event.agent.messages
        if not messages:
            return

        last = messages[-1]
        if last.get("role") != "user":
            return
        if "toolResult" in last.get("content", [{}])[0]:
            return

        user_text = last["content"][0].get("text", "")
        if not user_text:
            return

        actor_id = event.agent.state.get("actor_id")
        if not actor_id:
            return

        try:
            memories = self.client.retrieve_memories(
                memory_id=self.memory_id,
                namespace=f"/knowledge/{actor_id}",
                query=user_text,
            )
            snippets = [
                m.get("content", {}).get("text", "").strip()
                for m in memories
                if isinstance(m, dict) and m.get("content", {}).get("text", "").strip()
            ]
            if snippets:
                context_block = "\n".join(f"- {s}" for s in snippets)
                last["content"][0]["text"] = (
                    f"{user_text}\n\n[Retrieved memory context]\n{context_block}"
                )
                logger.info("Injected %d long-term memory snippets", len(snippets))

        except Exception as exc:
            logger.error("Failed to retrieve long-term memory: %s", exc)

    # ── Persist turn after response ───────────────────────────────────────────

    def on_after_invocation(self, event: AfterInvocationEvent):
        messages = event.agent.messages
        if len(messages) < 2 or messages[-1].get("role") != "assistant":
            return

        actor_id = event.agent.state.get("actor_id")
        session_id = event.agent.state.get("session_id")
        if not actor_id or not session_id:
            return

        try:
            # Find last user/assistant pair
            assistant_text = None
            user_text = None
            for msg in reversed(messages):
                if msg["role"] == "assistant" and not assistant_text:
                    content = msg.get("content", [{}])
                    assistant_text = content[0].get("text", "") if content else ""
                elif msg["role"] == "user" and not user_text:
                    content = msg.get("content", [{}])
                    if "toolResult" not in content[0]:
                        user_text = content[0].get("text", "")
                        break

            if user_text and assistant_text:
                self.client.create_event(
                    memory_id=self.memory_id,
                    actor_id=actor_id,
                    session_id=session_id,
                    messages=[(user_text, "USER"), (assistant_text, "ASSISTANT")],
                )
                logger.info("Persisted conversation turn to memory")

        except Exception as exc:
            logger.error("Failed to persist memory: %s", exc)

    def register_hooks(self, registry: HookRegistry):
        registry.add_callback(AgentInitializedEvent, self.on_agent_initialized)
        registry.add_callback(MessageAddedEvent, self.on_message_added)
        registry.add_callback(AfterInvocationEvent, self.on_after_invocation)
