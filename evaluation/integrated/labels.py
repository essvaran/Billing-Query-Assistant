"""Human labels for the evals, and judge agreement against them. Labels live in the catalog (table eval_labels).

A label belongs to the exact reply the person read, not to the case id: a later run can give a different reply to
the same case, and a label for the old reply says nothing about the new one. Each label stores a hash of the reply,
and agreement only counts a label when the hash matches the reply the judge saw.

The target and the minimum number of labels are settings (Admin, Settings, Evaluation).
"""
from collections import Counter

from src.catalog import eval_store, settings

VALUES = ("GOOD", "NOT_GOOD")
reply_sha = eval_store.reply_sha


def agreement_target() -> float:
    return settings.get("eval.agreement_target")


def min_labels() -> int:
    return settings.get("eval.min_labels")


def load() -> dict:
    return eval_store.labels()


def set_label(case_id: str, reply: str, label: str | None, tag: str, actor: str = "labeler") -> None:
    eval_store.set_label(case_id, reply, label, tag, actor)


def set_labeler(name: str, queue_experience: str, actor: str = "labeler") -> dict:
    return eval_store.set_labeler(name, queue_experience, actor)


def label_for(row: dict, data: dict) -> str | None:
    """The human label for this row's reply, or None if the case is unlabelled or was labelled for another reply."""
    entry = data["labels"].get(row["case_id"])
    if not entry:
        return None
    if entry.get("reply_sha") and entry["reply_sha"] != reply_sha(row.get("reply") or ""):
        return None
    return entry["label"]


def agreement(rows: list[dict], judge_key: str = "judge") -> dict:
    data = load()
    pairs = []
    for r in rows:
        verdict = (r.get(judge_key) or {}).get("verdict")
        human = label_for(r, data)
        if human and verdict in VALUES:
            pairs.append((human, verdict))
    if not pairs:
        return {"status": "no labelled cases matched judged cases", "labeler": data["labeler"], "n": 0}
    target, minimum = agreement_target(), min_labels()
    agree = sum(1 for human, judge in pairs if human == judge)
    confusion = Counter(pairs)
    out = {"n": len(pairs), "agree": agree, "agreement": round(agree / len(pairs), 3),
           "labeler": data["labeler"], "queue_experience": data["queue_experience"],
           "judge_good_human_not_good": confusion[("NOT_GOOD", "GOOD")],
           "judge_not_good_human_good": confusion[("GOOD", "NOT_GOOD")],
           "target": target, "min_labels": minimum,
           "meets_target": len(pairs) >= minimum and agree / len(pairs) >= target}
    out["status"] = "ok" if out["meets_target"] else f"below target: need n>={minimum} and agreement>={target:.0%}"
    return out
