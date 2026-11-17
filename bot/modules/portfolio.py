"""Answers questions about Mayank Ranghadiya from his CV (bot/portfolio/).

PRIORITY 9200 puts it in the arbiter's never-outvoted band (>= 9000) so a CV fact is never replaced
by a general-knowledge guess, and above safety.py (9000) in candidate order. It only proposes when
a line names Mayank or the host app has set memory["portfolio_agent"], and it stays silent on lines
the safety module would want: the engine's router has no pattern for crisis or harm topics, and the
crisis guard below hands those lines straight back.
"""
import re

from bot.portfolio import engine

PRIORITY = 9200
ANSWERS = ("portfolio", "career", "mayank")

_CRISIS = re.compile(
    r"\b(suicid|kill (my|him|her|them)self|self.harm|overdose|hurt (my|him|her)self|emergency|"
    r"can't breathe|chest pain|abuse|abused|assault)", re.I)


def respond(text, memory):
    if _CRISIS.search(text or ""):
        return None
    try:
        return engine.answer(text, memory)
    except Exception:  # noqa: BLE001 - never take the turn down
        return None
