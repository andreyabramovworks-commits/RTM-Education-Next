"""Preview or run the one-time catalogue import from a private Sheet snapshot."""

import argparse
import json
from pathlib import Path

from sqlalchemy import select

from app.catalog_import import apply_catalog, plan_catalog
from app.db import SessionLocal
from app.models import Employee


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--actor-bitrix-id", type=int, default=36)
    args = parser.parse_args()
    plan = plan_catalog(json.loads(args.snapshot.read_text(encoding="utf-8")))
    kinds = {kind: sum(article.source_kind == kind for article in plan.articles)
             for kind in ("document", "spreadsheets")}
    print(json.dumps({"folders": len(plan.folders), "articles": len(plan.articles),
                      "kinds": kinds, "skipped": len(plan.skipped)}, ensure_ascii=False))
    if not args.apply:
        return
    if SessionLocal is None:
        raise RuntimeError("Database is not configured")
    with SessionLocal() as db:
        actor = db.scalar(select(Employee).where(Employee.bitrix_id == args.actor_bitrix_id))
        if actor is None or actor.effective_role != "developer":
            raise RuntimeError("Developer account must sign in before import")
        print(json.dumps(apply_catalog(db, plan, actor), ensure_ascii=False))


if __name__ == "__main__":
    main()
