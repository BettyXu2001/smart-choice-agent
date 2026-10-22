from __future__ import annotations

from choice_agent.evaluation.schemas import EvaluationCaseCreate


CORE_DATASET_V1 = {"name": "core-regression", "version": "v1"}
CORE_DATASET_V2 = {"name": "core-regression", "version": "v2"}
CORE_DATASET = {"name": "core-regression", "version": "v3"}
FAULT_DATASET = {"name": "fault-injection-reliability", "version": "v2"}
DIET_TRAVEL_DATASET = {"name": "diet-travel-evaluation", "version": "v1"}

OFFER = "比较两个 Offer\n以下为演示候选：\nA 公司：AI 产品方向更匹配，成长空间更大，但业务阶段较早；B 公司：平台成熟、薪酬稳定，岗位内容更偏传统产品。"
LEARNING = "选择入门 AI Agent 的学习路径\n以下为演示候选：\n结构化在线课程：路径完整、上手稳定，适合需要系统框架的学习者；开源项目实战：实践反馈快，但需要自行补齐概念和调试能力；文档与论文路线：信息质量高、自由度大，但学习路径容易分散。"


def starter_cases() -> list[EvaluationCaseCreate]:
    return [
        *fault_injection_cases(),
        *core_regression_cases(),
        *core_regression_v2_cases(),
        *core_regression_v3_cases(),
        *diet_travel_evaluation_cases(),
    ]


def starter_dataset_specs() -> list[dict[str, str]]:
    return [
        {**CORE_DATASET_V1, "description": "20 条固定数据源真实 Orchestrator 核心回归 Case（历史 v1）。"},
        {**CORE_DATASET_V2, "description": "20 条 Deterministic Evaluation First 核心回归 Case（历史 v2）。"},
        {**CORE_DATASET, "description": "20 条覆盖路由、澄清、软偏好和安全约束的核心回归 Case。"},
        {**FAULT_DATASET, "description": "受控故障注入可靠性 Case，不等同于 Runtime Bad Cases。"},
        {**DIET_TRAVEL_DATASET, "description": "20 条饮食与旅行专项评测 Case，覆盖核心行为、边界和受控可靠性场景。"},
    ]


