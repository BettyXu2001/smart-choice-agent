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

    assert "评分字段覆盖" in conversation
    assert "结论稳健度" in conversation
    assert "不是成功率或模型置信度" in conversation
    assert "补充这个信息" in conversation
    assert "decisionOutcomeReviewForm" in app
    assert "待复盘实际结果" in app
    assert "saveOutcomeReview" in api
    assert "clearOutcomeReview" in api


def test_trace_management_exports_full_trace_data_and_uses_readable_labels():
    app = (STATIC_JS / "app.js").read_text(encoding="utf-8")
    trace = (STATIC_JS / "trace.js").read_text(encoding="utf-8")

    assert "trace-workbench" in app
    assert "data-action=\"export-trace\"" in app
    assert "data-action=\"export-session\"" in app
    assert "await DietApi.getTrace(selected.traceId)" in app
    assert "await DietApi.listSessionTraces(selected.sessionId, limit)" in app
    assert "limit = 1000" in app
    assert "downloadTextFile(`trace-${safeFilePart(trace.traceId)}-${exportDatePart()}.${ext}`" in app
    assert "downloadTextFile(`session-${safeFilePart(selected.sessionId)}-${exportDatePart()}.${ext}`" in app

    assert "MEAL_RECOMMENDATION: \"餐食推荐\"" in trace
    assert "IntentAgent: \"意图识别\"" in trace
    assert 'status === "failed" || status === "fallback"' in trace
    assert "exportTraceJson" in trace
    assert "exportSessionMarkdown" in trace
    assert "sortTracesChronologically" in trace
    assert 'tool: "工具调用"' in trace
    assert "function toolName(node)" in trace
    assert "function parentNodeLabel(node, nodes)" in trace
    assert "父节点：" in trace
    assert "工具：" in trace


def test_run_mode_is_persistent_in_chat_and_trace_exports():
    api = (STATIC_JS / "api.js").read_text(encoding="utf-8")
    app = (STATIC_JS / "app.js").read_text(encoding="utf-8")
    conversation = (STATIC_JS / "conversation.js").read_text(encoding="utf-8")
    trace = (STATIC_JS / "trace.js").read_text(encoding="utf-8")

    assert "function configuredRunMode" in api
    assert "function resolveRunMode" in app
    assert '已切换至 ${runModeLabel(nextMode)} 模式' in app
    assert "demoNoticeGenerations" in conversation
    assert 'class="run-mode-badge"' in conversation
    assert "当前为 Demo 模式，部分推荐结果或工具调用为模拟数据。" in conversation
    assert 'role="status"' in conversation
    assert "json.run_mode" in trace
    assert "运行模式" in trace
    assert "- Run Mode:" in trace


def test_formal_general_decision_uses_auto_search_when_configured():
    source = (STATIC_JS / "app.js").read_text(encoding="utf-8")
    submit = source[source.index("async function submitGeneralDecision") : source.index("function handleSubmit")]

    assert 'const searchMode = searchConfigured ? "auto" : "fixture";' in submit
    assert '{searchMode, onProgress:' in submit
    assert 'searchMode: realtime ? "web" : "fixture"' not in submit


def test_workflow_canvas_explains_ai_rule_and_source_boundaries():
    conversation = (STATIC_JS / "conversation.js").read_text(encoding="utf-8")
    app = (STATIC_JS / "app.js").read_text(encoding="utf-8")

    assert "function renderWorkflowSummary" in conversation
    assert "流程阶段" in conversation
    assert "executionModeView" in conversation
    assert "规则过滤" in conversation
    assert "模型、规则和数据怎么分工" in conversation
    assert "规则降级" in conversation
    assert "确定性规则" in conversation
    assert "演示数据用于体验流程" in conversation
    assert "processBoundaryNotice" in app
    assert "process-owner" in app


