"""
Pattern 7 — Branch-Aware Short-Term Memory Hook
================================================
Extends the basic MemoryHookProvider to support AgentCore Memory Branching.
Each agent in a multi-agent graph gets its own isolated branch so that
parallel execution is safe and contexts don't bleed between agents.
"""

import logging
from typing import Optional

from bedrock_agentcore.memory import MemoryClient
from bedrock_agentcore.memory.session import MemorySessionManager, MemorySession
from bedrock_agentcore.memory.types import ConversationalMessage, MessageRole
from bedrock_agentcore.runtime.hooks import (
    HookProvider,
    HookRegistry,
    AgentInitializedEvent,
    MessageAddedEvent,
)

logger = logging.getLogger(__name__)


class ShortTermMemoryHook(HookProvider):
    """
    Branch-aware memory hook for use inside Strands Agent Graphs.

    Each agent is assigned a branch_name.  The hook:
      1. Creates the branch (forked from `main`) on first use.
      2. Loads the last K turns from that branch on agent init.
      3. Appends every new message to the branch.
    """

    def __init__(
        self,
        memory_id: str,
        region_name: str = "us-west-2",
        branch_name: str = "main",
        k_turns: int = 5,
    ):
        self.memory_id = memory_id
        self.branch_name = branch_name
        self.k_turns = k_turns
        self._manager = MemorySessionManager(memory_id=memory_id, region_name=region_name)
        self._sessions: dict[str, MemorySession] = {}
        self._branch_initialized = False

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _session(self, actor_id: str, session_id: str) -> MemorySession:
        key = f"{actor_id}:{session_id}"
        if key not in self._sessions:
            self._sessions[key] = self._manager.create_memory_session(
                actor_id=actor_id, session_id=session_id
            )
        return self._sessions[key]

    def _ensure_branch(self, actor_id: str, session_id: str):
        """Fork the branch from `main` if it doesn't exist yet."""
        if self._branch_initialized or self.branch_name == "main":
            self._branch_initialized = True
            return

        sess = self._session(actor_id, session_id)
        branches = sess.list_branches()
        if any(b.name == self.branch_name for b in branches):
            self._branch_initialized = True
            return

        main_events = sess.list_events(branch_name="main")
        if not main_events:
            logger.info("Main branch is empty; skipping fork for %s", self.branch_name)
            return

        sess.fork_conversation(
            root_event_id=main_events[-1].eventId,
            branch_name=self.branch_name,
            messages=[
                ConversationalMessage(
                    f"Starting {self.branch_name} branch", MessageRole.ASSISTANT
                )
            ],
        )
        self._branch_initialized = True
        logger.info("Branch '%s' created", self.branch_name)

    # ── Lifecycle hooks ───────────────────────────────────────────────────────

    def on_agent_initialized(self, event: AgentInitializedEvent):
        actor_id = event.agent.state.get("actor_id")
        session_id = event.agent.state.get("session_id")
        if not actor_id or not session_id:
            return

        sess = self._session(actor_id, session_id)

        # Ensure branch exists before loading turns
        if self.branch_name != "main":
            try:
                main_events = sess.list_events(branch_name="main")
                if main_events:
                    self._ensure_branch(actor_id, session_id)
            except Exception as exc:
                logger.info("Main branch not ready yet: %s", exc)

        branches = sess.list_branches()
        branch_exists = any(b.name == self.branch_name for b in branches)

        if not branch_exists:
            logger.info("Branch '%s' doesn't exist yet; skipping load", self.branch_name)
            return

        try:
            turns = sess.get_last_k_turns(k=self.k_turns, branch_name=self.branch_name)
            if not turns:
                return

            lines = []
            for turn in turns:
                for msg in turn:
                    role = msg.content.get("role", "unknown").capitalize()
                    text = msg.content.get("content", {}).get("text", "")
                    if text:
                        lines.append(f"{role}: {text}")

            if lines:
                context = "\n".join(lines)
                event.agent.system_prompt += (
                    f"\n\nRecent conversation history (branch: {self.branch_name}):\n{context}\n"
                    "Continue naturally based on this context."
                )
                logger.info(
                    "Loaded %d turns from branch '%s'", len(turns), self.branch_name
                )
        except Exception as exc:
            logger.error("Failed to load branch history: %s", exc)

    def on_message_added(self, event: MessageAddedEvent):
        actor_id = event.agent.state.get("actor_id")
        session_id = event.agent.state.get("session_id")
        if not actor_id or not session_id:
            return

        messages = event.agent.messages
        if not messages:
            return

        last = messages[-1]
        role_str = last.get("role", "").upper()
        content = last.get("content", [{}])
        text = content[0].get("text", "") if content else ""
        if not text:
            return

        role_map = {
            "USER": MessageRole.USER,
            "ASSISTANT": MessageRole.ASSISTANT,
            "TOOL": MessageRole.TOOL,
        }
        role = role_map.get(role_str, MessageRole.USER)

        try:
            sess = self._session(actor_id, session_id)
            if self.branch_name == "main":
                sess.add_turns(messages=[ConversationalMessage(text, role)])
            else:
                if not self._branch_initialized:
                    self._ensure_branch(actor_id, session_id)
                branch_events = sess.list_events(branch_name=self.branch_name)
                if branch_events:
                    sess.add_turns(
                        messages=[ConversationalMessage(text, role)],
                        branch={"name": self.branch_name},
                    )
                else:
                    self._ensure_branch(actor_id, session_id)
            logger.debug("Stored message on branch '%s': %s", self.branch_name, role_str)
        except Exception as exc:
            logger.error("Failed to store message on branch '%s': %s", self.branch_name, exc)

    # ── Registration ──────────────────────────────────────────────────────────

    def register_hooks(self, registry: HookRegistry):
        registry.add_callback(AgentInitializedEvent, self.on_agent_initialized)
        registry.add_callback(MessageAddedEvent, self.on_message_added)