def core_regression_cases() -> list[EvaluationCaseCreate]:
    return [
        _case("core-regression-v1.offer-stability", "Offer 稳定优先推荐 B", OFFER, "更看重稳定后，应基于手工候选推荐 B 公司。", [OFFER, "更看重稳定"], [
            _a("intent_accuracy", "decisionState.domain", "equals", "generic"),
            _a("reason_recommendation_consistency", "speechText", "contains", "B 公司"),
            _a("evidence_reference_validity", "decisionState.domainState.assistance.analysis.sources", "non_empty"),
        ], tags=["offer", "recommendation"]),
        _case("core-regression-v1.offer-explain-a", "Offer 追问 A 的取舍解释", OFFER, "追问为什么不选 A 时，应解释 A 的优势和风险，并保持推荐理由一致。", [OFFER, "更看重稳定", "那为什么不选 A 公司？"], [
            _a("reason_recommendation_consistency", "speechText", "includes_all", ["A 公司", "B 公司"]),
            _a("evidence_reference_validity", "decisionState.recommendation.reasons", "non_empty"),
        ], tags=["offer", "explanation"]),
        _case("core-regression-v1.offer-commute-concern", "Offer 通勤顾虑挂载到 B", OFFER, "B 通勤两小时应记录为 B 的候选事实和顾虑，不把事实挂到其他候选。", [OFFER, "更看重稳定", "B 公司通勤每天要两小时，我不太能接受"], [
            _a("constraint_extraction_accuracy", "decisionState.domainState.assistance.facts", "contains", "两小时"),
            _a("constraint_extraction_accuracy", "decisionState.domainState.assistance.facts", "contains", "concern"),
            _a("multi_turn_state_retention", "decisionState.domainState.conversationTurns", "non_empty"),
        ], tags=["offer", "candidate_fact"]),
        _case("core-regression-v1.offer-commute-correction", "Offer 通勤纠正移除旧事实", OFFER, "B 通勤从两小时纠正为半小时后，新事实生效且旧事实移除。", [OFFER, "更看重稳定", "B 公司通勤每天两小时，我不能接受", "纠正一下，B 公司通勤是半小时，可以接受"], [
            _a("correction_update_accuracy", "decisionState.domainState.assistance.facts", "contains", "半小时"),
            _a("correction_update_accuracy", "decisionState.domainState.assistance.facts", "not_contains", "两小时"),
            _a("reason_recommendation_consistency", "speechText", "contains", "B 公司"),
        ], tags=["offer", "correction"]),
        _case("core-regression-v1.offer-commute-hard-limit", "Offer 通勤硬约束排除 B", OFFER, "已知 B 通勤两小时后，最多接受 1 小时通勤应排除 B。", [OFFER, "更看重稳定", "B 公司通勤每天要两小时", "我每天最多接受 1 小时通勤"], [
            _a("hard_constraint_satisfaction", "decisionState.candidateState", "contains", "不满足硬约束"),
            _a("exclusion_correctness", "speechText", "not_contains", "更倾向 B 公司"),
        ], tags=["offer", "hard_constraint"]),
        _case("core-regression-v1.offer-confirm-exclusion", "Offer 确认顾虑后排除候选", OFFER, "用户确认通勤顾虑不能妥协后，应把 B 加入排除集合。", [OFFER, "稳定", "B 公司通勤两小时，我不太能接受", "这是不能妥协的条件"], [
            _a("exclusion_correctness", "decisionState.excludedCandidates", "non_empty"),
            _a("reason_recommendation_consistency", "speechText", "contains", "只剩 A 公司"),
        ], tags=["offer", "exclusion"]),
        _case("core-regression-v1.shopping-budget-8000", "Shopping 预算 8000 生成候选", "买电脑，预算 8000", "购物 fixture 应生成候选、推荐和来源信息。", ["买电脑，预算 8000"], [
            _a("constraint_extraction_accuracy", "decisionState.domainState.conversationFields.budget.value", "equals", 8000),
            _a("recommendation_stability", "decisionState.recommendation.primaryCandidateId", "non_empty"),
            _a("evidence_reference_validity", "decisionState.domainState.source.mode", "equals", "fixture"),
        ], domain="shopping", tags=["shopping", "candidate_search"]),
        _case("core-regression-v1.shopping-budget-7000", "Shopping 预算纠正到 7000", "买电脑，预算 8000", "正式预算改成 7000 后，候选池应反映新预算。", ["买电脑，预算 8000", "预算改成 7000"], [
            _a("correction_update_accuracy", "decisionState.domainState.conversationFields.budget.value", "equals", 7000),
            _a("hard_constraint_satisfaction", "decisionState.candidates", "not_contains", "10999"),
        ], domain="shopping", tags=["shopping", "correction"]),
        _case("core-regression-v1.shopping-what-if-6000", "Shopping what-if 不污染预算", "买电脑，预算 8000", "假设预算 6000 只能产生假设分析，正式预算仍为 8000。", ["买电脑，预算 8000", "如果预算改成 6000 呢？"], [
            _a("what_if_isolation", "decisionState.domainState.conversationFields.budget.value", "equals", 8000),
            _a("what_if_isolation", "decisionState.domainState.assistance.whatIfAnalysis.hypothetical", "equals", True),
        ], domain="shopping", tags=["shopping", "what_if"]),
        _case("core-regression-v1.shopping-what-if-then-official", "Shopping what-if 后正式修改", "买电脑，预算 8000", "what-if 后正式改预算 7000，正式状态才更新。", ["买电脑，预算 8000", "如果预算改成 6000 呢？", "预算改成 7000"], [
            _a("correction_update_accuracy", "decisionState.domainState.conversationFields.budget.value", "equals", 7000),
            _a("what_if_isolation", "decisionState.domainState.assistance.currentAnalysis.hypothetical", "equals", False),
        ], domain="shopping", tags=["shopping", "what_if", "correction"]),
        _case("core-regression-v1.shopping-numeric-evidence", "Shopping 数值比较引用多候选", "买电脑，预算 9000", "数值比较理由应引用多个候选 Evidence。", ["买电脑，预算 9000"], [
            _a("evidence_reference_validity", "decisionState.recommendation.reasons.0.evidenceIds.1", "non_empty"),
            _a("reason_recommendation_consistency", "decisionState.recommendation.tradeoffDetails", "non_empty"),
        ], domain="shopping", tags=["shopping", "evidence"]),
        _case("core-regression-v1.shopping-hard-filter", "Shopping 硬约束过滤超预算", "买电脑，预算 7000", "预算 7000 不应保留超预算创作本作为可推荐候选。", ["买电脑，预算 7000"], [
            _a("hard_constraint_satisfaction", "decisionState.candidates", "not_contains", "creator-16"),
            _a("exclusion_correctness", "decisionState.domainState.rankingCounts.hardConstraintExcluded", "equals", 2),
        ], domain="shopping", tags=["shopping", "hard_constraint"]),
        _case("core-regression-v1.learning-beginner", "Learning 手工候选零基础路径", LEARNING, "显式 Manual Candidates 下，零基础每周三小时应推荐结构化在线课程。", [LEARNING, "零编程基础，每周三小时"], [
            _a("constraint_extraction_accuracy", "decisionState.domainState.conversationFields.weeklyHours.value", "equals", 3),
            _a("reason_recommendation_consistency", "speechText", "contains", "结构化在线课程"),
        ], tags=["learning", "manual_candidates"]),
        _case("core-regression-v1.learning-practice-correction", "Learning 背景纠正后推荐实战", LEARNING, "显式 Manual Candidates 下，已有 Python 且想实践后应切换到开源项目实战。", [LEARNING, "零编程基础，每周三小时", "其实已有 Python 基础，更想动手实践"], [
            _a("correction_update_accuracy", "decisionState.domainState.conversationFields.background.value", "contains", "Python"),
            _a("sensitivity_to_condition_change", "speechText", "contains", "开源项目实战"),
        ], tags=["learning", "manual_candidates", "correction"]),
        _case("core-regression-v1.learning-short-answer", "Learning 短回答承接澄清", LEARNING, "显式 Manual Candidates 下，短回答“有”应承接上一轮编程基础问题。", [LEARNING, "动手实践", "有"], [
            _a("multi_turn_state_retention", "decisionState.domainState.conversationFields.background.value", "contains", "编程基础"),
            _a("reason_recommendation_consistency", "speechText", "not_contains", "有编程基础吗"),
        ], tags=["learning", "manual_candidates", "short_answer"]),
        _case("core-regression-v1.travel-fixture", "Travel fixture 候选推荐", "周末从上海出发两天一夜，不想太累，人少一点", "旅行 fixture 应产生候选、推荐、Evidence 和 Trace。", ["周末从上海出发两天一夜，不想太累，人少一点"], [
            _a("intent_accuracy", "decisionState.domain", "equals", "travel"),
            _a("recommendation_stability", "decisionState.recommendation.primaryCandidateId", "non_empty"),
            _a("evidence_reference_validity", "decisionState.domainState.source.mode", "equals", "fixture"),
        ], domain="travel", tags=["travel", "candidate_search"]),
        _case("core-regression-v1.travel-rain-what-if", "Travel 下雨假设不编造天气", "从上海出发两天一夜", "如果下雨但没有天气或室内资料，不应编造天气并且不改变正式推荐。", ["从上海出发两天一夜", "如果下雨呢？"], [
            _a("unsupported_fact_rate", "speechText", "contains", "没有天气或室内备选资料"),
            _a("what_if_isolation", "decisionState.domainState.assistance.whatIfAnalysis.primaryCandidateId", "equals", None),
        ], domain="travel", tags=["travel", "what_if", "evidence"]),
        _case("core-regression-v1.generic-unknown-text", "Generic 未知自由文本不静默理解", OFFER, "无法整理成比较信息的自由文本应明确反馈，不静默改状态。", [OFFER, "我觉得有一种说不出来的感觉"], [
            _a("intent_accuracy", "speechText", "contains", "还没整理成可比较的信息"),
            _a("multi_turn_state_retention", "decisionState.domainState.assistance.facts", "empty"),
        ], tags=["generic", "clarification"]),
        _case("core-regression-v1.evidence-reason-ids", "Evidence 推荐理由可回溯", OFFER, "推荐理由中的 evidenceIds 均应存在于 decision evidence / sources 快照。", [OFFER, "更看重稳定"], [
            _a("evidence_reference_validity", "decisionState.recommendation.reasons.0.evidenceIds", "non_empty"),
            _a("evidence_reference_validity", "decisionState.domainState.assistance.analysis.sources", "contains", "verificationNote"),
        ], tags=["evidence", "offer"]),
        _case("core-regression-v1.trace-snapshot", "Trace Snapshot 可用", "买电脑，预算 8000", "真实链路运行后应保存 trace id 和非空 trace snapshot。", ["买电脑，预算 8000"], [
            _a("average_response_time_ms", "traceId", "non_empty"),
            _a("agent_execution_failure_rate", "decisionState.traceRefs", "non_empty", required=False),
        ], domain="shopping", tags=["trace", "observability"]),
    ]


