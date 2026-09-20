from choice_agent.evaluation.cli import build_parser
from choice_agent.evaluation.schemas import CURRENT_PROMPT_VERSION, CURRENT_RULE_VERSION


def test_evaluation_cli_preserves_old_defaults():
    args = build_parser().parse_args([])
    assert args.version_label == "cli"
    assert args.mode == "fixture"
    assert args.limit == 20
    assert args.repeat == 1
    assert args.run_label == "candidate"
    assert args.provider == "disabled"


def test_evaluation_cli_accepts_baseline_candidate_configuration():
    args = build_parser().parse_args(
        [
            "--run-label", "baseline",
            "--model", "baseline-model",
            "--provider", "configured",
            "--prompt-version", CURRENT_PROMPT_VERSION,
            "--rule-version", CURRENT_RULE_VERSION,
        ]
    )
    assert args.run_label == "baseline"
    assert args.model == "baseline-model"
    assert args.provider == "configured"