def test_preference_focus_and_candidate_exclusion_reasons_are_visible():
    app = (STATIC_JS / "app.js").read_text(encoding="utf-8")
    conversation = (STATIC_JS / "conversation.js").read_text(encoding="utf-8")
    candidate = app[app.index("function renderGenericCandidate") : app.index("function renderDemoWorkbench")]
    funnel = app[app.index("function renderCandidateFunnel") : app.index("function renderGenericCandidate")]

    assert "function renderPreferenceFocus" in app
    assert "当前偏好重点" in app
    assert "权重 ${Number(item.weight || 0).toFixed(1)}" in app
    assert "function candidateStatusText" in app
    assert "candidate.eliminationReasons" in app
    assert "candidateState" in app
    assert "excluded-summary" in funnel
    assert "candidateStatusText(candidate, decision)" in candidate
    assert "renderPreferenceFocus(d, changeText)" in conversation
    assert "更看重${item.label}" in conversation
    assert "预算提高到 ${relaxedBudget} 会怎样？" in conversation
    assert 'kind: "what_if"' in conversation
    assert 'data-diet-action="open-details"' in conversation
    assert 'href="#generalDetailsPanel"' not in conversation
    assert "renderStructuredClarification" in conversation
    assert 'data-diet-action="adopt-what-if"' in conversation


def test_demo_entry_describes_fixture_flow_and_service_requirement():
    app = (STATIC_JS / "app.js").read_text(encoding="utf-8")
    demo = app[app.index("function renderDemoWorkbench") : app.index("async function startDemoChat")]
    start = app[app.index("async function startDemoChat") : app.index("function renderDemoConstraintInput")]

    assert "后端 fixture · 无需 LLM Key" in demo
    assert "用 fixture 跑真实流程" in demo
    assert "需要本地服务运行" in demo
    assert "未配置、不可用或校验失败时由规则降级" in demo
    assert "请确认本地服务正在运行" in start


def test_new_diet_conversation_defaults_to_public_source():
    app = (STATIC_JS / "app.js").read_text(encoding="utf-8")
    conversation = (STATIC_JS / "conversation.js").read_text(encoding="utf-8")

    assert 'sourceMode: "PUBLIC"' in app
    prepare = conversation[
        conversation.index("function prepareChatFromHome"):
        conversation.index("function triggerPendingPrompt")
    ]
    assert 'state.chat.sourceMode = "PUBLIC"' in prepare
    assert 'state.chat.sourceMode = "PERSONAL"' not in prepare


def test_diet_card_labels_expressed_condition_score_and_keeps_zero_visible():
    source = (STATIC_JS / "app.js").read_text(encoding="utf-8")
    card = source[source.index("function renderMealCard") : source.index("async function ensurePersonalMeals")]

    assert "条件匹配" in card
    assert "仅计算本轮已表达条件" in card
    assert "meal.matchScore != null" in card
    assert "meal.matchScore ?" not in card


def test_diet_quick_message_reuses_single_submit_path():
    source = (STATIC_JS / "app.js").read_text(encoding="utf-8")
    handler = source[
        source.index('} else if (action === "quick-message")'):
        source.index('} else if (action === "feedback")')
    ]

    assert "state.chat.draft = input.value" in handler
    assert "conversation.submitChat(input.form)" in handler
    assert handler.count("conversation.submitChat") == 1
    assert "DietApi" not in handler


def test_chat_submission_immediately_shows_message_and_clears_composer():
    source = (STATIC_JS / "conversation.js").read_text(encoding="utf-8")
    send = source[
        source.index("async function sendChatMessage"):
        source.index("async function submitChat")
    ]
    operation = source[
        source.index("async function runDietOperation"):
        source.index("function sendDietCommand")
    ]

    assert 'state.chat.messages = [...state.chat.messages, {role: "user", text' in send
    assert 'state.chat.draft = ""' in send
    assert send.index('state.chat.draft = ""') < send.index("await runDietOperation")
    assert "pendingRequestId: requestId" in send
    assert "message.pendingRequestId !== operation.body.requestId" in operation
    assert "state.chat.draft = operation.body.message" in operation
    assert "state.chat.draft.trim() === operation.body.message" not in operation