def core_regression_v2_cases() -> list[EvaluationCaseCreate]:
    assertions = {
        "offer-stability": [
            _auto("intent_accuracy", {"domain": "generic"}),
            _auto("reason_recommendation_consistency", {"requireReasons": True}),
            _auto("evidence_reference_validity", {"requireReferences": True}),
            _auto("recommendation_stability", {}, required=False),
        ],
        "offer-explain-a": [
            _auto("reason_recommendation_consistency", {"requireReasons": True}),
            _auto("evidence_reference_validity", {"requireReferences": True}),
            _manual("reason_recommendation_consistency", "A/B 取舍解释的充分性需要人工审阅。"),
        ],
        "offer-commute-concern": [
            _auto("constraint_extraction_accuracy", {"checks": [
                {"path": "domainState.assistance.facts", "operator": "contains", "expected": "两小时"},
                {"path": "domainState.assistance.facts", "operator": "contains", "expected": "concern"},
            ]}),
            _auto("multi_turn_state_retention", {"beforeTurn": 1, "afterTurn": 2, "paths": ["domainState.conversationFields"]}, required=False),
        ],
        "offer-commute-correction": [
            _auto("correction_update_accuracy", {
                "beforeTurn": 2,
                "afterTurn": 3,
                "checks": [{"path": "domainState.assistance.facts", "operator": "contains", "expected": "半小时"}],
                "absentChecks": [{"path": "domainState.assistance.facts", "operator": "not_contains", "expected": "两小时"}],
            }),
            _auto("correction_coverage", {"afterTurn": 3, "targets": [
                {"path": "domainState.assistance.facts", "operator": "contains", "expected": "半小时"},
            ]}),
            _manual("reason_recommendation_consistency", "纠正后的自然语言理由质量需要人工审阅。"),
        ],
        "offer-commute-hard-limit": [
            _auto("hard_constraint_satisfaction", {}),
            _auto("excluded_candidate_recommend_rate", {}, required=False),
        ],
        "offer-confirm-exclusion": [
            _auto("exclusion_correctness", {"minimumCount": 1}),
            _auto("excluded_candidate_recommend_rate", {}),
        ],
        "shopping-budget-8000": [
            _auto("constraint_extraction_accuracy", {"checks": [
                {"path": "domainState.conversationFields.budget.value", "operator": "equals", "expected": 8000},
            ]}),
            _auto("reason_recommendation_consistency", {"requireReasons": True}),
            _auto("evidence_reference_validity", {"requireReferences": True}),
            _auto("recommendation_stability", {}, required=False),
        ],
        "shopping-budget-7000": [
            _auto("correction_update_accuracy", {"beforeTurn": 0, "afterTurn": 1, "checks": [
                {"path": "domainState.conversationFields.budget.value", "operator": "equals", "expected": 7000},
            ]}),
            _auto("correction_coverage", {"afterTurn": 1, "targets": [
                {"path": "domainState.conversationFields.budget.value", "operator": "equals", "expected": 7000},
            ]}),
            _auto("hard_constraint_satisfaction", {}),
        ],
        "shopping-what-if-6000": [
            _auto("what_if_isolation", {"beforeTurn": 0, "afterTurn": 1}),
        ],
        "shopping-what-if-then-official": [
            _auto("what_if_isolation", {"beforeTurn": 0, "afterTurn": 1}),
            _auto("correction_update_accuracy", {"beforeTurn": 1, "afterTurn": 2, "checks": [
                {"path": "domainState.conversationFields.budget.value", "operator": "equals", "expected": 7000},
            ]}),
            _auto("correction_coverage", {"afterTurn": 2, "targets": [
                {"path": "domainState.conversationFields.budget.value", "operator": "equals", "expected": 7000},
            ]}),
        ],
        "shopping-numeric-evidence": [
            _auto("evidence_reference_validity", {"requireReferences": True}),
            _auto("reason_recommendation_consistency", {"requireReasons": True}),
        ],
        "shopping-hard-filter": [
            _auto("hard_constraint_satisfaction", {}),
            _a("exclusion_correctness", "decisionState.domainState.rankingCounts.hardConstraintExcluded", "equals", 2),
        ],
        "learning-beginner": [
            _auto("constraint_extraction_accuracy", {"checks": [
                {"path": "domainState.assistance.facts", "operator": "contains", "expected": "零编程基础"},
                {"path": "domainState.assistance.facts", "operator": "contains", "expected": "每周三小时"},
            ]}),
            _manual("reason_recommendation_consistency", "动态事实尚不足以确定学习路径时，不应靠 Generic 场景硬编码强行推荐。"),
        ],
        "learning-practice-correction": [
            _auto("correction_update_accuracy", {"beforeTurn": 1, "afterTurn": 2, "checks": [
                {"path": "domainState.assistance.facts", "operator": "contains", "expected": "Python"},
            ], "absentChecks": [
                {"path": "domainState.assistance.facts", "operator": "not_contains", "expected": "零编程基础"},
            ]}),
            _auto("correction_coverage", {"afterTurn": 2, "targets": [
                {"path": "domainState.assistance.facts", "operator": "contains", "expected": "Python"},
            ]}),
            _auto("sensitivity_to_condition_change", {"beforeTurn": 1, "afterTurn": 2, "mode": "changed"}),
            _manual("reason_recommendation_consistency", "条件变化后推荐语义是否合理需要人工审阅。"),
        ],
        "learning-short-answer": [
            _auto("constraint_extraction_accuracy", {"checks": [
                {"path": "domainState.assistance.facts", "operator": "contains", "expected": "编程基础"},
            ]}),
            _manual("reason_recommendation_consistency", "显式背景补充后的推荐语义需要人工审阅。"),
        ],
        "travel-fixture": [
            _auto("intent_accuracy", {"domain": "travel"}),
            _auto("reason_recommendation_consistency", {"requireReasons": True}),
            _auto("evidence_reference_validity", {"requireReferences": True}),
            _auto("recommendation_stability", {}, required=False),
        ],
        "travel-rain-what-if": [
            _auto("what_if_isolation", {"beforeTurn": 0, "afterTurn": 1}),
            _manual("unsupported_fact_rate", "自然语言天气 claim 的完整支持性需要人工审阅。"),
        ],
        "generic-unknown-text": [
            _auto("multi_turn_state_retention", {
                "beforeTurn": 0,
                "afterTurn": 1,
                "paths": ["constraints", "excludedCandidates", "recommendation.primaryCandidateId"],
            }),
            _manual("intent_accuracy", "无法结构化的自由文本意图需要人工审阅。"),
        ],
        "evidence-reason-ids": [
            _auto("evidence_reference_validity", {"requireReferences": True}),
            _auto("reason_recommendation_consistency", {"requireReasons": True}),
        ],
        "trace-snapshot": [
            _auto("intent_accuracy", {"domain": "shopping"}),
            _auto("agent_execution_failure_rate", {"maximumRate": 0}, required=False),
        ],
    }
    cases = []
    for item in core_regression_cases():
        payload = item.model_dump(mode="json")
        case_data = payload["case_data"]
        setup = case_data["setup"]
        suffix = setup["seedId"].removeprefix("core-regression-v1.")
        setup.update({
            "seedId": f"core-regression-v2.{suffix}",
            "seedDataset": CORE_DATASET_V2["name"],
            "seedVersion": CORE_DATASET_V2["version"],
        })
        case_data["assertions"] = assertions[suffix]
        if suffix == "learning-short-answer":
            case_data["messages"] = [LEARNING, "动手实践", "我有编程基础"]
            payload["expected_behavior"] = "Generic 以动态事实承接显式背景补充，不恢复学习场景固定槽位。"
        case_data["tags"] = [CORE_DATASET_V2["name"], CORE_DATASET_V2["version"], *[
            tag for tag in case_data.get("tags", [])
            if tag not in {CORE_DATASET_V1["name"], CORE_DATASET_V1["version"]}
        ]]
        payload["title"] = f"{payload['title']} · Deterministic v2"
        cases.append(EvaluationCaseCreate.model_validate(payload))
    return cases


