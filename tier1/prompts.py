"""System prompt and user message for the Tier-1 agent. The texts are versioned prompts in the catalog
(Admin, Prompts): tier1.rules, tier1.error_code_rule, tier1.prefetch_note and tier1.user_message."""
from agent.prompting import tool_section
from src.catalog import prompts
from tier1.flags import ablated


def system_prompt(schemas: list[dict], prefetched: bool = False) -> str:
    rule = "" if ablated("error_code_prompt") else prompts.body("tier1.error_code_rule")
    rules = prompts.render("tier1.rules", error_code_rule=rule)
    note = ("\n\n" + prompts.body("tier1.prefetch_note")) if prefetched else ""
    return rules + note + "\n\nTOOLS\n" + tool_section(schemas)


def user_message(subject: str, body: str, customer_id: str, order_id: str, ticket_id: str) -> str:
    context = [f"ticket_id: {ticket_id or 'n/a'}", f"customer_id: {customer_id or 'unknown'}"]
    if order_id:
        context.append(f"order_id: {order_id}")
    return prompts.render("tier1.user_message", context="\n".join(context), subject=subject, body=body)
