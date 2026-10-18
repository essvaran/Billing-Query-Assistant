"""Runtime settings, read from the catalog.

Resolution order for a value: the environment variable named in the setting's `env` field (deployment control), then
the stored value (edited in the app), then the seed default. Secrets never live here; they stay in .env.
"""
import json
import os

from src.catalog import db


class SettingError(ValueError):
    pass


_CAST = {"int": int, "float": float, "str": str, "bool": lambda v: v if isinstance(v, bool) else str(v).lower() in ("1", "true", "yes", "on"),
         "json": lambda v: v}


def _load() -> dict:
    with db.connect() as conn:
        return {r["key"]: dict(r) for r in conn.execute("SELECT * FROM settings ORDER BY group_name, key")}


def _rows() -> dict:
    return db.cached("settings", _load)


def get(key: str):
    row = _rows().get(key)
    if row is None:
        raise SettingError(f"unknown setting {key!r}")
    env_name = row["env"]
    if env_name and os.getenv(env_name, "").strip():
        try:
            return _CAST[row["type"]](os.environ[env_name].strip())
        except (TypeError, ValueError):
            pass
    return _CAST[row["type"]](json.loads(row["value"]))


def describe() -> list[dict]:
    """Every setting with its stored value, the effective value, and whether an environment variable overrides it."""
    out = []
    for key, row in _rows().items():
        env_name = row["env"]
        overridden = bool(env_name and os.getenv(env_name, "").strip())
        out.append({"key": key, "group": row["group_name"], "label": row["label"], "description": row["description"],
                    "type": row["type"], "min": row["min_value"], "max": row["max_value"],
                    "value": json.loads(row["value"]), "default": json.loads(row["default_value"]),
                    "effective": get(key), "env": env_name, "overridden_by_env": overridden,
                    "restart_required": bool(row["restart"]), "updated_at": row["updated_at"], "updated_by": row["updated_by"]})
    return out


def validate(key: str, value):
    row = _rows().get(key)
    if row is None:
        raise SettingError(f"unknown setting {key!r}")
    kind = row["type"]
    try:
        if kind == "int":
            if isinstance(value, bool) or (isinstance(value, float) and not value.is_integer()):
                raise ValueError
            value = int(value)
        elif kind == "float":
            if isinstance(value, bool):
                raise ValueError
            value = float(value)
        elif kind == "bool":
            if not isinstance(value, bool):
                raise ValueError
        elif kind == "str":
            if not isinstance(value, str) or not value.strip():
                raise ValueError
            value = value.strip()
            if key.endswith("as_of") and value.lower() != "today":
                from datetime import date
                date.fromisoformat(value)
    except (TypeError, ValueError):
        raise SettingError(f"{row['label']} must be a {kind}")
    if kind in ("int", "float"):
        if row["min_value"] is not None and value < row["min_value"]:
            raise SettingError(f"{row['label']} must be at least {row['min_value']:g}")
        if row["max_value"] is not None and value > row["max_value"]:
            raise SettingError(f"{row['label']} must be at most {row['max_value']:g}")
    return value


def set(key: str, value, actor: str) -> dict:
    value = validate(key, value)
    before = json.loads(_rows()[key]["value"])
    with db.connect() as conn:
        conn.execute("UPDATE settings SET value=?, updated_at=datetime('now'), updated_by=? WHERE key=?",
                     (json.dumps(value), actor, key))
        db.log_change(conn, actor, "setting", key, "update", before, value)
    return next(s for s in describe() if s["key"] == key)


def reset(key: str, actor: str) -> dict:
    row = _rows().get(key)
    if row is None:
        raise SettingError(f"unknown setting {key!r}")
    return set(key, json.loads(row["default_value"]), actor)