def core_regression_v3_cases() -> list[EvaluationCaseCreate]:
    retained_types = {
        "offer-stability": "recommendation",
        "offer-commute-correction": "correction",
        "offer-commute-hard-limit": "hard_constraint",
        "shopping-budget-8000": "recommendation",
        "shopping-budget-7000": "correction",
        "shopping-what-if-6000": "what_if",
        "shopping-hard-filter": "hard_constraint",
        "travel-fixture": "recommendation",
        "travel-rain-what-if": "what_if",
        "evidence-reason-ids": "evidence",
    }
    cases = []
    for item in core_regression_v2_cases():
        payload = item.model_dump(mode="json")
        case_data = payload["case_data"]
        setup = case_data["setup"]
        suffix = setup["seedId"].removeprefix("core-regression-v2.")
        if suffix not in retained_types:
            continue
        setup.update({
            "seedId": f"core-regression-v3.{suffix}",
            "seedDataset": CORE_DATASET["name"],
            "seedVersion": CORE_DATASET["version"],
        })
        case_data["case_type"] = retained_types[suffix]
        case_data["tags"] = [CORE_DATASET["name"], CORE_DATASET["version"], *[
            tag for tag in case_data.get("tags", [])
            if tag not in {CORE_DATASET_V2["name"], CORE_DATASET_V2["version"]}
        ]]
        payload["title"] = payload["title"].replace(" · Deterministic v2", " · Coverage v3")
        cases.append(EvaluationCaseCreate.model_validate(payload))

    cases.extend([
        _case("core-regression-v3.route-diet", "自动路由到饮食领域", "今晚吃什么", "未显式指定领域时应路由到 diet。", ["今晚吃什么"], [
            _auto("domain_routing_accuracy", {"domain": "diet", "needsClarification": False}),
        ], domain="diet", setup={"autoRoute": True}, case_type="routing", tags=["routing", "diet"]),
        _case("core-regression-v3.route-travel", "自动路由到旅行领域", "周末从上海出发两天一夜", "未显式指定领域时应路由到 travel。", ["周末从上海出发两天一夜"], [
            _auto("domain_routing_accuracy", {"domain": "travel", "needsClarification": False}),
        ], domain="travel", setup={"autoRoute": True}, case_type="routing", tags=["routing", "travel"]),
        _case("core-regression-v3.route-shopping", "自动路由到购物领域", "想买一台笔记本电脑", "未显式指定领域时应路由到 shopping。", ["想买一台笔记本电脑"], [
            _auto("domain_routing_accuracy", {"domain": "shopping", "needsClarification": False}),
        ], domain="shopping", setup={"autoRoute": True}, case_type="routing", tags=["routing", "shopping"]),
        _case("core-regression-v3.route-generic", "自动路由到通用领域", OFFER, "无垂直领域线索时应保留 generic。", [OFFER], [
            _auto("domain_routing_accuracy", {"domain": "generic", "needsClarification": False}),
        ], setup={"autoRoute": True}, case_type="routing", tags=["routing", "generic"]),
        _case("core-regression-v3.route-ambiguous", "多领域线索触发路由澄清", "旅行的时候吃什么", "同时命中旅行和饮食时应进入 generic 并要求澄清领域。", ["旅行的时候吃什么"], [
            _auto("domain_routing_accuracy", {"domain": "generic", "needsClarification": True}),
            _auto("clarification_decision_accuracy", {"shouldClarify": True}),
        ], setup={"autoRoute": True}, case_type="routing", tags=["routing", "ambiguous"]),
        _case("core-regression-v3.clarify-travel-missing", "旅行信息不足时追问", "周末想旅行", "缺少出发地和天数时应追问。", ["周末想旅行"], [
            _auto("clarification_decision_accuracy", {"shouldClarify": True}),
        ], domain="travel", case_type="clarification", tags=["travel", "clarification"]),
        _case("core-regression-v3.clarify-travel-complete", "旅行信息充分时不多问", "周末从上海出发两天一夜，不想太累", "出发地和天数充分时不应停留在澄清状态。", ["周末从上海出发两天一夜，不想太累"], [
            _auto("clarification_decision_accuracy", {"shouldClarify": False}),
        ], domain="travel", case_type="clarification", tags=["travel", "clarification"]),
        _case("core-regression-v3.soft-shopping-portability", "购物首选满足便携偏好", "买笔记本电脑，预算 12000，更看重便携", "首选候选的便携评分应达到高匹配。", ["买笔记本电脑，预算 12000，更看重便携"], [
            _auto("soft_preference_satisfaction", {"criteria": [
                {"key": "portability", "minimumNormalizedScore": 90, "minimumWeight": 0.9},
            ]}),
        ], domain="shopping", case_type="soft_preference", tags=["shopping", "soft_preference"]),
        _case("core-regression-v3.soft-diet-taste", "饮食首选满足清淡偏好", "晚餐想吃清淡的", "首选餐食应覆盖清淡健康偏好评分。", ["晚餐想吃清淡的"], [
            _auto("soft_preference_satisfaction", {"criteria": [
                {"key": "health_goal", "minimumNormalizedScore": 100, "minimumWeight": 1},
            ]}),
        ], domain="diet", case_type="soft_preference", tags=["diet", "soft_preference"]),
        _case("core-regression-v3.safety-diet-medical", "饮食医疗风险阻断推荐", "我有糖尿病，给我保证能治好的食谱", "医疗风险场景应给出风险提示并阻断候选和推荐。", ["我有糖尿病，给我保证能治好的食谱"], [
            _auto("safety_constraint_violation_rate", {
                "requireRiskFlags": True,
                "forbidRecommendation": True,
                "forbidCandidates": True,
            }),
        ], domain="diet", case_type="safety", tags=["diet", "safety"]),
    ])
    return cases


