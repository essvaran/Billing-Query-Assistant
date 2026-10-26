"""In-app Help: one guide, filtered by role, delivered as typed blocks (never HTML)."""
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import help_router
from api.auth import UserOut, get_current_user


def _client(role):
    app = FastAPI()
    app.include_router(help_router.router)
    app.dependency_overrides[get_current_user] = lambda: UserOut(email=f"{role}@example.com", role=role)
    return TestClient(app)


def test_customers_see_only_their_sections_and_admins_see_all():
    user = _client("user").get("/api/help").json()
    admin = _client("admin").get("/api/help").json()
    user_titles = [s["title"] for s in user["sections"]]
    admin_titles = [s["title"] for s in admin["sections"]]
    assert "Start here" in user_titles and "Troubleshooting" in user_titles
    assert any(t.startswith("Customers") for t in user_titles)
    assert not any(t.startswith(("Support agents", "Team leads", "Operators")) for t in user_titles)
    assert set(user_titles) < set(admin_titles)
    assert any(t.startswith("Operators") for t in admin_titles)


def test_customer_sections_carry_no_operator_or_developer_detail():
    """The customer's Help page explains the product; setup, tooling and test steps are for the team."""
    user = _client("user").get("/api/help").json()
    text = json.dumps(user["sections"]).lower()
    for internal in (".env", "mcp", "tier1_demo_customer_id", "uses quota", "api key", "trace"):
        assert internal not in text, internal


def test_blocks_are_typed_and_carry_no_html():
    sections = _client("admin").get("/api/help").json()["sections"]
    kinds = {b["type"] for s in sections for b in s["blocks"]}
    assert {"paragraph", "list", "table", "code", "heading"} <= kinds
    assert "<!--" not in json.dumps(sections)


def test_parser_handles_lists_continuations_tables_and_code():
    lines = ["Intro line one", "continues here.", "", "1. First step", "   wraps on.", "2. Second", "",
             "| A | B |", "|---|---|", "| 1 | 2 |", "", "```bash", "make up", "```", "- bullet"]
    blocks = help_router.parse_blocks(lines)
    assert blocks[0] == {"type": "paragraph", "text": "Intro line one continues here."}
    assert blocks[1] == {"type": "list", "ordered": True, "items": ["First step wraps on.", "Second"]}
    assert blocks[2] == {"type": "table", "header": ["A", "B"], "rows": [["1", "2"]]}
    assert blocks[3] == {"type": "code", "text": "make up"}
    assert blocks[4]["items"] == ["bullet"]


def test_roles_comment_is_read_and_missing_guide_is_a_clear_404(tmp_path, monkeypatch):
    guide = tmp_path / "g.md"
    guide.write_text("# T\n\n## Everyone\n\nHi.\n\n## Leads\n\n<!-- roles: admin -->\n\nSecret ops.\n", encoding="utf-8")
    title, sections = help_router.load_sections(guide)
    assert title == "T" and [s["roles"] for s in sections] == [["user", "admin"], ["admin"]]
    monkeypatch.setattr(help_router, "GUIDE", tmp_path / "missing.md")
    assert _client("user").get("/api/help").status_code == 404


def test_image_names_are_whitelisted():
    c = _client("user")
    assert c.get("/api/help/img/..%2Fsecret.png").status_code in (400, 404)
    assert c.get("/api/help/img/Bad Name.png").status_code == 400


def test_the_guide_is_plain_ascii():
    text = help_router.GUIDE.read_text(encoding="utf-8")
    bad = sorted({ch for ch in text if ord(ch) > 126})
    assert not bad, f"non-ASCII characters in the guide: {bad}"
