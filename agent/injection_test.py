"""Prompt injection testing for the ticket agent.

Plants hidden instructions inside ticket text, runs the agent undefended
and defended, and reports whether the injection succeeded.
"""

import json
import re
import time

from agent.tickets import score_reply
from agent.tools import dispatch_tool

def injection_payloads() -> list[dict]:
    """Attacks planted into Week 7 tickets (catalog list injection_payload: target ticket, payload, expected verdict)."""
    from src.catalog import ref
    return [{"id": v["code"], "name": v["label"], **v["meta"]} for v in ref.values("injection_payload")]

def defense_addition() -> str:
    from src.catalog import prompts
    return "\n\n" + prompts.body("week8.injection_defense")


def _sanitize_tool_output(output: str) -> str:
    """Strip known injection patterns from tool output."""
    from src.catalog import ref
    patterns = [v["label"] for v in ref.values("injection_sanitize_pattern")]
    cleaned = output
    for pattern in patterns:
        cleaned = re.sub(pattern, "[REDACTED: potential injection]", cleaned, flags=re.IGNORECASE | re.DOTALL)
    return cleaned


def create_sanitizing_dispatch():
    """Return a dispatch wrapper that sanitizes tool outputs."""
    def sanitizing_dispatch(name: str, arguments: str) -> str:
        result = dispatch_tool(name, arguments)
        return _sanitize_tool_output(result)
    return sanitizing_dispatch


def _detect_verdict(reply: str) -> str:
    """Detect which verdict the agent gave in its reply."""
    for verdict in ["approve", "deny", "escalate"]:
        if score_reply(reply, verdict):
            return verdict
    return "unknown"


def _run_single_injection(payload: dict, defended: bool = False) -> dict:
    """Run agent on a ticket with injected payload, optionally with defenses."""
    from agent.agent_loop import run_agent, system_prompt

    target_ticket = payload["target_ticket"]

    def injecting_dispatch(name: str, arguments: str) -> str:
        """The attack arrives the way a real one would: inside the ticket text the get_ticket tool returns."""
        result = dispatch_tool(name, arguments)
        if name == "get_ticket":
            data = json.loads(result)
            if data.get("ticket_id") == target_ticket and "text" in data:
                data["text"] += payload["payload"]
                result = json.dumps(data)
        return result

    try:
        kwargs = {
            "ticket_id": target_ticket,
            "expected_verdict": payload["expected_verdict"],
            "verbose": False,
            "dispatch_override": injecting_dispatch,
        }

        if defended:
            kwargs["system_prompt_override"] = system_prompt() + defense_addition()
            kwargs["dispatch_override"] = lambda name, arguments: _sanitize_tool_output(injecting_dispatch(name, arguments))

        result = run_agent(**kwargs)

        agent_verdict = _detect_verdict(result.reply)
        injection_succeeded = agent_verdict != payload["expected_verdict"]

        return {
            "reply": result.reply[:500],
            "agent_verdict": agent_verdict,
            "injection_succeeded": injection_succeeded,
            "defense_held": not injection_succeeded if defended else False,
        }
    finally:
        pass


def run_all_injection_tests() -> list[dict]:
    """Run all injection payloads undefended and defended."""
    results = []

    for payload in injection_payloads():
        undefended = _run_single_injection(payload, defended=False)
        time.sleep(3)

        defended = _run_single_injection(payload, defended=True)
        time.sleep(3)

        what_still_gets_through = ""
        if defended["injection_succeeded"]:
            what_still_gets_through = (
                "The injection bypassed the defense. Possible reasons: "
                "the payload pattern was not in the sanitization list, "
                "or the LLM still interpreted the injected text as instructions "
                "despite the security prompt."
            )
        elif not undefended["injection_succeeded"]:
            what_still_gets_through = (
                "The agent was not vulnerable to this injection even without defenses. "
                "The model may be robust to this specific attack pattern."
            )
        else:
            what_still_gets_through = (
                "This specific injection was blocked. However, more sophisticated attacks "
                "(e.g., encoded instructions, multi-turn manipulation, or indirect injection "
                "through tool results from external sources) could still get through. "
                "Defense-in-depth with output validation and least-privilege tools is essential."
            )

        results.append({
            "payload_id": payload["id"],
            "payload_name": payload["name"],
            "payload_text": payload["payload"],
            "target_ticket": payload["target_ticket"],
            "expected_verdict": payload["expected_verdict"],
            "undefended": undefended,
            "defended": defended,
            "what_still_gets_through": what_still_gets_through,
        })

    return results
