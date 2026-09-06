from __future__ import annotations

from choice_agent.evaluation.schemas import EvaluationCaseCreate


def starter_cases() -> list[EvaluationCaseCreate]:
    return [
        EvaluationCaseCreate(
            title="Offer 候选事实纠正挂载",
            original_question="A 公司稳定离家近，B 公司成长快但通勤两小时，我应该怎么选？",
            expected_behavior="B 的通勤风险必须挂载到 B 候选；用户纠正为半小时后旧通勤事实被移除。",
            actual_behavior="历史 Bad Case：B 的通勤事实未稳定挂载到候选。",
            error_type="约束处理错误",
            diagnosis="Candidate Fact Grounding 对候选归属和纠正覆盖校验不足。",
            modules=["decision.assistance", "decision.evidence", "orchestration.generic"],
            fix_plan="补充候选归属解析、引用校验和回归断言。",
            status="diagnosed",
            case_data={
                "domain": "career",
                "messages": [
                    "A 公司工作稳定、离家近，B 公司成长更快但每天通勤两小时，我应该怎么选？",
                    "B 其实只要半小时，不是两小时。",
                ],
                "fixtureActual": {
                    "decisionState": {
                        "recommendation": {"primaryCandidateId": "b"},
                        "domainState": {"assistance": {"candidateFacts": {"b": ["通勤半小时"]}}},
                        "excludedCandidates": [],
                    },
                    "speechText": "B 的成长性更好，通勤纠正为半小时后风险下降。",
                },
                "assertions": [
                    {"metricId": "constraint_extraction_accuracy", "path": "decisionState.domainState.assistance.candidateFacts.b", "operator": "contains", "expected": "通勤半小时"},
                    {"metricId": "correction_update_accuracy", "path": "decisionState.domainState.assistance.candidateFacts.b", "operator": "not_contains", "expected": "通勤两小时"},
                    {"metricId": "reason_recommendation_consistency", "path": "speechText", "operator": "contains", "expected": "B"},
                ],
                "tags": ["offer", "candidate_fact_grounding"],
            },
        ),
        EvaluationCaseCreate(
            title="What-if 不污染正式预算",
            original_question="预算 8000，假设只有 6000 呢？然后正式改成 7000。",
            expected_behavior="6000 的假设比较不改正式预算，正式编辑 7000 后才更新状态。",
            actual_behavior="用于防止假设分析污染正式状态。",
            error_type="多轮状态丢失",
            diagnosis="正式业务投影需要和假设 projection 分开比较。",
            modules=["decision.what_if", "decision.assistance"],
            fix_plan="用正式投影断言验证 what-if 后状态未变。",
            status="awaiting_regression",
            case_data={
                "domain": "shopping",
                "fixtureActual": {
                    "before": {"budget": 8000},
                    "afterWhatIf": {"budget": 8000},
                    "afterOfficial": {"budget": 7000},
                    "decisionState": {"context": {"searchMode": "fixture"}},
                },
                "assertions": [
                    {"metricId": "what_if_isolation", "beforePath": "before", "actualPath": "afterWhatIf", "operator": "unchanged"},
                    {"metricId": "correction_update_accuracy", "path": "afterOfficial.budget", "operator": "equals", "expected": 7000},
                ],
                "tags": ["what_if", "shopping"],
            },
        ),
        EvaluationCaseCreate(
            title="模型超时后显式 Fallback",
            original_question="模型解释超时后仍需返回可用的规则解释。",
            expected_behavior="LLM 调用失败时返回规则 fallback，并在指标中记录为 Fallback 成功。",
            actual_behavior="用于区分禁用模型、校验拒绝和真实调用失败。",
            error_type="Fallback 异常",
            diagnosis="调用失败和规则降级事件必须可观察。",
            modules=["agents.base", "decision.assistance"],
            fix_plan="记录模型失败和 fallback 输出断言。",
            status="awaiting_regression",
            case_data={
                "domain": "generic",
                "fixtureActual": {
                    "modelCallFailed": True,
                    "fallbackUsed": True,
                    "speechText": "模型暂不可用，已使用规则比较生成当前结论。",
                },
                "assertions": [
                    {"metricId": "llm_fallback_success", "path": "fallbackUsed", "operator": "equals", "expected": True},
                    {"metricId": "agent_execution_failure_rate", "path": "modelCallFailed", "operator": "equals", "expected": True, "required": False},
                ],
                "tags": ["fallback"],
            },
        ),
    ]
