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

    function baseState(fixture, prompt) {
        const state = clone(fixture);
        const timestamp = nowIso();
        state.id = `${fixture.id}-${Date.now().toString(36)}`;
        state.goal = prompt || fixture.goal;
        state.assumptions = ["当前为通用演示数据，非实时搜索结果；用于展示 Choice Agent 如何维护目标、约束、权重、候选和证据。"];
        state.trace = [
            { id: "understand", label: "理解目标", detail: "根据输入识别决策领域和候选结构。", status: "done" },
            { id: "compare", label: "比较候选", detail: "使用演示属性和权重进行稳定排序。", status: "current" },
            { id: "decide", label: "生成建议", detail: "在用户确认或调整权重后生成结论。", status: "todo" }
        ];
        state.recommendation = undefined;
        state.revision = 1;
        state.createdAt = timestamp;
        state.updatedAt = timestamp;
        return state;
    }

    function candidateNames(prompt) {
        const matches = String(prompt || "").match(/[A-Z][\w-]*(?:\s*公司)?|[\u4e00-\u9fa5A-Za-z0-9]+(?:方案|公司|Offer|路线|电脑|本)/g) || [];
        return Array.from(new Set(matches.map((item) => item.trim()).filter((item) => item.length >= 2))).slice(0, 5);
    }

    function createGeneric(prompt) {
        const names = candidateNames(prompt);
        const cleanNames = names.length >= 2 ? names : ["方案 A", "方案 B"];
        const timestamp = nowIso();
        return {
            id: `demo-generic-${Date.now().toString(36)}`,
            status: "comparing",
            domain: "generic",
            candidateState: names.length >= 2 ? "complete" : "unknown",
            nextAction: "compare",
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
            trace: [
                { id: "understand", label: "理解目标", detail: "将开放式输入整理成可比较的候选结构。", status: "done" },
                { id: "compare", label: "比较候选", detail: "使用演示属性和权重进行稳定排序。", status: "current" }
            ],
            revision: 1,
            createdAt: timestamp,
            updatedAt: timestamp
        };
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
        const state = baseState(fixtures[domain], prompt);
        if (domain === "career") {
            const names = candidateNames(prompt);
            if (names.length >= 2) {
                state.candidates = state.candidates.map((candidate, index) => {
                    const name = names[index] || candidate.name;
                    return {
                        ...candidate,
                        name,
                        evidence: candidate.evidence.map((item) => ({ ...item, candidateId: candidate.id }))
                    };
                });
            }
        }
        return saveDecision(state);
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
        store[decision.id] = decision;
        writeStore(store);
        window.localStorage.setItem(LAST_ID_KEY, decision.id);
        return decision;
    }

    function loadDecision(id) {
        const store = readStore();
        if (id && store[id]) {
            return store[id];
        }
        const lastId = window.localStorage.getItem(LAST_ID_KEY);
        if (lastId && store[lastId]) {
            return store[lastId];
        }
        return createDecision(fixtures.travel.goal, "travel");
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
        const next = clone(decision);
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
        rank,
        explain,
        detectDomain
    };
})();