"""Prompt helpers that keep the system prompt in sync with discovered MCP tools.

The old agent prompt hardcoded tool names, so runtime discovery changed nothing the
model could see. Here the tool section is generated from the schemas the MCP client
discovered (after the allow-list), so adding or removing a tool needs no prompt edit.
"""


def tool_section(schemas: list[dict]) -> str:
    """Render discovered OpenAI-format tool schemas as a short prompt section."""
    lines = []
    for s in schemas:
        fn = s["function"]
        props = (fn.get("parameters") or {}).get("properties") or {}
        required = set((fn.get("parameters") or {}).get("required") or [])
        args = ", ".join(f"{p}{'' if p in required else '?'}" for p in props)
        first_line = (fn.get("description") or "").strip().split("\n")[0]
        lines.append(f"- {fn['name']}({args}): {first_line}")
    names = ", ".join(s["function"]["name"] for s in schemas)
    return (
        f"You have EXACTLY these tools and no others: {names}.\n"
        "Never call a tool that is not listed.\n" + "\n".join(lines)
    )
