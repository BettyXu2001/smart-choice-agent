(function () {
    "use strict";

    const STORAGE_KEY = "choiceAgentDemoDecisions";
    const LAST_ID_KEY = "choiceAgentLastDemoDecisionId";
    const retrievedAt = "2026-08-27T00:00:00.000Z";
    const domainLabels = {
        travel: "旅行决策",
        career: "职业选择",
        learning: "学习路径",
        shopping: "消费选择",
        generic: "通用比较"
    };

    function nowIso() {
        return new Date().toISOString();
    }

    function clone(value) {
        return JSON.parse(JSON.stringify(value));
    }

    function demoEvidence(id, candidateId, criterionKey, claim, sourceTitle) {
        return {
            id,
            candidateId,
            criterionKey,
            claim,
            sourceUrl: "https://example.com/choice-agent-demo",
            sourceTitle: sourceTitle || "Choice Agent 演示数据",
            retrievedAt,
            confidence: 0.68,
            freshness: "unknown"
        };
    }

    function demoCandidate(id, name, summary, attributes, claim, criterionKey) {
        return {
            id,
            name,
            summary,
            attributes,
            eliminated: false,
            evidence: [demoEvidence(`${id}-demo-evidence`, id, criterionKey, claim)]
        };
    }

    const fixtures = {
        travel: {
            id: "demo-shanghai-weekend",
            status: "comparing",
            domain: "travel",
            candidateState: "complete",
            nextAction: "compare",
            goal: "周末从上海出发，找一个两天一夜、轻松、人相对少的目的地",
            constraints: [
                { key: "travelHours", label: "单程交通不超过 3 小时", kind: "hard", operator: "lte", value: 3, source: "user", confidence: 1 },
                { key: "budget", label: "总预算不超过 1500 元", kind: "hard", operator: "lte", value: 1500, source: "user", confidence: 0.9 },
                { key: "pace", label: "节奏轻松，不做特种兵行程", kind: "soft", operator: "preference", value: "relaxed", source: "inferred", confidence: 0.82 }
            ],
            criteria: [
                { key: "relaxation", label: "轻松程度", weight: 35, direction: "higher_better" },
                { key: "crowdLevel", label: "避开人群", weight: 25, direction: "lower_better" },
                { key: "nature", label: "自然景观", weight: 25, direction: "higher_better" },
                { key: "costScore", label: "预算友好", weight: 15, direction: "higher_better" }
            ],
            unansweredQuestions: [
                { id: "rain-plan", question: "如果周末下雨，你更想保留户外自然景观，还是换成室内轻松路线？", options: ["优先自然景观", "下雨就换室内", "都可以"], reason: "天气会明显影响目的地排序", answered: false }
            ],
            candidates: [
                demoCandidate("moganshan", "莫干山", "自然景观强，适合放空和慢节奏，但周末热门民宿区可能偏贵。", { travelHours: 2.5, budget: 1450, relaxation: 88, crowdLevel: 48, nature: 92, costScore: 62 }, "从上海到德清高铁时间短，适合两天一夜。", "relaxation"),
                demoCandidate("shaoxing", "绍兴", "交通近、预算稳定，城市漫游轻松，缺点是自然景观不如山野目的地。", { travelHours: 1.5, budget: 950, relaxation: 78, crowdLevel: 42, nature: 58, costScore: 86 }, "短途高铁出行成本较可控，适合周末城市漫游。", "costScore"),
                demoCandidate("ningbo-dongqian", "宁波东钱湖", "湖景开阔，适合轻度骑行和散步；交通略远，但比热门古镇更舒展。", { travelHours: 2.8, budget: 1280, relaxation: 84, crowdLevel: 30, nature: 84, costScore: 70 }, "湖区路线分散，适合避开单点拥挤。", "crowdLevel"),
                demoCandidate("suzhou", "苏州", "距离最近、安排最稳，但核心园林和商业区周末人流压力较高。", { travelHours: 0.6, budget: 900, relaxation: 68, crowdLevel: 72, nature: 64, costScore: 88 }, "上海到苏州通勤式交通便利，短途成本较低。", "costScore")
            ]
        },
        career: {
            id: "demo-career-offers",
            status: "comparing",
            domain: "career",
            candidateState: "complete",
            nextAction: "compare",
            goal: "比较 A 公司和 B 公司的 Offer，判断哪个更适合长期发展",
            constraints: [],
            criteria: [
                { key: "roleFit", label: "岗位匹配", weight: 35, direction: "higher_better" },
                { key: "growth", label: "成长空间", weight: 30, direction: "higher_better" },
                { key: "stability", label: "稳定程度", weight: 20, direction: "higher_better" },
                { key: "compensation", label: "薪酬回报", weight: 15, direction: "higher_better" }
            ],
            unansweredQuestions: [],
            candidates: [
                demoCandidate("career-a", "A 公司", "AI 产品方向更匹配，成长空间更大，但业务阶段较早。", { roleFit: 90, growth: 88, stability: 62, compensation: 78 }, "岗位方向与 AI 产品目标更接近，但早期业务存在一定不确定性。", "roleFit"),
                demoCandidate("career-b", "B 公司", "平台成熟、薪酬稳定，岗位内容更偏传统产品。", { roleFit: 70, growth: 72, stability: 90, compensation: 86 }, "成熟平台能提供更稳定的资源与回报，但岗位方向匹配度较低。", "stability")
            ]
        },
        learning: {
            id: "demo-learning-ai",
            status: "comparing",
            domain: "learning",
            candidateState: "complete",
            nextAction: "compare",
            goal: "选择一条适合入门 AI Agent 的学习路径",
            constraints: [],
            criteria: [
                { key: "goalFit", label: "目标匹配", weight: 35, direction: "higher_better" },
                { key: "prerequisite", label: "上手难度", weight: 25, direction: "higher_better" },
                { key: "practice", label: "实践强度", weight: 25, direction: "higher_better" },
                { key: "timeCost", label: "时间友好", weight: 15, direction: "higher_better" }
            ],
            unansweredQuestions: [],
            candidates: [
                demoCandidate("learning-course", "结构化在线课程", "路径完整、上手稳定，适合需要系统框架的学习者。", { goalFit: 86, prerequisite: 88, practice: 72, timeCost: 78 }, "课程按基础概念、工具调用和项目实践逐步展开。", "prerequisite"),
                demoCandidate("learning-project", "开源项目实战", "实践反馈快，但需要自行补齐概念和调试能力。", { goalFit: 90, prerequisite: 60, practice: 95, timeCost: 62 }, "直接完成一个小型 Agent 项目能够快速暴露知识缺口。", "practice"),
                demoCandidate("learning-reading", "文档与论文路线", "信息质量高、自由度大，但学习路径容易分散。", { goalFit: 78, prerequisite: 65, practice: 55, timeCost: 70 }, "官方文档与论文适合建立准确概念，但需要自行组织顺序。", "goalFit")
            ]
        },
        shopping: {
            id: "demo-shopping-laptop",
            status: "comparing",
            domain: "shopping",
            candidateState: "complete",
            nextAction: "compare",
            goal: "选择一台适合通勤和日常工作的轻便电脑",
            constraints: [],
            criteria: [
                { key: "portability", label: "便携程度", weight: 35, direction: "higher_better" },
                { key: "performance", label: "工作性能", weight: 30, direction: "higher_better" },
                { key: "battery", label: "续航表现", weight: 20, direction: "higher_better" },
                { key: "costScore", label: "预算友好", weight: 15, direction: "higher_better" }
            ],
            unansweredQuestions: [],
            candidates: [
                demoCandidate("laptop-light", "轻薄本 A", "重量更轻、续航更稳，适合高频通勤。", { portability: 94, performance: 74, battery: 90, costScore: 76 }, "轻量机身和长续航更适合每天携带。", "portability"),
                demoCandidate("laptop-balanced", "全能本 B", "性能更均衡，但重量和价格略高。", { portability: 72, performance: 90, battery: 78, costScore: 66 }, "更高性能适合需要本地开发和多任务处理的工作。", "performance"),
                demoCandidate("laptop-budget", "性价比本 C", "预算压力低，基础办公足够，便携与续航一般。", { portability: 70, performance: 72, battery: 68, costScore: 94 }, "较低成本能够满足文档和轻量办公需求。", "costScore")
            ]
        }
    };

    const defaultConstraintDrafts = {
        career: [
            { label: "更看重长期发展", kind: "soft", value: "成长和方向优先" },
            { label: "薪酬不能明显低于当前预期", kind: "hard", value: "薪酬达标" }
        ],
        learning: [
            { label: "每周学习时间有限", kind: "hard", value: "每周 6 小时以内" },
            { label: "希望有实际项目练习", kind: "soft", value: "实践优先" }
        ],
        shopping: [
            { label: "适合高频通勤", kind: "hard", value: "轻便和续航优先" },
            { label: "预算需要可控", kind: "soft", value: "性价比优先" }
        ],
        generic: [
            { label: "先满足核心目标", kind: "hard", value: "目标匹配" },
            { label: "风险尽量可控", kind: "soft", value: "低风险" }
        ]
    };

    function stableId(prefix, index) {
        return `${prefix}-${Date.now().toString(36)}-${index}`;
    }

    function constraintDraftFromConstraint(constraint, index) {
        return {
            id: `constraint-draft-${constraint.key || index}`,
            sourceConstraintKey: constraint.key || "",
            label: constraint.label || "",
            kind: constraint.kind || "hard",
            value: constraint.value === undefined || constraint.value === null ? "" : String(constraint.value)
        };
    }

    function blankConstraintDraft(index) {
        return { id: stableId("constraint-draft", index), sourceConstraintKey: "", label: "", kind: "hard", value: "" };
    }

    function fixtureConstraintDrafts(domain, constraints) {
        if (Array.isArray(constraints) && constraints.length) {
            return constraints.map(constraintDraftFromConstraint);
        }
        const defaults = defaultConstraintDrafts[domain] || defaultConstraintDrafts.generic;
        return defaults.map((item, index) => ({
            id: stableId("constraint-draft", index),
            sourceConstraintKey: "",
            label: item.label,
            kind: item.kind,
            value: item.value
        }));
    }

    function traceForStage(stage) {
        return [
            { id: "understand", label: "理解目标", detail: "根据输入识别决策领域和候选结构。", status: "done" },
            { id: "constraints", label: "确认约束", detail: "让用户确认硬条件和重要偏好。", status: stage === "constraint_input" ? "current" : "done" },
            { id: "collect", label: "准备候选", detail: "让用户确认、补充或编辑候选项。", status: stage === "constraint_input" ? "todo" : stage === "candidate_input" ? "current" : "done" },
            { id: "compare", label: "比较候选", detail: "使用演示属性和权重进行稳定排序。", status: stage === "compare" ? "current" : "todo" },
            { id: "decide", label: "生成建议", detail: "在用户确认或调整权重后生成结论。", status: "todo" }
        ];
    }

    function applyConstraintInputStage(state, prompt, candidates) {
        const promptItems = promptDrafts(prompt, candidates);
        state.stage = "constraint_input";
        state.status = "collecting_constraints";
        state.candidateState = "draft";
        state.nextAction = "collect_constraints";
        state.constraintInput = {
            prefilledFrom: Array.isArray(state.constraints) && state.constraints.length ? "fixture" : "domain_default",
            items: fixtureConstraintDrafts(state.domain, state.constraints)
        };
        state.candidateInput = {
            prefilledFrom: promptItems.length ? "prompt" : "fixture",
            items: promptItems.length ? promptItems : fixtureDrafts(candidates)
        };
        state.trace = traceForStage("constraint_input");
        return state;
    }
    function draftId(index) {
        return stableId("draft", index);
    }

    function blankDraft(index) {
        return { id: draftId(index), sourceCandidateId: "", name: "", summary: "" };
    }

    function draftFromCandidate(candidate, index) {
        return {
            id: `draft-${candidate.id || index}`,
            sourceCandidateId: candidate.id || "",
            name: candidate.name || "",
            summary: candidate.summary || ""
        };
    }

    function promptDrafts(prompt, candidates) {
        const names = candidateNames(prompt);
        if (names.length < 2) {
            return [];
        }
        return names.map((name, index) => {
            const source = candidates[index] || {};
            return {
                id: draftId(index),
                sourceCandidateId: source.id || "",
                name,
                summary: source.summary || "等待你补充更多信息，当前先按演示维度比较。"
            };
        });
    }

    function fixtureDrafts(candidates) {
        const source = Array.isArray(candidates) && candidates.length ? candidates : [
            demoCandidate("generic-1", "方案 A", "等待你补充更多信息，当前先按演示维度比较。", {}, "这是用于展示结构化比较的演示属性，不代表真实外部数据。", "fit"),
            demoCandidate("generic-2", "方案 B", "等待你补充更多信息，当前先按演示维度比较。", {}, "这是用于展示结构化比较的演示属性，不代表真实外部数据。", "fit")
        ];
        return source.map(draftFromCandidate);
    }

    function applyCandidateInputStage(state, prompt, candidates, prefilledFrom) {
        const promptItems = promptDrafts(prompt, candidates);
        state.stage = "candidate_input";
        state.status = "collecting_candidates";
        state.candidateState = "draft";
        state.nextAction = "collect_candidates";
        state.candidateInput = {
            prefilledFrom: promptItems.length ? "prompt" : prefilledFrom,
            items: promptItems.length ? promptItems : fixtureDrafts(candidates)
        };
        state.trace = traceForStage("candidate_input");
        return state;
    }

    function baseState(fixture, prompt) {
        const state = clone(fixture);
        const timestamp = nowIso();
        state.id = `${fixture.id}-${Date.now().toString(36)}`;
        state.goal = prompt || fixture.goal;
        state.assumptions = ["当前为通用演示数据，非实时搜索结果；用于展示 Choice Agent 如何维护目标、约束、权重、候选和证据。"];
        state.recommendation = undefined;
        state.revision = 1;
        state.createdAt = timestamp;
        state.updatedAt = timestamp;
        return applyConstraintInputStage(state, prompt, state.candidates);
    }

    function candidateNames(prompt) {
        const matches = String(prompt || "").match(/[A-Z][\w-]*(?:\s*公司)?|[\u4e00-\u9fa5A-Za-z0-9]+(?:方案|公司|Offer|路线|电脑|本)/g) || [];
        return Array.from(new Set(matches.map((item) => item.trim()).filter((item) => item.length >= 2))).slice(0, 5);
    }

    function createGeneric(prompt) {
        const names = candidateNames(prompt);
        const cleanNames = names.length >= 2 ? names : ["方案 A", "方案 B"];
        const timestamp = nowIso();
        const state = {
            id: `demo-generic-${Date.now().toString(36)}`,
            status: "collecting_candidates",
            domain: "generic",
            stage: "candidate_input",
            candidateState: "draft",
            nextAction: "collect_candidates",
            goal: prompt || "比较已有选项，找出当前最值得优先选择的方案",
            constraints: [],
            criteria: [
                { key: "fit", label: "匹配需求", weight: 45, direction: "higher_better" },
                { key: "risk", label: "风险更低", weight: 30, direction: "lower_better" },
                { key: "costScore", label: "成本可控", weight: 25, direction: "higher_better" }
            ],
            unansweredQuestions: [],
            candidates: cleanNames.map((name, index) => demoCandidate(
                `generic-${index + 1}`,
                name,
                "等待你补充更多信息，当前先按可调整维度做粗略比较。",
                { fit: 76 - index * 6, risk: 32 + index * 9, costScore: 74 - index * 4 },
                "这是用于展示结构化比较的演示属性，不代表真实外部数据。",
                "fit"
            )),
            recommendation: undefined,
            assumptions: ["当前为通用结构演示，不含真实外部数据检索。"],
            trace: traceForStage("constraint_input"),
            revision: 1,
            createdAt: timestamp,
            updatedAt: timestamp
        };
        state.candidateInput = {
            prefilledFrom: names.length >= 2 ? "prompt" : "fixture",
            items: cleanNames.map((name, index) => ({
                id: draftId(index),
                sourceCandidateId: `generic-${index + 1}`,
                name,
                summary: state.candidates[index].summary
            }))
        };
        return state;
    }

    function detectDomain(prompt, explicitDomain) {
        if (explicitDomain && fixtures[explicitDomain]) {
            return explicitDomain;
        }
        const text = String(prompt || "").toLowerCase();
        if (/(旅行|周末|出发|目的地|旅游|两天一夜|travel)/i.test(text)) return "travel";
        if (/(offer|公司|职业|工作|跳槽|岗位|薪酬|career)/i.test(text)) return "career";
        if (/(学习|课程|入门|ai agent|agent|路线|文档|论文|learning)/i.test(text)) return "learning";
        if (/(电脑|笔记本|购物|买|通勤|性能|续航|shopping)/i.test(text)) return "shopping";
        return "generic";
    }

    function createDecision(prompt, explicitDomain) {
        const domain = detectDomain(prompt, explicitDomain);
        if (domain === "generic") {
            return saveDecision(createGeneric(prompt));
        }
        return saveDecision(baseState(fixtures[domain], prompt));
    }

    function normalizeDecision(decision) {
        const next = clone(decision);
        if (!next.stage) {
            next.stage = Array.isArray(next.candidates) && next.candidates.length ? "compare" : "candidate_input";
        }
        if (!next.constraintInput) {
            next.constraintInput = {
                prefilledFrom: Array.isArray(next.constraints) && next.constraints.length ? "fixture" : "domain_default",
                items: fixtureConstraintDrafts(next.domain, next.constraints)
            };
        }
        if (!Array.isArray(next.constraintInput.items) || !next.constraintInput.items.length) {
            next.constraintInput.items = [blankConstraintDraft(0)];
        }
        if (!next.candidateInput) {
            next.candidateInput = {
                prefilledFrom: "fixture",
                items: fixtureDrafts(next.candidates)
            };
        }
        if (!Array.isArray(next.candidateInput.items) || !next.candidateInput.items.length) {
            next.candidateInput.items = [blankDraft(0)];
        }
        return next;
    }

    function readStore() {
        try {
            const raw = window.localStorage.getItem(STORAGE_KEY);
            const parsed = raw ? JSON.parse(raw) : {};
            return parsed && typeof parsed === "object" ? parsed : {};
        } catch (error) {
            return {};
        }
    }

    function writeStore(store) {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
    }

    function saveDecision(decision) {
        const store = readStore();
        const normalized = normalizeDecision(decision);
        store[normalized.id] = normalized;
        writeStore(store);
        window.localStorage.setItem(LAST_ID_KEY, normalized.id);
        return normalized;
    }

    function loadDecision(id) {
        const store = readStore();
        if (id && store[id]) {
            return normalizeDecision(store[id]);
        }
        const lastId = window.localStorage.getItem(LAST_ID_KEY);
        if (lastId && store[lastId]) {
            return normalizeDecision(store[lastId]);
        }
        return createDecision(fixtures.travel.goal, "travel");
    }

    function constraintDrafts(decision) {
        return normalizeDecision(decision).constraintInput.items;
    }

    function replaceConstraintDrafts(decision, items, prefilledFrom) {
        return updateDecision(decision, (next) => {
            next.constraintInput = {
                prefilledFrom: prefilledFrom || "manual",
                items: items.length ? items : [blankConstraintDraft(0)]
            };
            next.stage = "constraint_input";
            next.status = "collecting_constraints";
            next.nextAction = "collect_constraints";
            next.candidateState = "draft";
            next.recommendation = undefined;
            next.trace = traceForStage("constraint_input");
        });
    }

    function addConstraintDraft(decision) {
        const items = constraintDrafts(decision);
        return replaceConstraintDrafts(decision, [...items, blankConstraintDraft(items.length)], "manual");
    }

    function removeConstraintDraft(decision, draftIdToRemove) {
        const items = constraintDrafts(decision).filter((item) => item.id !== draftIdToRemove);
        return replaceConstraintDrafts(decision, items.length ? items : [blankConstraintDraft(0)], "manual");
    }

    function resetConstraintDrafts(decision) {
        return replaceConstraintDrafts(decision, fixtureConstraintDrafts(decision.domain, fixtures[decision.domain] ? fixtures[decision.domain].constraints : decision.constraints), "fixture");
    }

    function clearConstraintDrafts(decision) {
        return replaceConstraintDrafts(decision, [blankConstraintDraft(0)], "manual");
    }

    function constraintFromDraft(draft, index) {
        const label = String(draft.label || "").trim();
        return {
            key: draft.sourceConstraintKey || `customConstraint${index + 1}`,
            label,
            kind: draft.kind === "soft" ? "soft" : "hard",
            operator: "preference",
            value: String(draft.value || "").trim() || label,
            source: "user",
            confidence: draft.kind === "soft" ? 0.85 : 1
        };
    }

    function confirmConstraintDrafts(decision) {
        const normalized = normalizeDecision(decision);
        const valid = normalized.constraintInput.items
            .map((item) => ({ ...item, label: String(item.label || "").trim(), value: String(item.value || "").trim() }))
            .filter((item) => item.label);
        const next = updateDecision(normalized, (draft) => {
            draft.constraints = valid.map(constraintFromDraft);
            draft.constraintInput = { prefilledFrom: normalized.constraintInput.prefilledFrom || "manual", items: valid.length ? valid : [blankConstraintDraft(0)] };
            draft.stage = "candidate_input";
            draft.status = "collecting_candidates";
            draft.candidateState = "draft";
            draft.nextAction = "collect_candidates";
            draft.recommendation = undefined;
            draft.trace = traceForStage("candidate_input");
        });
        return { decision: next, warning: valid.length ? null : "已跳过约束，接下来确认候选项。" };
    }

    function editConstraints(decision) {
        return updateDecision(decision, (next) => {
            next.stage = "constraint_input";
            next.status = "collecting_constraints";
            next.nextAction = "collect_constraints";
            next.candidateState = "draft";
            next.constraintInput = {
                prefilledFrom: "manual",
                items: fixtureConstraintDrafts(next.domain, next.constraints)
            };
            next.recommendation = undefined;
            next.trace = traceForStage("constraint_input");
        });
    }
    function candidateDrafts(decision) {
        return normalizeDecision(decision).candidateInput.items;
    }

    function replaceCandidateDrafts(decision, items, prefilledFrom) {
        return updateDecision(decision, (next) => {
            next.candidateInput = {
                prefilledFrom: prefilledFrom || "manual",
                items: items.length ? items : [blankDraft(0)]
            };
            next.stage = "candidate_input";
            next.candidateState = "draft";
            next.nextAction = "collect_candidates";
            next.status = "collecting_candidates";
            next.recommendation = undefined;
            next.trace = traceForStage("candidate_input");
        });
    }

    function addCandidateDraft(decision) {
        const items = candidateDrafts(decision);
        return replaceCandidateDrafts(decision, [...items, blankDraft(items.length)], "manual");
    }

    function removeCandidateDraft(decision, draftIdToRemove) {
        const items = candidateDrafts(decision).filter((item) => item.id !== draftIdToRemove);
        return replaceCandidateDrafts(decision, items.length ? items : [blankDraft(0)], "manual");
    }

    function resetCandidateDrafts(decision) {
        const fixture = fixtures[decision.domain];
        const source = fixture ? fixture.candidates : decision.candidates;
        return replaceCandidateDrafts(decision, fixtureDrafts(source), "fixture");
    }

    function clearCandidateDrafts(decision) {
        return replaceCandidateDrafts(decision, [blankDraft(0)], "manual");
    }

    function defaultAttributes(criteria, index) {
        return (criteria || []).reduce((result, criterion, criterionIndex) => {
            const offset = (index * 7 + criterionIndex * 3) % 15;
            result[criterion.key] = criterion.direction === "lower_better" ? 28 + offset : 82 - offset;
            return result;
        }, {});
    }

    function candidateFromDraft(decision, draft, index) {
        const name = String(draft.name || "").trim();
        const summary = String(draft.summary || "").trim() || "等待你补充更多信息，当前先按演示维度比较。";
        const source = (decision.candidates || []).find((candidate) => candidate.id === draft.sourceCandidateId);
        const id = source ? source.id : `custom-${String(draft.id || index).replace(/[^a-zA-Z0-9-]/g, "")}`;
        if (source) {
            const next = clone(source);
            next.name = name;
            next.summary = summary;
            next.eliminated = false;
            next.evidence = (next.evidence || []).map((item) => ({ ...item, candidateId: next.id }));
            return next;
        }
        const strongest = (decision.criteria || [])[0] || { key: "fit", label: "匹配需求" };
        return demoCandidate(
            id,
            name,
            summary,
            defaultAttributes(decision.criteria, index),
            `「${name}」是你补充的演示候选，当前使用本地演示属性参与比较。`,
            strongest.key
        );
    }

    function confirmCandidateDrafts(decision) {
        const normalized = normalizeDecision(decision);
        const valid = normalized.candidateInput.items
            .map((item) => ({ ...item, name: String(item.name || "").trim(), summary: String(item.summary || "").trim() }))
            .filter((item) => item.name);
        if (valid.length < 2) {
            return { decision: normalized, error: "至少需要 2 个候选项，才能开始比较。" };
        }
        const next = updateDecision(normalized, (draft) => {
            draft.candidates = valid.map((item, index) => candidateFromDraft(normalized, item, index));
            draft.candidateInput = { prefilledFrom: normalized.candidateInput.prefilledFrom || "manual", items: valid };
            draft.stage = "compare";
            draft.status = "comparing";
            draft.candidateState = "complete";
            draft.nextAction = "compare";
            draft.recommendation = undefined;
            draft.trace = traceForStage("compare");
        });
        return { decision: next, error: null };
    }

    function editCandidates(decision) {
        return updateDecision(decision, (next) => {
            next.stage = "candidate_input";
            next.status = "collecting_candidates";
            next.candidateState = "draft";
            next.nextAction = "collect_candidates";
            next.candidateInput = {
                prefilledFrom: "manual",
                items: fixtureDrafts(next.candidates)
            };
            next.recommendation = undefined;
            next.trace = traceForStage("candidate_input");
        });
    }

    function normalize(value, direction) {
        const number = Number(value);
        if (!Number.isFinite(number)) return 0;
        if (direction === "lower_better") {
            return Math.max(0, Math.min(100, 100 - number));
        }
        return Math.max(0, Math.min(100, number));
    }

    function rank(decision) {
        if (!decision || !Array.isArray(decision.candidates) || !Array.isArray(decision.criteria)) {
            return [];
        }
        const totalWeight = decision.criteria.reduce((sum, criterion) => sum + Number(criterion.weight || 0), 0) || 1;
        return decision.candidates
            .map((candidate, index) => {
                const score = decision.criteria.reduce((sum, criterion) => {
                    const value = candidate.attributes ? candidate.attributes[criterion.key] : undefined;
                    return sum + normalize(value, criterion.direction) * Number(criterion.weight || 0);
                }, 0) / totalWeight;
                return { candidate, score: Math.round(score), index };
            })
            .sort((left, right) => {
                if (left.candidate.eliminated !== right.candidate.eliminated) {
                    return left.candidate.eliminated ? 1 : -1;
                }
                if (right.score !== left.score) {
                    return right.score - left.score;
                }
                return left.index - right.index;
            });
    }

    function explain(decision) {
        if (decision.stage === "constraint_input" || decision.stage === "candidate_input" || decision.candidateState !== "complete") {
            return { candidateId: null, conclusion: "先确认候选项，再生成演示结论。", reasons: [], tradeOffs: [] };
        }
        const active = rank(decision).filter((item) => !item.candidate.eliminated);
        const top = active[0];
        if (!top) {
            return { candidateId: null, conclusion: "当前候选都已排除，先恢复至少一个候选再生成结论。", reasons: [], tradeOffs: [] };
        }
        const alternative = active[1];
        const evidence = top.candidate.evidence || [];
        const reasonItems = evidence.slice(0, 2);
        const strongest = decision.criteria.reduce((best, item) => Number(item.weight) > Number(best.weight) ? item : best, decision.criteria[0]);
        const reasons = reasonItems.length
            ? reasonItems.map((item) => ({ text: item.claim, evidenceIds: [item.id] }))
            : [{ text: `${top.candidate.name} 在“${strongest.label}”这个高权重维度上更占优。`, evidenceIds: [] }];
        return {
            candidateId: top.candidate.id,
            conclusion: `基于当前演示权重，优先选择「${top.candidate.name}」。这不是实时搜索结论，而是用固定演示数据展示结构化决策过程。`,
            reasons,
            tradeOffs: [`当前排序由 ${decision.criteria.length} 个维度加权得到；你可以调整权重观察结论如何变化。`],
            alternative: alternative ? {
                candidateId: alternative.candidate.id,
                whenToChoose: `如果你更看重它的特定优势，可以改选「${alternative.candidate.name}」。`,
                evidenceIds: (alternative.candidate.evidence || []).slice(0, 1).map((item) => item.id)
            } : undefined
        };
    }

    function updateDecision(decision, updater) {
        const next = normalizeDecision(decision);
        updater(next);
        next.revision = Number(next.revision || 0) + 1;
        next.updatedAt = nowIso();
        return saveDecision(next);
    }

    window.ChoiceAgentDemo = {
        domainLabels,
        createDecision,
        loadDecision,
        saveDecision,
        updateDecision,
        constraintDrafts,
        replaceConstraintDrafts,
        addConstraintDraft,
        removeConstraintDraft,
        resetConstraintDrafts,
        clearConstraintDrafts,
        confirmConstraintDrafts,
        editConstraints,
        candidateDrafts,
        replaceCandidateDrafts,
        addCandidateDraft,
        removeCandidateDraft,
        resetCandidateDrafts,
        clearCandidateDrafts,
        confirmCandidateDrafts,
        editCandidates,
        rank,
        explain,
        detectDomain
    };
})();