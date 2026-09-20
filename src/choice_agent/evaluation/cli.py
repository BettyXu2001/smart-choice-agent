from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from pydantic import ValidationError

from choice_agent.config import Settings
from choice_agent.database import Database
from choice_agent.domains.diet.seed import seed_legacy_data
from choice_agent.evaluation.comparison import EvaluationComparisonError
from choice_agent.evaluation.schemas import (
    CURRENT_PROMPT_VERSION,
    CURRENT_RULE_VERSION,
    EvaluationRunConfiguration,
    EvaluationRunCreate,
)
from choice_agent.evaluation.service import EvaluationConfigurationError, EvaluationService
from choice_agent.providers.model import DisabledProvider, OpenAICompatibleProvider


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Choice Agent regression evaluation.")
    parser.add_argument("--user-id", type=int, default=1)
    parser.add_argument("--dataset-id")
    parser.add_argument("--version-label", default="cli")
    parser.add_argument("--mode", choices=["fixture", "historical", "live_model"], default="fixture")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--run-label", choices=["baseline", "candidate"], default="candidate")
    parser.add_argument("--model")
    parser.add_argument("--provider", choices=["configured", "disabled"], default="disabled")
    parser.add_argument("--prompt-version", default=CURRENT_PROMPT_VERSION)
    parser.add_argument("--rule-version", default=CURRENT_RULE_VERSION)
    parser.add_argument("--compare-to-run-id")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.compare_to_run_id and args.run_label != "candidate":
        parser.error("--compare-to-run-id 只能与 --run-label candidate 一起使用")

    settings = Settings.from_env()
    provider = DisabledProvider()
    if args.provider == "configured":
        provider = OpenAICompatibleProvider(settings)
        if not provider.enabled:
            parser.error("configured provider 未启用，请配置模型 API 后重试")

    try:
        run_configuration = EvaluationRunConfiguration(
            model=args.model or settings.main_model,
            provider=args.provider,
            prompt_version=args.prompt_version,
            rule_version=args.rule_version,
            run_label=args.run_label,
        )
    except ValidationError as error:
        parser.error(str(error))
    database = Database(settings)
    database.create_all()
    try:
        with database.session_factory() as db:
            seed_legacy_data(db)
            evaluation = EvaluationService(db, settings=settings, provider=provider)
            run = evaluation.create_run(
                args.user_id,
                EvaluationRunCreate(
                    dataset_id=args.dataset_id,
                    version_label=args.version_label,
                    mode=args.mode,
                    run_configuration=run_configuration,
                    limit=args.limit,
                    repeat=args.repeat,
                ),
            )
            output: dict[str, object] = run
            if args.compare_to_run_id:
                output = {
                    "run": run,
                    "comparison": evaluation.compare_runs(args.user_id, args.compare_to_run_id, run["id"]),
                }
    except (EvaluationConfigurationError, EvaluationComparisonError, KeyError) as error:
        parser.error(str(error))
    print(json.dumps(output, ensure_ascii=False, indent=2))
    counts = run.get("summary", {}).get("caseCounts", {})
    return 1 if counts.get("failed") or counts.get("error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