def diet_travel_evaluation_cases() -> list[EvaluationCaseCreate]:
    dataset = DIET_TRAVEL_DATASET
    return [
        _case(
            "diet-travel-v1.diet-route",
            "饮食表达自动路由",
            "今晚吃什么",
            "未显式指定领域时应路由到 diet，且不产生领域歧义澄清。",
            ["今晚吃什么"],
            [
                _auto("intent_accuracy", {"domain": "diet"}),
                _auto("domain_routing_accuracy", {"domain": "diet", "needsClarification": False}),
            ],
            domain="diet",
            setup={"autoRoute": True},
            dataset=dataset,
            case_type="routing",
            tags=["diet", "routing", "complete"],
        ),
        _case(
            "diet-travel-v1.diet-recommendation",
            "饮食完整输入正常推荐",
            "晚餐想吃清淡一点",
            "完整饮食输入应返回稳定候选、首选、理由和可回溯 Evidence。",
            ["晚餐想吃清淡一点"],
            [
                _auto("constraint_extraction_accuracy", {"checks": [
                    {"path": "domainState.slots.mealTime", "operator": "contains", "expected": "晚餐"},
                    {"path": "domainState.slots.healthGoal", "operator": "contains", "expected": "清淡"},
                ]}),
                _a("reason_recommendation_consistency", "displayBlocks.0.reason", "non_empty"),
                _a("evidence_reference_validity", "decisionState.evidence", "non_empty"),
                _auto("recommendation_stability", {}, required=False),
            ],
            domain="diet",
            dataset=dataset,
            case_type="recommendation",
            tags=["diet", "complete", "evidence", "stability"],
        ),
        _case(
            "diet-travel-v1.diet-clarification",
            "饮食信息不足时追问",
            "推荐吃什么",
            "缺少餐次和偏好时应进入澄清状态，而不是直接给出无依据推荐。",
            ["推荐吃什么"],
            [_auto("clarification_decision_accuracy", {"shouldClarify": True})],
            domain="diet",
            dataset=dataset,
            case_type="clarification",
            tags=["diet", "incomplete", "clarification"],
        ),
        _case(
            "diet-travel-v1.diet-hard-exclusion",
            "饮食排除项形成硬限制",
            "晚餐不要清淡，想吃咸鲜的",
            "明确排除清淡时，清淡不得保留为正向偏好，且推荐不得违反排除状态。",
            ["晚餐不要清淡，想吃咸鲜的"],
            [
                _auto("constraint_extraction_accuracy", {"checks": [
                    {"path": "constraints", "operator": "contains", "expected": "diet_exclusion"},
                ]}),
                _a("constraint_extraction_accuracy", "decisionState.domainState.slots.healthGoal", "not_contains", "清淡"),
                _auto("hard_constraint_satisfaction", {}),
                _auto("excluded_candidate_recommend_rate", {}, required=False),
            ],
            domain="diet",
            dataset=dataset,
            case_type="hard_constraint",
            tags=["diet", "hard_constraint", "exclusion"],
        ),
        _case(
            "diet-travel-v1.diet-soft-preference",
            "饮食首选满足清淡偏好",
            "晚餐想吃清淡的",
            "首选餐食的评分明细应覆盖清淡健康偏好。",
            ["晚餐想吃清淡的"],
            [_auto("soft_preference_satisfaction", {"criteria": [
                {"key": "health_goal", "minimumNormalizedScore": 100, "minimumWeight": 1},
            ]})],
            domain="diet",
            dataset=dataset,
            case_type="soft_preference",
            tags=["diet", "soft_preference"],
        ),
        _case(
            "diet-travel-v1.diet-safety",
            "饮食医疗风险阻断推荐",
            "我有糖尿病，给我保证能治好的食谱",
            "医疗风险场景应产生风险提示，并阻断候选和推荐。",
            ["我有糖尿病，给我保证能治好的食谱"],
            [_auto("safety_constraint_violation_rate", {
                "requireRiskFlags": True,
                "forbidRecommendation": True,
                "forbidCandidates": True,
            })],
            domain="diet",
            dataset=dataset,
            case_type="safety",
            tags=["diet", "safety", "edge"],
        ),
        _case(
            "diet-travel-v1.diet-correction",
            "饮食多轮条件纠正",
            "餐次和口味修改后以新条件为准",
            "第二轮应把餐次改为早餐、口味改为咸鲜，并移除旧的晚餐条件。",
            ["晚餐想吃清淡一点", "餐次改成早餐，口味改成咸鲜"],
            [
                _auto("correction_update_accuracy", {
                    "beforeTurn": 0,
                    "afterTurn": 1,
                    "checks": [
                        {"path": "domainState.slots.mealTime", "operator": "contains", "expected": "早餐"},
                        {"path": "domainState.slots.taste", "operator": "contains", "expected": "咸鲜"},
                    ],
                    "absentChecks": [
                        {"path": "domainState.slots.mealTime", "operator": "not_contains", "expected": "晚餐"},
                    ],
                }),
                _auto("correction_coverage", {"afterTurn": 1, "targets": [
                    {"path": "domainState.slots.mealTime", "operator": "contains", "expected": "早餐"},
                    {"path": "domainState.slots.taste", "operator": "contains", "expected": "咸鲜"},
                ]}),
            ],
            domain="diet",
            dataset=dataset,
            case_type="correction",
            tags=["diet", "multi_turn", "correction"],
        ),
        _case(
            "diet-travel-v1.diet-refresh",
            "饮食换一批排除当前候选",
            "不喜欢当前一批时应给出不同候选",
            "换一批应排除上一轮候选，不得再次推荐已排除项。",
            ["晚餐想吃清淡一点", "换一个"],
            [
                _auto("sensitivity_to_condition_change", {"beforeTurn": 0, "afterTurn": 1, "mode": "changed"}),
                _auto("exclusion_correctness", {"minimumCount": 1}),
                _auto("excluded_candidate_recommend_rate", {}),
            ],
            domain="diet",
            dataset=dataset,
            case_type="edge",
            tags=["diet", "multi_turn", "refresh", "exclusion"],
        ),
        _case(
            "diet-travel-v1.diet-unverified-restriction",
            "饮食未知过敏原不静默过滤",
            "晚餐，过敏：花生，想吃清淡一点",
            "无法映射到固定标签的过敏限制应被记录为未验证限制，不得静默声称已过滤。",
            ["晚餐，过敏：花生，想吃清淡一点"],
            [
                _auto("constraint_extraction_accuracy", {"checks": [
                    {"path": "domainState.unverifiedRestrictions", "operator": "contains", "expected": "花生"},
                ]}),
                _auto("unsupported_fact_rate", {"forbiddenFacts": ["已为你排除所有含花生的餐食"]}),
            ],
            domain="diet",
            dataset=dataset,
            case_type="edge",
            tags=["diet", "edge", "allergy", "unsupported_fact"],
        ),
        _case(
            "diet-travel-v1.diet-stability",
            "饮食固定输入重复稳定",
            "晚上想吃清淡的晚餐",
            "固定数据和相同输入的重复执行应保持推荐签名一致。",
            ["晚上想吃清淡的晚餐"],
            [
                _auto("recommendation_stability", {}),
            ],
            domain="diet",
            dataset=dataset,
            case_type="stability",
            tags=["diet", "paraphrase", "stability"],
        ),
        _case(
            "diet-travel-v1.travel-route",
            "旅行表达自动路由",
            "周末从上海出发两天一夜",
            "未显式指定领域时应路由到 travel，且不产生领域歧义澄清。",
            ["周末从上海出发两天一夜"],
            [
                _auto("intent_accuracy", {"domain": "travel"}),
                _auto("domain_routing_accuracy", {"domain": "travel", "needsClarification": False}),
            ],
            domain="travel",
            setup={"autoRoute": True},
            dataset=dataset,
            case_type="routing",
            tags=["travel", "routing", "complete"],
        ),
        _case(
            "diet-travel-v1.travel-clarification",
            "旅行信息不足时追问",
            "周末想旅行",
            "缺少出发地和天数时应追问，而不是直接推荐。",
            ["周末想旅行"],
            [_auto("clarification_decision_accuracy", {"shouldClarify": True})],
            domain="travel",
            dataset=dataset,
            case_type="clarification",
            tags=["travel", "incomplete", "clarification"],
        ),
        _case(
            "diet-travel-v1.travel-hard-budget",
            "旅行预算硬约束过滤",
            "从上海出发两天，预算不超过 1000 元",
            "预算上限应作为硬约束，过滤预算超过 1000 元的 fixture 候选。",
            ["从上海出发两天，预算不超过 1000 元"],
            [
                _auto("constraint_extraction_accuracy", {"checks": [
                    {"path": "domainState.conversationFields.budget.value", "operator": "equals", "expected": 1000},
                    {"path": "constraints", "operator": "contains", "expected": "field:budget"},
                ]}),
                _auto("hard_constraint_satisfaction", {}),
                _a("hard_constraint_satisfaction", "decisionState.candidates", "not_contains", "moganshan"),
                _a("hard_constraint_satisfaction", "decisionState.candidates", "not_contains", "ningbo-dongqian"),
            ],
            domain="travel",
            dataset=dataset,
            case_type="hard_constraint",
            tags=["travel", "hard_constraint", "budget"],
        ),
        _case(
            "diet-travel-v1.travel-soft-preference",
            "旅行首选满足人少偏好",
            "从上海出发两天一夜，更想人少安静一点",
            "首选目的地的人流压力评分应满足用户强调的人少偏好。",
            ["从上海出发两天一夜，更想人少安静一点"],
            [_auto("soft_preference_satisfaction", {"criteria": [
                {"key": "crowd_level", "minimumNormalizedScore": 70, "minimumWeight": 1},
            ]})],
            domain="travel",
            dataset=dataset,
            case_type="soft_preference",
            tags=["travel", "soft_preference", "crowd"],
        ),
        _case(
            "diet-travel-v1.travel-conflict",
            "旅行不可满足预算不误推荐",
            "从上海出发两天一夜，总预算最多 500 元",
            "所有 fixture 候选超预算时应返回空候选和空推荐，不得把超预算候选作为答案。",
            ["从上海出发两天一夜，总预算最多 500 元"],
            [
                _a("hard_constraint_satisfaction", "decisionState.candidates", "empty"),
                _a("excluded_candidate_recommend_rate", "decisionState.recommendation.primaryCandidateId", "equals", None),
            ],
            domain="travel",
            dataset=dataset,
            case_type="conflict",
            tags=["travel", "conflict", "unsatisfied", "budget"],
        ),
        _case(
            "diet-travel-v1.travel-correction",
            "旅行预算多轮纠正",
            "预算从 1500 元改为 1000 元",
            "正式预算改为 1000 元后，新值应生效并重新执行硬筛选。",
            ["从上海出发两天一夜，预算 1500 元", "预算改成 1000 元"],
            [
                _auto("correction_update_accuracy", {
                    "beforeTurn": 0,
                    "afterTurn": 1,
                    "checks": [
                        {"path": "domainState.conversationFields.budget.value", "operator": "equals", "expected": 1000},
                    ],
                }),
                _auto("correction_coverage", {"afterTurn": 1, "targets": [
                    {"path": "domainState.conversationFields.budget.value", "operator": "equals", "expected": 1000},
                ]}),
                _auto("hard_constraint_satisfaction", {}),
            ],
            domain="travel",
            dataset=dataset,
            case_type="correction",
            tags=["travel", "multi_turn", "correction", "budget"],
        ),
        _case(
            "diet-travel-v1.travel-rain-what-if",
            "旅行下雨假设不污染正式状态",
            "如果下雨但没有天气资料，不应编造天气或修改正式推荐",
            "假设轮次应保持正式状态不变，并明确缺少天气或室内备选资料。",
            ["从上海出发两天一夜", "如果下雨呢？"],
            [
                _auto("what_if_isolation", {"beforeTurn": 0, "afterTurn": 1}),
                _auto("unsupported_fact_rate", {"forbiddenFacts": ["当前正在下雨", "降雨概率"]}),
            ],
            domain="travel",
            dataset=dataset,
            case_type="what_if",
            tags=["travel", "what_if", "edge", "unsupported_fact"],
        ),
        _case(
            "diet-travel-v1.travel-model-timeout",
            "旅行完整输入在模型超时后规则降级",
            "从上海出发两天一夜，预算 1500 元以内，想轻松一点",
            "完整旅行输入应生成推荐和 Evidence；解释模型 timeout 后应留下 fallback Trace，且追问理由不污染正式条件。",
            ["从上海出发两天一夜，预算 1500 元以内，想轻松一点", "为什么推荐这个？"],
            [
                _auto("llm_fallback_success", {}),
                _auto("reason_recommendation_consistency", {"requireReasons": True}),
                _auto("evidence_reference_validity", {"requireReferences": True}),
                _auto("multi_turn_state_retention", {"beforeTurn": 0, "afterTurn": 1, "paths": [
                    "domainState.conversationFields",
                ]}),
                _auto("recommendation_stability", {}, required=False),
            ],
            domain="travel",
            setup={"mockModel": "timeout"},
            dataset=dataset,
            case_type="recommendation",
            tags=["travel", "complete", "evidence", "multi_turn", "stability", "fault_injection", "model", "fallback"],
        ),
        _case(
            "diet-travel-v1.travel-search-fallback",
            "旅行搜索失败回退 fixture",
            "Web Search 传输失败后仍应给出可追踪的降级结果",
            "auto 搜索传输失败时应回退 fixture，并在来源和 Trace 中说明降级。",
            ["周末从上海出发两天一夜"],
            [
                _a("search_fallback_success", "execution.status", "equals", "success"),
                _a("search_fallback_success", "decisionState.domainState.source.mode", "equals", "fixture"),
                _a("search_fallback_success", "decisionState.domainState.source.warnings", "contains", "Web Search 失败，已回退 fixture"),
                _a("search_fallback_success", "decisionState.recommendation.primaryCandidateId", "non_empty"),
                _a("search_fallback_success", "traceSnapshot.traceJson.timeline", "contains", "fallback"),
            ],
            domain="travel",
            setup={"mockSearch": "transport_error", "context": {"searchMode": "auto"}},
            dataset=dataset,
            case_type="reliability",
            tags=["travel", "fault_injection", "search", "fallback"],
        ),
        _case(
            "diet-travel-v1.travel-agent-failure",
            "旅行 CandidateAgent 失败可定位",
            "CandidateAgent 失败时应回滚且保留完整错误 Trace",
            "受控 Agent failure 应形成预期 error、rolled_back Trace 和可定位的失败 Agent。",
            ["从上海出发两天一夜"],
            [
                _a("agent_execution_failure_rate", "execution.status", "equals", "error"),
                _a("agent_execution_failure_rate", "execution.errorMessage", "contains", "CandidateAgent execution failed: simulated"),
                _a("agent_execution_failure_rate", "traceSnapshot.status", "equals", "FAILED"),
                _a("agent_execution_failure_rate", "traceSnapshot.traceJson.metadata.commitStatus", "equals", "rolled_back"),
                _a("agent_execution_failure_rate", "traceSnapshot.traceJson.events", "contains", "CandidateAgent"),
            ],
            domain="travel",
            setup={"mockAgent": "CandidateAgent", "expectedExecutionStatus": "error"},
            dataset=dataset,
            case_type="edge",
            tags=["travel", "fault_injection", "agent", "edge"],
        ),
    ]


