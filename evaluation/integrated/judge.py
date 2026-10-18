"""LLM judge for the integrated system, from a DIFFERENT model family than the agent.

The agent is openai/gpt-oss-120b; the judge is qwen/qwen3.8-27b (Alibaba). A judge from the same
family as the agent tends to approve its own style, so the family differs on purpose.

The judge runs only on replies the system chose to ANSWER. Escalations are decided by assertions
(was it supposed to escalate, with a sensible reason, and did a handoff exist).

Its verdicts mean nothing until they are compared with human labels: see run.py, agreement().
"""
import re

from src.generation import gateway

JUDGE_VERSION = "v3b-integrated"  # v3 did not show the order record, so it flagged correct order statuses


def judge_model() -> str:
    """The judge model is a setting (Admin, Settings, Models); JUDGE_MODEL in the environment overrides it."""
    from src.catalog import settings
    return settings.get("models.judge")


def system_prompt() -> str:
    from src.catalog import prompts
    return prompts.body("judge.integrated")


_VERDICT = re.compile(r"VERDICT:\s*(NOT_GOOD|GOOD)", re.IGNORECASE)
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def build_prompt(case: dict, resp: dict) -> str:
    sources = "\n\n".join(
        f"[{s['chunk_id']}] ({s['slug']}, policy_version={s['policy_version']})\n{(s['text'] or '')[:900]}"
        for s in (resp.get("sources") or [])) or "(none retrieved)"
    facts = {"entitlement": resp.get("entitlement") or "(not checked)",
             "order": resp.get("order_facts") or "(not looked up)"}
    return (f"TICKET:\n{case['subject']}\n{case['body']}\n\n"
            f"ACCOUNT FACTS (trusted, from the account system: entitlement and order):\n{facts}\n\n"
            f"SOURCES retrieved from the help centre:\n{sources}\n\n"
            f"REPLY TO GRADE:\n{resp['reply']}")


def parse_verdict(text: str) -> tuple[str, str]:
    text = _THINK.sub("", text or "").strip()
    m = _VERDICT.search(text)
    if not m:
        return "ERROR", text[:200]
    reason = re.search(r"REASON:\s*(.+)", text)
    return m.group(1).upper(), (reason.group(1).strip() if reason else "")[:300]


WEEK6_VERSION = "week6-v2r"   # v2 criteria verbatim; answer format "verdict + one reason" (see WEEK6_FORMAT)
# The Week 6 rubric is the catalog prompt judge.week6_v2.
# Week 6 asked for exactly one word. On qwen that format said NOT_GOOD to every reply in the first 9 integrated cases,
# including a reply it called GOOD, with the right reason, as soon as it was allowed one sentence (seam 55). The
# criteria are unchanged; only the last line, the answer format, is replaced.
WEEK6_ONE_WORD_LINE = "Respond with exactly one word: GOOD or NOT_GOOD"
WEEK6_FORMAT = ("Reply with exactly two lines:\nVERDICT: GOOD or VERDICT: NOT_GOOD\n"
                "REASON: one sentence naming the rule above that decided it")


def week6_human_agreement() -> str:
    """Each Week 6 rubric's agreement with the Week 6 human labels, computed from the stored Week 6 run.

    The old code and docs said "v1 = v2 = 96%". The stored data says otherwise: v1 agreed on 24 of 25, v2 on 20 of 25.
    Quote what the data says.
    """
    from evaluation.integrated import labels
    from src.catalog import eval_store
    rows = eval_store.results("week6")
    parts = []
    for key, name in (("judge", "v2"), ("judge_alt", "v1")):
        ag = labels.agreement(rows, key) if rows else {"n": 0}
        if ag.get("n"):
            parts.append(f"{name} {ag['agree']}/{ag['n']} = {ag['agreement']:.0%}")
    return ("; ".join(parts) + " (Week 6 labels)") if parts else "not stored"


def build_week6_prompt(case: dict, resp: dict) -> str:
    """The Week 6 judge's own input format (question, context, response), unchanged except for one addition.

    The integrated system also answers from account facts (entitlement and order record), which Week 6 never had.
    They are given as one more context block; without them the Week 6 rubric calls every correct order status
    "stated facts not present in any context chunk" (the same failure as seam 31).
    """
    parts = [f"[Chunk {i}: {s['chunk_id']}]\n{(s.get('text') or '')[:400]}"
             for i, s in enumerate((resp.get("sources") or [])[:5], 1)]
    facts = {"entitlement": resp.get("entitlement") or "(not checked)", "order": resp.get("order_facts") or "(not looked up)"}
    parts.append(f"[Account facts from the account system: trusted]\n{facts}")
    return (f"Question: {case['subject']}\n{case['body']}\n\n"
            f"Context provided to the assistant:\n" + "\n\n".join(parts) + "\n\n"
            f"Assistant response:\n{resp['reply']}")


def week6_system_prompt() -> str:
    from src.catalog import prompts
    text = prompts.body("judge.week6_v2").strip()
    assert WEEK6_ONE_WORD_LINE in text, "prompt judge.week6_v2 must keep its answer-format line (a required phrase)"
    return text.replace(WEEK6_ONE_WORD_LINE, WEEK6_FORMAT)


def judge_reply_week6(case: dict, resp: dict) -> dict:
    """The Week 6 validated rubric (judge_v2.txt), re-checked on integrated outputs.

    The Week 6 judge model is no longer available on this key, so the rubric runs on the judge model setting (a different family
    from the agent). Its Week 6 agreement does not carry over: it is re-measured against labels of integrated replies.
    """
    try:
        data = gateway.chat(
            [{"role": "system", "content": week6_system_prompt()},
             {"role": "user", "content": build_week6_prompt(case, resp)}],
            model=judge_model(), temperature=0.0)
    except gateway.GatewayError as exc:
        return {"verdict": "ERROR", "reason": str(exc)[:200], "model": judge_model(), "version": WEEK6_VERSION,
                "cache": None, "tokens": 0}
    verdict, reason = parse_verdict(data["choices"][0]["message"].get("content") or "")
    return {"verdict": verdict, "reason": reason, "model": judge_model(),
            "version": WEEK6_VERSION, "cache": (data.get("gateway") or {}).get("cache"),
            "tokens": (data.get("usage") or {}).get("total_tokens", 0)}


def judge_reply(case: dict, resp: dict) -> dict:
    """Returns {verdict: GOOD|NOT_GOOD|ERROR, reason, model, cache, tokens}."""
    try:
        data = gateway.chat(
            [{"role": "system", "content": system_prompt()}, {"role": "user", "content": build_prompt(case, resp)}],
            model=judge_model(), temperature=0.0)
    except gateway.GatewayError as exc:
        return {"verdict": "ERROR", "reason": str(exc)[:200], "model": judge_model(), "cache": None, "tokens": 0}
    verdict, reason = parse_verdict(data["choices"][0]["message"].get("content") or "")
    return {"verdict": verdict, "reason": reason, "model": judge_model(), "version": JUDGE_VERSION,
            "cache": (data.get("gateway") or {}).get("cache"),
            "tokens": (data.get("usage") or {}).get("total_tokens", 0)}
