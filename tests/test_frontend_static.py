from pathlib import Path


STATIC_JS = Path(__file__).resolve().parents[1] / "src" / "choice_agent" / "static" / "assets" / "js"


def test_candidate_funnel_uses_ranking_counts():
    source = (STATIC_JS / "app.js").read_text(encoding="utf-8")
    funnel = source[source.index("function renderCandidateFunnel") : source.index("function renderGenericCandidate")]

    assert "decision.domainState?.rankingCounts" in funnel
    assert "rankingCounts.hardConstraintExcluded" in funnel
    assert "rankingCounts.userExcluded" in funnel
    assert "rankingCounts.missingDataExcluded" in funnel
    assert "rankingCounts.remaining" in funnel
    assert "foundCount - activeCandidates.length" not in funnel
    assert "excludedCount" not in funnel


def test_quick_followups_are_contextual_not_fixed_growth_prompt():
    source = (STATIC_JS / "conversation.js").read_text(encoding="utf-8")

    assert "如果更看重成长呢？" not in source
    assert "function buildQuickFollowupPrompts" in source
    assert "decision?.criteria" in source
    assert "为什么不选 ${firstAlternative.name}？" in source


def test_revision_only_visible_in_developer_or_trace_views():
    app_source = (STATIC_JS / "app.js").read_text(encoding="utf-8")
    trace_source = (STATIC_JS / "trace.js").read_text(encoding="utf-8")

    assert "第 ${escapeHtml(decision.revision" not in app_source
    assert "第 ${escapeHtml(decision.revision ??" not in app_source
    assert "<strong>Revision</strong>" in app_source
    assert "<span>Revision</span>" in trace_source

def test_general_decision_process_visualization_is_user_facing():
    source = (STATIC_JS / "app.js").read_text(encoding="utf-8")

    assert "function renderHomeDecisionProcess" in source
    assert "Choice Agent 决策流程" in source
    assert "function buildDecisionProcess" in source
    assert "function renderDecisionProcess" in source
    assert "这次决策是怎么走到结论的" in source
    assert "function renderDecisionResultCard" in source
    assert "什么会改变结论" in source
    assert "candidate-compare-card" in source
    assert "score-breakdown" in source
