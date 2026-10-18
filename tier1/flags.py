"""Test seams for before/after measurement. They exist so the eval can switch OFF a defence and show
what the number was without it. Never set TIER1_ABLATE in production.

TIER1_ABLATE is a comma-separated list:
  version_filter  the help-centre server ignores policy_version, so both refund policies are searchable
  policy_guard    the post-guard stops checking the cited policy version and the stated window
  macro_filter    internal Zendesk macros become searchable again for customer-facing answers
  error_code_prompt  the prompt stops telling the model to put the ticket's error code in its search query
  prefetch        code stops making the entitlement check and first search before lap 1 (the model makes them)
"""
import os


def ablated(name: str) -> bool:
    return name in {p.strip() for p in os.getenv("TIER1_ABLATE", "").split(",") if p.strip()}
