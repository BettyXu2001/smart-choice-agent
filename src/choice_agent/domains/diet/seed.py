from __future__ import annotations

import csv
import json
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from choice_agent.db_models import MealRecord, SlotOptionRecord


SEED_SQL = Path(__file__).with_name("data") / "legacy_diet_db.sql"


def _rows(table: str) -> list[list[str]]:
    prefix = f"INSERT INTO `{table}` VALUES ("
    rows: list[list[str]] = []
    for line in SEED_SQL.read_text(encoding="utf-8-sig").splitlines():
        if not line.startswith(prefix):
            continue
        raw = line[len(prefix) :].removesuffix(");")
        rows.append(next(csv.reader([raw], delimiter=",", quotechar="'", skipinitialspace=True)))
    return rows


def _nullable_int(value: str) -> int | None:
    return None if value.upper() == "NULL" else int(value)


def _json_list(value: str) -> list[str]:
    if not value or value.upper() == "NULL":
        return []
    parsed = json.loads(value.replace(r'\"', '"'))
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def seed_legacy_data(db: Session) -> None:
    if db.scalar(select(func.count()).select_from(SlotOptionRecord)) == 0:
        for row in _rows("diet_slot_option"):
            db.add(
                SlotOptionRecord(
                    id=int(row[0]),
                    slot_name=row[1],
                    option_value=row[2],
                    sort_order=int(row[3]),
                    enabled=int(row[4]),
                )
            )

    if db.scalar(select(func.count()).select_from(MealRecord)) == 0:
        for row in _rows("meal_item"):
            db.add(
                MealRecord(
                    id=int(row[0]),
                    source_type=row[1],
                    owner_user_id=_nullable_int(row[2]),
                    name=row[3],
                    meal_time=_json_list(row[4]),
                    mood=_json_list(row[5]),
                    scene=_json_list(row[6]),
                    health_goal=_json_list(row[7]),
                    cuisine=_json_list(row[8]),
                    taste=_json_list(row[9]),
                    convenience=_json_list(row[10]),
                )
            )
    db.commit()
