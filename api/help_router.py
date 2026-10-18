"""In-app Help: serves FUNCTIONAL_README.md, the one source of truth, filtered to the caller's role.

Each `## ` section of the guide may carry a comment line right under its heading:
    <!-- roles: user, admin -->
Sections without one are shown to everybody. Admins see every section.

The Markdown is parsed here into simple typed blocks (heading, paragraph, list, code, table, image), never HTML, so
the page renders it with plain text bindings and nothing in the guide can inject markup.
"""
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from api.auth import UserOut, get_current_user
from src.config import PROJECT_ROOT

router = APIRouter(prefix="/api/help", tags=["help"])

GUIDE = PROJECT_ROOT / "FUNCTIONAL_README.md"
IMG_DIR = PROJECT_ROOT / "docs" / "img"
_ROLES = re.compile(r"^<!--\s*roles:\s*([a-z, ]+)\s*-->$")
_IMG = re.compile(r"^!\[([^\]]*)\]\((?:img/)?([a-z0-9_-]+\.png)\)$")
_IMG_NAME = re.compile(r"^[a-z0-9_-]+\.png$")
_ORDERED = re.compile(r"^\d+\.\s+")


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def parse_blocks(lines: list[str]) -> list[dict]:
    blocks: list[dict] = []
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if not line.strip() or line.strip().startswith("<!--"):
            i += 1
            continue
        if line.startswith("```"):
            body = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                body.append(lines[i].rstrip("\n"))
                i += 1
            blocks.append({"type": "code", "text": "\n".join(body)})
            i += 1
            continue
        if line.startswith("### ") or line.startswith("#### "):
            level = 3 if line.startswith("### ") else 4
            blocks.append({"type": "heading", "level": level, "text": line.lstrip("#").strip()})
            i += 1
            continue
        m = _IMG.match(line.strip())
        if m:
            blocks.append({"type": "image", "alt": m.group(1), "src": f"/api/help/img/{m.group(2)}"})
            i += 1
            continue
        if line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(set(c) <= set("-: ") for c in cells):
                    rows.append(cells)
                i += 1
            blocks.append({"type": "table", "header": rows[0] if rows else [], "rows": rows[1:]})
            continue
        if line.lstrip().startswith(("- ", "* ")) or _ORDERED.match(line.lstrip()):
            ordered = bool(_ORDERED.match(line.lstrip()))
            items: list[str] = []
            while i < len(lines):
                cur = lines[i].rstrip()
                stripped = cur.lstrip()
                if stripped.startswith(("- ", "* ")) or _ORDERED.match(stripped):
                    items.append(_ORDERED.sub("", stripped)[2:] if not _ORDERED.match(stripped) else _ORDERED.sub("", stripped))
                elif cur.startswith("  ") and stripped and items:
                    items[-1] += " " + stripped          # wrapped continuation line of the previous item
                else:
                    break
                i += 1
            blocks.append({"type": "list", "ordered": ordered, "items": items})
            continue
        para = [line.strip()]
        i += 1
        while i < len(lines) and lines[i].strip() and not lines[i].startswith(("#", "|", "```", "- ", "* ", "<!--", "![")) \
                and not _ORDERED.match(lines[i].lstrip()):
            para.append(lines[i].strip())
            i += 1
        blocks.append({"type": "paragraph", "text": " ".join(para)})
    return blocks


def load_sections(path: Path = GUIDE) -> tuple[str, list[dict]]:
    text = path.read_text(encoding="utf-8")
    title = next((ln[2:].strip() for ln in text.splitlines() if ln.startswith("# ")), "User guide")
    sections, current = [], None
    for line in text.splitlines():
        if line.startswith("## "):
            current = {"title": line[3:].strip(), "roles": None, "lines": []}
            sections.append(current)
        elif current is not None:
            m = _ROLES.match(line.strip())
            if m and current["roles"] is None and not any(l.strip() for l in current["lines"]):
                current["roles"] = [r.strip() for r in m.group(1).split(",") if r.strip()]
            else:
                current["lines"].append(line)
    out = [{"id": _slug(s["title"]), "title": s["title"], "roles": s["roles"] or ["user", "admin"],
            "blocks": parse_blocks(s["lines"])} for s in sections]
    return title, out


@router.get("")
def help_for_me(user: UserOut = Depends(get_current_user)):
    if not GUIDE.exists():
        raise HTTPException(404, "The user guide is missing from this installation")
    title, sections = load_sections()
    visible = sections if user.role == "admin" else [s for s in sections if user.role in s["roles"]]
    return {"title": title, "role": user.role, "sections": visible}


@router.get("/img/{name}")
def help_image(name: str):
    """Public on purpose: an <img> tag cannot send the sign-in token, and these are screenshots of synthetic data."""
    if not _IMG_NAME.match(name):
        raise HTTPException(400, "Invalid image name")
    path = IMG_DIR / name
    if not path.exists():
        raise HTTPException(404, "Image not found")
    return FileResponse(path, media_type="image/png")
