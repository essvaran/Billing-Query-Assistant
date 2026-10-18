"""Command line entry point:  python -m tier1 <command>

  up                            one command from a fresh clone: check .env, install, build data and index, answer a ticket
  seed                          load the synthetic customers, orders and tickets
  answer --ticket TK3001        run a ticket from the sample
  answer --text "..." --customer C1000 [--order O2000]
  demo --seed 7                 draw a RANDOM ticket from the sample (seed is printed)
  handoffs                      show queued escalations
  eval [--tag after] [--ablate ...]   run the integrated eval suite (see evaluation/integrated/run.py)
"""
import argparse
import json
import random
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from tier1 import db
from tier1.models import TicketRequest


def _print_result(resp, ticket: dict | None = None) -> None:
    print()
    if ticket:
        print(f"expected: {ticket['expected_decision']}"
              f"  policy: {ticket['expected_policy_version']}  gold: {ticket['gold_slug']}")
    print(f"decision: {resp.decision}" + (f"  (reason: {resp.reason})" if resp.reason else ""))
    if resp.entitlement:
        e = resp.entitlement
        print(f"entitlement: plan={e['plan']} policy={e['policy_version']} window={e['refund_days']}d region={e['region']}")
    print(f"tools: {' > '.join(resp.tools_called) or '(none)'}")
    if resp.reply:
        print(f"\nreply:\n{resp.reply}")
    if resp.draft:
        print(f"\nblocked draft:\n{resp.draft}")
    if resp.citations:
        print("\ncitations: " + ", ".join(c["display"] for c in resp.citations))
    for v in resp.violations:
        print(f"violation: {v['code']} - {v['detail']}")
    if resp.handoff_id:
        print(f"handoff: {resp.handoff_id}")
    print(f"\ntrace_id={resp.trace_id}  laps={resp.laps}  tokens={resp.total_tokens}  "
          f"cost=${resp.cost_usd:.5f}  latency={resp.latency_ms / 1000:.1f}s")


def _request_from_ticket(t: dict) -> TicketRequest:
    return TicketRequest(body=t["body"], subject=t["subject"] or "", customer_id=t["customer_id"],
                         order_id=t["order_id"], ticket_id=t["ticket_id"])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tier1", description="Tier-1 Deflection Assistant")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("seed", help="load synthetic data into data/tier1.db")
    a = sub.add_parser("answer", help="answer one ticket")
    a.add_argument("--ticket", help="ticket id from the sample, e.g. TK3001")
    a.add_argument("--text", help="free-text ticket body")
    a.add_argument("--subject", default="")
    a.add_argument("--customer", default="")
    a.add_argument("--order", default="")
    a.add_argument("--json", action="store_true", help="print the raw response as JSON")
    d = sub.add_parser("demo", help="answer a random ticket from the sample")
    d.add_argument("--seed", type=int, default=None, help="reproduce a previous draw")
    d.add_argument("--kind", default=None, help="restrict to a ticket kind, e.g. refund")
    sub.add_parser("handoffs", help="list queued escalations")
    sub.add_parser("eval", help="run the integrated eval suite; extra flags are passed through")
    sub.add_parser("up", help="set up everything from a fresh clone and answer one ticket")
    args, extra = ap.parse_known_args(argv)
    if args.cmd == "up":
        from tier1.bootstrap import main as up
        return up(extra)
    if args.cmd == "eval":
        from evaluation.integrated.run import main as run_eval
        return run_eval(extra)
    if extra:
        ap.error(f"unrecognised arguments: {' '.join(extra)}")

    db.seed_from_synthetic()

    if args.cmd == "seed":
        print(db.seed_from_synthetic(force=True))
        return 0
    if args.cmd == "handoffs":
        for h in db.list_handoffs():
            print(f"{h['created_at'][:19]}  {h['handoff_id']}  {h['ticket_ref']:<12} {h['reason']:<24} trace={h['trace_id']}")
        return 0

    from tier1.service import handle_ticket

    ticket = None
    if args.cmd == "demo":
        seed = args.seed if args.seed is not None else random.SystemRandom().randrange(1_000_000)
        print(f"random draw, seed={seed} (rerun with --seed {seed} to reproduce)")
        with db.get_conn() as conn:
            rows = [dict(r) for r in conn.execute(
                "SELECT * FROM tickets" + (" WHERE kind=?" if args.kind else "") + " ORDER BY ticket_id",
                (args.kind,) if args.kind else ())]
        ticket = random.Random(seed).choice(rows)
        print(f"{ticket['ticket_id']} [{ticket['kind']}] customer={ticket['customer_id']} order={ticket['order_id']}")
        print(f"> {ticket['body']}")
        req = _request_from_ticket(ticket)
    elif args.ticket:
        ticket = db.get_ticket(args.ticket)
        if ticket is None:
            print(f"unknown ticket {args.ticket}", file=sys.stderr)
            return 2
        print(f"> {ticket['body']}")
        req = _request_from_ticket(ticket)
    elif args.text:
        req = TicketRequest(body=args.text, subject=args.subject, customer_id=args.customer, order_id=args.order)
    else:
        print("give --ticket or --text", file=sys.stderr)
        return 2

    resp = handle_ticket(req)
    if getattr(args, "json", False):
        print(json.dumps(resp.to_dict(), indent=2))
    else:
        _print_result(resp, ticket)
    return 0


if __name__ == "__main__":
    sys.exit(main())