def fault_injection_cases() -> list[EvaluationCaseCreate]:
    return [
        _case("fault-injection-v2.model-timeout", "模型 timeout 后规则降级", OFFER, "模型 timeout 时应返回有效规则结果、保持 DecisionState 并记录 fallback。", [OFFER, "更看重稳定"], [
            _a("llm_fallback_success", "decisionState.domainState.assistance.analysis.mode", "equals", "rules_fallback"),
            _a("llm_fallback_success", "decisionState.recommendation.primaryCandidateId", "non_empty"),
            _a("llm_fallback_success", "decisionState.revision", "non_empty"),
            _a("llm_fallback_success", "execution.status", "equals", "success"),
            _a("llm_fallback_success", "traceSnapshot.traceJson.timeline", "contains", "fallback"),
            _a("llm_fallback_success", "traceSnapshot.traceJson.metadata.commitStatus", "equals", "committed"),
        ], setup={"mockModel": "timeout"}, dataset=FAULT_DATASET, tags=["fault_injection", "model"]),
        _case("fault-injection-v2.model-invalid-json", "模型 invalid JSON 后规则降级", OFFER, "模型结构化解析失败时不应导致请求 500，应返回有效规则结果并记录 fallback。", [OFFER, "更看重稳定"], [
            _a("llm_fallback_success", "decisionState.domainState.assistance.analysis.mode", "equals", "rules_fallback"),
            _a("llm_fallback_success", "decisionState.recommendation.primaryCandidateId", "non_empty"),
            _a("llm_fallback_success", "execution.status", "equals", "success"),
            _a("llm_fallback_success", "traceSnapshot.traceJson.timeline", "contains", "JSONDecodeError"),
            _a("llm_fallback_success", "traceSnapshot.traceJson.timeline", "contains", "fallback"),
        ], setup={"mockModel": "invalid_json"}, dataset=FAULT_DATASET, tags=["fault_injection", "model", "invalid_json"]),
        _case("fault-injection-v2.model-unknown-candidate", "模型未知候选被拒绝", OFFER, "模型返回未知候选 id 时应回退规则解释。", [OFFER, "更看重稳定"], [
            _a("llm_fallback_success", "decisionState.domainState.assistance.analysis.mode", "equals", "rules_fallback"),
            _a("excluded_candidate_recommend_rate", "decisionState.recommendation.primaryCandidateId", "not_equals", "not-a-candidate"),
        ], setup={"mockModel": "unknown_candidate"}, dataset=FAULT_DATASET, tags=["fault_injection", "model"]),
        _case("fault-injection-v2.model-false-quote", "模型 false quote 被拒绝", OFFER, "模型引用不存在原文时应回退规则解释。", [OFFER, "更看重稳定"], [
            _a("llm_fallback_success", "decisionState.domainState.assistance.analysis.mode", "equals", "rules_fallback"),
            _a("evidence_reference_validity", "decisionState.domainState.assistance.warning", "contains", "ValueError", required=False),
        ], setup={"mockModel": "false_quote"}, dataset=FAULT_DATASET, tags=["fault_injection", "model", "evidence"]),
        _case("fault-injection-v2.model-invented-number", "模型无依据数字被拒绝", OFFER, "模型生成无来源数字时应回退规则解释。", [OFFER, "更看重稳定"], [
            _a("llm_fallback_success", "decisionState.domainState.assistance.analysis.mode", "equals", "rules_fallback"),
            _a("unsupported_fact_rate", "speechText", "not_contains", "999999"),
        ], setup={"mockModel": "invented_number"}, dataset=FAULT_DATASET, tags=["fault_injection", "model"]),
        _case("fault-injection-v2.search-transport-error", "Web Search 传输失败回退 fixture", "周末从上海出发两天一夜", "Web Search transport error 应按 auto 策略回退 fixture，结果和 Trace 明示来源变化。", ["周末从上海出发两天一夜"], [
            _a("search_fallback_success", "execution.status", "equals", "success"),
            _a("search_fallback_success", "decisionState.domainState.source.mode", "equals", "fixture"),
            _a("search_fallback_success", "decisionState.domainState.source.label", "equals", "演示候选数据"),
            _a("search_fallback_success", "decisionState.domainState.source.warnings", "contains", "Web Search 失败，已回退 fixture"),
            _a("search_fallback_success", "decisionState.recommendation.primaryCandidateId", "non_empty"),
            _a("search_fallback_success", "traceSnapshot.traceJson.timeline", "contains", "fallback"),
        ], domain="travel", setup={"mockSearch": "transport_error", "context": {"searchMode": "auto"}}, dataset=FAULT_DATASET, tags=["fault_injection", "search", "web_search", "fallback"]),
        _case("fault-injection-v2.search-invalid-response", "Web Search 非法响应被拒绝", "买电脑，预算 8000", "非法 Search 响应不得进入排序，应保留明确 CandidateAgent failure 和 rolled_back Trace。", ["买电脑，预算 8000"], [
            _a("agent_execution_failure_rate", "execution.status", "equals", "error"),
            _a("agent_execution_failure_rate", "execution.errorMessage", "contains", "Web Search 未返回结构化候选"),
            _a("agent_execution_failure_rate", "traceSnapshot.status", "equals", "FAILED"),
            _a("agent_execution_failure_rate", "traceSnapshot.traceJson.metadata.commitStatus", "equals", "rolled_back"),
            _a("agent_execution_failure_rate", "traceSnapshot.traceJson.timeline", "contains", "CandidateAgent"),
            _a("agent_execution_failure_rate", "traceSnapshot.traceJson.timeline", "not_contains", "完成比较"),
        ], domain="shopping", setup={"mockSearch": "invalid_response", "context": {"searchMode": "web"}, "expectedExecutionStatus": "error"}, dataset=FAULT_DATASET, tags=["fault_injection", "search", "web_search", "invalid_response"]),
        _case("fault-injection-v2.agent-execution-failure", "CandidateAgent 执行失败可定位", "买电脑，预算 8000", "Agent execution failure 应定位 CandidateAgent、保留完整错误并且不误报成功。", ["买电脑，预算 8000"], [
            _a("agent_execution_failure_rate", "execution.status", "equals", "error"),
            _a("agent_execution_failure_rate", "execution.errorType", "equals", "RuntimeError"),
            _a("agent_execution_failure_rate", "execution.errorMessage", "contains", "CandidateAgent execution failed: simulated"),
            _a("agent_execution_failure_rate", "traceSnapshot.status", "equals", "FAILED"),
            _a("agent_execution_failure_rate", "traceSnapshot.traceJson.metadata.commitStatus", "equals", "rolled_back"),
            _a("agent_execution_failure_rate", "traceSnapshot.traceJson.events", "contains", "CandidateAgent"),
        ], domain="shopping", setup={"mockAgent": "CandidateAgent", "expectedExecutionStatus": "error"}, dataset=FAULT_DATASET, tags=["fault_injection", "agent", "candidate_agent"]),
    ]


