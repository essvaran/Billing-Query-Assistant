"""Model prices (USD per 1M tokens), read from the catalog. 'default' prices any model that is not listed."""
from src.catalog import db


class PriceError(ValueError):
    pass


def _load() -> dict:
    with db.connect() as conn:
        return {r["model"]: dict(r) for r in conn.execute("SELECT * FROM model_prices ORDER BY model")}


def all_prices() -> list[dict]:
    return list(db.cached("prices", _load).values())


def for_model(model: str) -> dict:
    table = db.cached("prices", _load)
    return table.get(model) or table.get("default") or {"input_per_1m": 0.0, "output_per_1m": 0.0}


def upsert(model: str, input_per_1m: float, output_per_1m: float, source: str, checked_on: str, actor: str, create: bool) -> dict:
    model = model.strip()
    if not model:
        raise PriceError("model is required")
    if input_per_1m < 0 or output_per_1m < 0:
        raise PriceError("prices cannot be negative")
    table = db.cached("prices", _load)
    if create and model in table:
        raise PriceError(f"{model} already has a price")
    if not create and model not in table:
        raise PriceError(f"no price for {model}")
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO model_prices(model, input_per_1m, output_per_1m, source, checked_on, updated_at, updated_by) "
            "VALUES (?,?,?,?,?,datetime('now'),?) ON CONFLICT(model) DO UPDATE SET input_per_1m=excluded.input_per_1m, "
            "output_per_1m=excluded.output_per_1m, source=excluded.source, checked_on=excluded.checked_on, "
            "updated_at=excluded.updated_at, updated_by=excluded.updated_by",
            (model, input_per_1m, output_per_1m, source, checked_on, actor))
        db.log_change(conn, actor, "model_price", model, "create" if create else "update", table.get(model),
                      {"input_per_1m": input_per_1m, "output_per_1m": output_per_1m})
    return for_model(model)


def delete(model: str, actor: str) -> None:
    table = db.cached("prices", _load)
    if model not in table:
        raise PriceError(f"no price for {model}")
    if model == "default":
        raise PriceError("the default price is required: it prices any model that is not listed")
    with db.connect() as conn:
        conn.execute("DELETE FROM model_prices WHERE model=?", (model,))
        db.log_change(conn, actor, "model_price", model, "delete", table[model], None)
