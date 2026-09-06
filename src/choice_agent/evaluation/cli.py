from __future__ import annotations

import argparse
import json

from choice_agent.config import Settings
from choice_agent.database import Database
from choice_agent.domains.diet.seed import seed_legacy_data
from choice_agent.evaluation.schemas import EvaluationRunCreate
from choice_agent.evaluation.service import EvaluationService
from choice_agent.providers.model import DisabledProvider


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Choice Agent regression evaluation.")
    parser.add_argument("--user-id", type=int, default=1)
    parser.add_argument("--dataset-id")
    parser.add_argument("--version-label", default="cli")
    parser.add_argument("--mode", choices=["fixture", "historical", "live_model"], default="fixture")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--repeat", type=int, default=1)
    args = parser.parse_args()

    settings = Settings.from_env()
    database = Database(settings)
    database.create_all()
    with database.session_factory() as db:
        seed_legacy_data(db)
        run = EvaluationService(db, settings=settings, provider=DisabledProvider()).create_run(
            args.user_id,
            EvaluationRunCreate(
                dataset_id=args.dataset_id,
                version_label=args.version_label,
                mode=args.mode,
                limit=args.limit,
                repeat=args.repeat,
            ),
        )
    print(json.dumps(run, ensure_ascii=False, indent=2))
    counts = run.get("summary", {}).get("caseCounts", {})
    return 1 if counts.get("failed") or counts.get("error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