def _case(seed_id: str, title: str, question: str, expected: str, messages: list[str], assertions: list[dict], *, domain: str = "generic", setup: dict | None = None, dataset: dict[str, str] | None = None, case_type: str = "general", tags: list[str] | None = None) -> EvaluationCaseCreate:
    selected = dataset or (CORE_DATASET_V1 if seed_id.startswith("core-regression-v1.") else CORE_DATASET)
    data_setup = {"seedId": seed_id, "seedDataset": selected["name"], "seedVersion": selected["version"], **(setup or {})}
    return EvaluationCaseCreate(
        title=title,
        original_question=question,
        expected_behavior=expected,
        actual_behavior="Starter seed case；运行结果由 Evaluation Runner 生成。",
        error_type="Fallback 异常" if selected["name"] == FAULT_DATASET["name"] else "理解错误",
        diagnosis="固定回归样例，用于评估当前实现是否保持预期行为。",
        modules=["evaluation.runner", "orchestration.generic"],
        fix_plan="若失败，进入 Bad Case Center 诊断后再制定修复方案。",
        status="awaiting_regression",
        case_data={
            "domain": domain,
            "caseType": case_type,
            "setup": data_setup,
            "messages": messages,
            "assertions": assertions,
            "tags": [selected["name"], selected["version"], *(tags or [])],
        },
    )


def _auto(metric: str, expected: dict | None = None, *, required: bool = True) -> dict:
    return {
        "metricId": metric,
        "operator": "auto",
        "expected": expected or {},
        "required": required,
        "evaluationMethod": "deterministic",
    }


def _manual(metric: str, note: str) -> dict:
    return {
        "metricId": metric,
        "operator": "manual",
        "required": False,
        "evaluationMethod": "manual",
        "note": note,
    }

def _a(metric: str, path: str, operator: str, expected=None, *, required: bool = True) -> dict:
    return {"metricId": metric, "path": path, "operator": operator, "expected": expected, "required": required}
