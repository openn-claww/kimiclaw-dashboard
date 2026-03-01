#!/usr/bin/env python3
"""
memory_integration.py
Drop-in wrapper that gives your OpenClaw agent:
  1. recall_before_answer(topic)  → inject relevant context
  2. log_turn(role, content)      → auto-log every exchange
  3. summarize_and_store(topic)   → condense recent turns into a memory
"""

import sys
from pathlib import Path

# Allow import from workspace root
sys.path.insert(0, str(Path(__file__).parent))

from memory.memory import recall, log_memory, log_conversation, recent_conversations


# ─── 1. Recall before answering ───────────────────────────────────────────────

def recall_before_answer(topic: str, limit: int = 3) -> str:
    """
    Call this at the START of handling any user message.
    Returns a formatted context block to prepend to your system/user prompt.

    Example:
        context = recall_before_answer("BTC price alert")
        full_prompt = context + user_message
    """
    memories = recall(topic, limit)
    if not memories:
        return ""

    lines = ["[MEMORY CONTEXT]"]
    for m in memories:
        lines.append(f"- ({m['topic']}) {m['content']}")
    lines.append("")
    return "\n".join(lines)


# ─── 2. Log every conversation turn ──────────────────────────────────────────

def log_turn(role: str, content: str, topic: str = "") -> None:
    """
    Call this AFTER every user message and every assistant reply.

    Usage in your agent loop:
        log_turn("user", user_input, topic="trading")
        response = agent.chat(user_input)
        log_turn("assistant", response, topic="trading")
    """
    log_conversation(role, content, topic)


# ─── 3. Summarize recent turns into long-term memory ─────────────────────────

def summarize_and_store(topic: str, n_turns: int = 10, summary: str = "") -> None:
    """
    Condense the last N conversation turns into a single memory entry.
    Pass `summary` manually, or build one automatically.

    Example (with OpenAI/Claude API):
        turns = recent_conversations(10)
        transcript = "\\n".join(f"{t['role']}: {t['content']}" for t in turns)
        summary = your_llm.summarize(transcript)
        summarize_and_store("BTC trade session", summary=summary)
    """
    if not summary:
        turns = recent_conversations(n_turns)
        # Naive auto-summary: last assistant message
        for t in reversed(turns):
            if t["role"] == "assistant":
                summary = t["content"][:500]
                break
        if not summary:
            return

    log_memory(topic, summary, tags="auto-summary", source="conversation")
    print(f"[memory] Stored summary under topic: '{topic}'")


# ─── 4. Full agent loop wrapper ───────────────────────────────────────────────

class MemoryAwareAgent:
    """
    Minimal wrapper. Swap `your_llm_call` with your actual LLM invocation.

    Example:
        agent = MemoryAwareAgent(llm_fn=my_openai_call, default_topic="trading_bot")
        reply = agent.chat("What was BTC doing last week?")
    """

    def __init__(self, llm_fn, default_topic: str = "general"):
        self.llm_fn = llm_fn
        self.topic = default_topic

    def chat(self, user_message: str, topic: str = None) -> str:
        t = topic or self.topic

        # Step 1: inject memory context
        context = recall_before_answer(t)
        prompt = context + user_message if context else user_message

        # Step 2: log user turn
        log_turn("user", user_message, t)

        # Step 3: call your LLM
        response = self.llm_fn(prompt)

        # Step 4: log assistant turn
        log_turn("assistant", response, t)

        return response

    def end_session(self, summary: str = "") -> None:
        """Call at end of session to persist a summary."""
        summarize_and_store(self.topic, summary=summary)


# ─── Quick smoke test ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Memory Integration Smoke Test ===\n")

    log_turn("user", "What's the RSI for BTC right now?", "trading")
    log_turn("assistant", "BTC RSI is at 67, approaching overbought territory.", "trading")
    log_memory("BTC_RSI_alert", "RSI hit 67 on 2025-02-28, watch for reversal.", tags="BTC,RSI,alert")

    ctx = recall_before_answer("BTC")
    print("Recalled context:\n", ctx)

    summarize_and_store("BTC_session_2025-02-28")
    print("\nDone. Run `python3 memory/memory.py stats` to verify.")
