"""Reference lists (reason codes, statuses, regions, policy versions, ...), read from the catalog.

Code keeps using the CODES (they are what logic branches on); everything a person reads (labels, descriptions,
customer messages, policy windows) comes from here, and admins edit it in the app.
"""
import json

from src.catalog import db


class RefError(ValueError):
    pass


def _load() -> dict:
    with db.connect() as conn:
        cats = {r["category"]: {"category": r["category"], "label": r["label"], "description": r["description"],
                                "codes_editable": bool(r["codes_editable"]), "meta_schema": json.loads(r["meta_schema"]),
                                "default_meta": json.loads(r["default_meta"]), "values": []}
                for r in conn.execute("SELECT * FROM ref_categories ORDER BY label")}
        for r in conn.execute("SELECT * FROM ref_values ORDER BY category, sort_order, code"):
            if r["category"] in cats:
                c = cats[r["category"]]
                c["values"].append({"code": r["code"], "label": r["label"], "description": r["description"],
                                    "sort_order": r["sort_order"], "active": bool(r["active"]), "system": bool(r["system"]),
                                    "meta": {**c["default_meta"], **json.loads(r["meta"])},
                                    "meta_raw": json.loads(r["meta"]),
                                    "updated_at": r["updated_at"], "updated_by": r["updated_by"]})
    return cats


def all_categories() -> dict:
    return db.cached("ref", _load)


def category(name: str) -> dict:
    cat = all_categories().get(name)
    if cat is None:
        raise RefError(f"unknown reference category {name!r}")
    return cat


def values(name: str, include_inactive: bool = False) -> list[dict]:
    return [v for v in category(name)["values"] if include_inactive or v["active"]]


def codes(name: str, include_inactive: bool = False) -> list[str]:
    return [v["code"] for v in values(name, include_inactive)]


def get(name: str, code: str) -> dict | None:
    return next((v for v in category(name)["values"] if v["code"] == code), None)


def label(name: str, code: str | None, default: str | None = None) -> str:
    v = get(name, code) if code is not None else None
    return v["label"] if v else (default if default is not None else (code or ""))


def meta(name: str, code: str, key: str, default=None):
    v = get(name, code)
    return v["meta"].get(key, default) if v else default


def is_valid(name: str, code: str) -> bool:
    return code in codes(name)


def require(name: str, code: str) -> str:
    """For request validation: the code must be an ACTIVE value of the list."""
    if not is_valid(name, code):
        raise RefError(f"{code!r} is not one of {codes(name)}")
    return code


# --- writes (admin) --------------------------------------------------------------------------------

def upsert(name: str, code: str, fields: dict, actor: str, create: bool) -> dict:
    cat = category(name)
    code = code.strip()
    if not code:
        raise RefError("code is required")
    current = get(name, code)
    if create:
        if current:
            raise RefError(f"{name} already has {code!r}")
        if not cat["codes_editable"]:
            raise RefError(f"{cat['label']}: codes are fixed by the application; edit labels instead")
    elif current is None:
        raise RefError(f"{name} has no {code!r}")
    if current and current["system"] and fields.get("active") is False:
        raise RefError(f"{code!r} is used by the application and cannot be switched off")
    meta_in = fields.get("meta")
    if meta_in is not None:
        _check_meta(cat, meta_in)
    row = {
        "label": (fields.get("label") if fields.get("label") is not None else (current or {}).get("label") or "").strip(),
        "description": fields.get("description") if fields.get("description") is not None else (current or {}).get("description", ""),
        "sort_order": int(fields["sort_order"]) if fields.get("sort_order") is not None else
                      (current or {}).get("sort_order", (len(cat["values"]) + 1) * 10),
        "active": int(fields["active"]) if fields.get("active") is not None else int((current or {}).get("active", True)),
        "meta": json.dumps(meta_in if meta_in is not None else (current or {}).get("meta_raw", {})),
    }
    if not row["label"]:
        raise RefError("label is required")
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO ref_values(category, code, label, description, sort_order, active, system, meta, updated_at, updated_by) "
            "VALUES (?,?,?,?,?,?,0,?,datetime('now'),?) ON CONFLICT(category, code) DO UPDATE SET label=excluded.label, "
            "description=excluded.description, sort_order=excluded.sort_order, active=excluded.active, meta=excluded.meta, "
            "updated_at=excluded.updated_at, updated_by=excluded.updated_by",
            (name, code, row["label"], row["description"], row["sort_order"], row["active"], row["meta"], actor))
        db.log_change(conn, actor, f"ref:{name}", code, "create" if create else "update", current, row)
    return get(name, code)


def delete(name: str, code: str, actor: str, in_use: int = 0) -> None:
    cat = category(name)
    current = get(name, code)
    if current is None:
        raise RefError(f"{name} has no {code!r}")
    if current["system"] or not cat["codes_editable"]:
        raise RefError(f"{code!r} is used by the application and cannot be deleted; you can relabel it")
    if in_use:
        raise RefError(f"{code!r} is still used by {in_use} record(s); switch it off instead of deleting it")
    with db.connect() as conn:
        conn.execute("DELETE FROM ref_values WHERE category=? AND code=?", (name, code))
        db.log_change(conn, actor, f"ref:{name}", code, "delete", current, None)


def _check_meta(cat: dict, meta_in: dict) -> None:
    if not isinstance(meta_in, dict):
        raise RefError("meta must be an object")
    schema = cat["meta_schema"]
    for key, value in meta_in.items():
        spec = schema.get(key)
        if spec is None:
            raise RefError(f"{cat['label']} has no field {key!r}")
        kind = spec.get("type")
        ok = (kind == "text" and isinstance(value, str)) or \
             (kind == "int" and isinstance(value, int) and not isinstance(value, bool)) or \
             (kind == "bool" and isinstance(value, bool)) or \
             (kind == "list" and isinstance(value, list) and all(isinstance(x, str) for x in value))
        if not ok:
            raise RefError(f"{spec.get('label', key)} must be a {kind}")
