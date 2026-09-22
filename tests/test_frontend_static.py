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


def test_recommendation_feedback_is_wired_to_versioned_conversation_flow():
    app = (STATIC_JS / "app.js").read_text(encoding="utf-8")
    conversation = (STATIC_JS / "conversation.js").read_text(encoding="utf-8")

    assert 'renderMealCard(meal, { compact: true, sessionId: message.sessionId })' in app
    assert "conversation.sendFeedback(target)" in app
    assert 'kind: "feedback"' in conversation
    assert "requestId: crypto.randomUUID()" in conversation
    assert "expectedRevision: state.chat.decision.revision" in conversation
    assert "await DietApi.saveFeedback(operation.body)" in conversation
    assert 'feedbackRound.status !== "adopted"' in conversation
    assert "likedCandidateIds" in app
    assert "已采纳，本轮推荐已结束" in app


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


def test_general_details_has_only_one_recommendation_card():
    source = (STATIC_JS / "app.js").read_text(encoding="utf-8")
    details = source[source.index("function renderGeneralDetails") : source.index("function sendGenericCommand")]

    assert details.count("${renderDecisionResultCard(decision, primaryName)}") == 1
    assert "demo-recommendation" not in details


def test_general_details_reuses_complete_domain_labels():
    source = (STATIC_JS / "app.js").read_text(encoding="utf-8")
    demo = (STATIC_JS / "demo.js").read_text(encoding="utf-8")
    index = (STATIC_JS.parents[1] / "index.html").read_text(encoding="utf-8")
    details = source[source.index("function renderGeneralDetails") : source.index("function sendGenericCommand")]
    labels = demo[demo.index("const domainLabels") : demo.index("function nowIso")]

    assert "ChoiceAgentDemo.domainLabels[decision.domain] || decision.domain" in details
    assert "const labels =" not in details
    for key, label in {"career": "职业选择", "learning": "学习路径", "diet": "饮食决策"}.items():
        assert f'{key}: "{label}"' in labels
    assert index.index("assets/js/demo.js") < index.index("assets/js/app.js")


def test_candidate_fields_use_criteria_labels_units_and_key_fallback():
    source = (STATIC_JS / "app.js").read_text(encoding="utf-8")
    candidate = source[source.index("function renderGenericCandidate") : source.index("function renderDemoWorkbench")]

    assert "item.key === key" in candidate
    assert "criterion.key === item.criterionKey" in candidate
    assert "escapeHtml(criterion?.label || key)" in candidate
    assert "escapeHtml(criterion?.label || item.criterionKey)" in candidate
    assert 'criterion?.unit || ""' in candidate
    assert "escapeHtml(unit)" in candidate
    assert 'value != null && value !== ""' in candidate
    assert "escapeHtml(key)</strong>" not in candidate
    assert "${escapeHtml(item.criterionKey)}" not in candidate


def test_general_details_preserves_candidate_weight_and_evidence_controls():
    source = (STATIC_JS / "app.js").read_text(encoding="utf-8")
    details = source[source.index("function renderGeneralDetails") : source.index("function sendGenericCommand")]
    candidate = source[source.index("function renderGenericCandidate") : source.index("function renderDemoWorkbench")]

    assert 'excluded ? "restore_candidate" : "exclude_candidate"' in candidate
    assert 'data-candidate-id="${escapeHtml(candidate.candidateId)}"' in candidate
    assert "sendGenericCommand(button.dataset.candidateAction, { candidateId: button.dataset.candidateId })" in details
    assert 'data-weight="${escapeHtml(item.key)}"' in details
    assert 'sendGenericCommand("set_criterion_weight", { criterionKey: input.dataset.weight, weight: Number(input.value) })' in details
    assert '<details class="evidence-details"><summary>查看候选依据</summary>${window.EvidenceView.candidate(evidence)}</details>' in candidate


def test_decision_quality_and_outcome_review_are_wired_to_user_ui():
    conversation = (STATIC_JS / "conversation.js").read_text(encoding="utf-8")
    app = (STATIC_JS / "app.js").read_text(encoding="utf-8")
    api = (STATIC_JS / "api.js").read_text(encoding="utf-8")

    assert "数据完整度" in conversation
    assert "结论稳健度" in conversation
    assert "不是 AI 正确概率" in conversation
    assert "补充这个信息" in conversation
    assert "decisionOutcomeReviewForm" in app
    assert "待复盘实际结果" in app
    assert "saveOutcomeReview" in api
    assert "clearOutcomeReview" in api
