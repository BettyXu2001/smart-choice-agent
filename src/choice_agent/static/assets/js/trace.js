(function () {
    "use strict";

    function escapeHtml(value) {
        return String(value ?? "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;");
    }

    function safeJson(value) {
        if (value === null || value === undefined || value === "") return "";
        try {
            const parsed = typeof value === "string" ? JSON.parse(value) : value;
            return JSON.stringify(parsed, null, 2);
        } catch (error) {
            return String(value);
        }
    }

    function traceJson(trace) {
        const value = trace && trace.traceJson;
        if (!value) return {};
        if (typeof value === "string") {
            try { return JSON.parse(value); } catch (error) { return {}; }
        }
        return value;
    }

    const LABELS = {
        intent: {
            MEAL_RECOMMENDATION: "餐食推荐",
            CLARIFY_NEEDED: "需要澄清",
            MEAL_ADJUST: "调整推荐",
            MEAL_PLAN: "三餐计划",
            HEALTH_RISK: "健康风险",
            OTHER: "其他"
        },
        domain: {
            diet: "饮食决策",
            travel: "旅行决策",
            shopping: "购物决策",
            generic: "通用决策"
        },
        status: {
            success: "成功",
            failed: "失败",
            fallback: "降级",
            skipped: "跳过",
            running: "运行中",
            unknown: "未记录",
            SUCCESS: "成功",
            FAILED: "失败"
        },
        change: {
            add: "新增",
            remove: "删除",
            replace: "修改",
            truncated: "已截断"
        },
        requestKind: {
            create: "创建决策",
            message: "继续对话",
            command: "手动调整",
            feedback: "用户反馈"
        },
        action: {
            ASK: "继续提问",
            READY: "信息足够"
        },
        stage: {
            "User Message": "用户输入",
            IntentAgent: "意图识别",
            UnderstandingAgent: "条件更新",
            ClarificationAgent: "澄清判断",
            "Candidate Retrieval": "候选检索",
            CandidateAgent: "候选检索",
            Evidence: "证据整理",
            "Hard Filter": "硬约束过滤",
            Ranking: "候选排序",
            RankAgent: "候选排序",
            PlanningAgent: "计划生成",
            CriticAgent: "质量检查",
            ExplanationAgent: "解释生成",
            RiskAgent: "风险检查",
            Feedback: "用户反馈",
            Selection: "推荐选择",
            Composition: "组合计划",
            Failure: "失败处理"
        }
    };

    const PATH_LABELS = [
        ["domainState.slots", "槽位/条件"],
        ["domainState.feedbackRound", "反馈轮次"],
        ["domainState.selection", "选择策略"],
        ["recommendation", "推荐结果"],
        ["constraints", "约束条件"],
        ["criteria", "评分标准"],
        ["candidates", "候选项"],
        ["candidateState", "候选状态"],
        ["evidence", "证据"],
        ["excludedCandidates", "排除候选"],
        ["riskFlags", "风险提示"],
        ["status", "决策状态"],
        ["nextAction", "下一步"],
        ["intent", "意图"],
        ["userGoal", "用户目标"]
    ];

    function valueLabel(value, category) {
        if (value === null || value === undefined || value === "") return "-";
        const text = String(value);
        return LABELS[category]?.[text] || LABELS[category]?.[text.toLowerCase()] || text;
    }

    function stageLabel(stage) {
        return valueLabel(stage || "Trace Step", "stage");
    }

    function statusLabel(status) {
        return valueLabel(String(status || "unknown").toLowerCase(), "status");
    }

    function shortId(value) {
        const text = String(value || "-");
        return text.length > 14 ? `${text.slice(0, 8)}...${text.slice(-4)}` : text;
    }

    function formatMs(value) {
        return value === null || value === undefined || value === "" ? "-" : `${value} ms`;
    }

    function formatDate(value) {
        if (!value) return "-";
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return String(value);
        return date.toLocaleString("zh-CN", { hour12: false });
    }

    function summarizeText(value, fallback = "-") {
        if (value === null || value === undefined || value === "") return fallback;
        if (typeof value === "string") return value.length > 96 ? `${value.slice(0, 96)}...` : value;
        if (Array.isArray(value)) return `${value.length} 项`;
        if (typeof value === "object") {
            const name = value.name || value.label || value.summary || value.primaryCandidateId || value.candidateId;
            if (name) return String(name);
            const keys = Object.keys(value);
            return keys.length ? `${keys.slice(0, 4).join("、")}${keys.length > 4 ? "..." : ""}` : "空对象";
        }
        return String(value);
    }

    function pathLabel(path) {
        const text = String(path || "$");
        const found = PATH_LABELS.find(([prefix]) => text === prefix || text.startsWith(`${prefix}.`) || text.startsWith(`${prefix}[`));
        return found ? `${found[1]} · ${text}` : text;
    }

    function legacyTimeline(trace) {
        const json = traceJson(trace);
        const events = json.events || [];
        return events.map((event, index) => ({
            eventId: `legacy-${index + 1}`,
            sequence: event.stepOrder || index + 1,
            stage: event.agentName || event.eventType || "Legacy Event",
            kind: event.eventType === "AGENT_CALL" ? "agent" : "operation",
            status: event.status ? String(event.status).toLowerCase() : "unknown",
            summary: "历史记录未拆分为业务时间轴",
            input: event.inputPayload,
            output: event.outputPayload || event,
            changes: [],
            refs: {},
        }));
    }

    function timeline(trace) {
        const json = traceJson(trace);
        return Array.isArray(json.timeline) && json.timeline.length ? json.timeline : legacyTimeline(trace);
    }

    function normalizeTrace(trace) {
        const json = traceJson(trace);
        const metadata = json.metadata || {};
        const summary = json.turnSummary || {};
        const nodes = timeline(trace);
        const recommendationChange = json.recommendationChange || summary.recommendationChange || {};
        return { trace, json, metadata, summary, nodes, recommendationChange };
    }

    function candidateLabel(trace, candidateId) {
        if (!candidateId) return "-";
        const json = traceJson(trace);
        const candidates = []
            .concat(json?.initialSnapshot?.candidates || [])
            .concat(json?.timeline?.flatMap((node) => node?.output?.candidates || node?.output?.ranked || []) || []);
        const found = candidates.find((item) => String(item.id || item.candidateId) === String(candidateId));
        return found ? `${found.name || candidateId} (${candidateId})` : candidateId;
    }

    function recommendationChangeText(trace) {
        const { recommendationChange: change } = normalizeTrace(trace);
        const before = change.before?.primaryCandidateId;
        const after = change.after?.primaryCandidateId;
        return {
            initial: `首次推荐 ${candidateLabel(trace, after)}`,
            changed: `${candidateLabel(trace, before)} -> ${candidateLabel(trace, after)}`,
            unchanged: `保持 ${candidateLabel(trace, after || before)}`,
            cleared: `清空 ${candidateLabel(trace, before)}`,
            no_recommendation: "本轮没有生成推荐",
        }[change.status] || "未记录推荐变化";
    }

    function traceListSummary(trace) {
        const { metadata, summary, nodes } = normalizeTrace(trace);
        return {
            traceId: trace.traceId || metadata.traceId || "-",
            sessionId: trace.sessionId || metadata.sessionId || "-",
            status: trace.status || summary.status || "UNKNOWN",
            statusLabel: statusLabel(trace.status || summary.status),
            createdAt: trace.createdAt || "",
            createdLabel: formatDate(trace.createdAt),
            userMessage: summary.userMessage || "未记录用户输入",
            intent: valueLabel(summary.intent || metadata.intent || "", "intent"),
            domain: valueLabel(metadata.domain || traceJson(trace).initialSnapshot?.domain || "", "domain"),
            duration: formatMs(trace.durationMs ?? traceJson(trace).durationMs),
            stepCount: nodes.length,
            labeled: Boolean(trace.labeledAt || trace.expectedIntent || trace.expectedSlots || trace.expectedClarifyAction)
        };
    }

    function renderHero(trace) {
        const { metadata, summary, nodes } = normalizeTrace(trace);
        const revision = `${metadata.revisionBefore ?? "-"} -> ${metadata.revisionAfter ?? "-"}`;
        return `
            <section class="trace-detail-hero">
                <div class="trace-hero-input">
                    <span>用户输入</span>
                    <strong>${escapeHtml(summary.userMessage || "未记录用户输入")}</strong>
                    <small>Trace ${escapeHtml(shortId(trace.traceId))} · Session ${escapeHtml(shortId(trace.sessionId))}</small>
                </div>
                <div class="trace-hero-metrics">
                    <div><span>本轮状态</span><strong>${escapeHtml(statusLabel(trace.status || summary.status))}</strong></div>
                    <div><span>耗时</span><strong>${escapeHtml(formatMs(trace.durationMs ?? traceJson(trace).durationMs))}</strong></div>
                    <div><span>步骤数</span><strong>${escapeHtml(nodes.length)}</strong></div>
                    <div><span>Revision</span><strong>${escapeHtml(revision)}</strong></div>
                    <div class="wide"><span>推荐变化</span><strong>${escapeHtml(recommendationChangeText(trace))}</strong></div>
                    <div><span>意图 / 领域</span><strong>${escapeHtml(`${valueLabel(summary.intent || "", "intent")} / ${valueLabel(metadata.domain || "", "domain")}`)}</strong></div>
                </div>
            </section>
        `;
    }

    function renderChangeValue(label, value) {
        return `<div class="trace-change-value"><span>${escapeHtml(label)}</span><code>${escapeHtml(summarizeText(value, "空"))}</code></div>`;
    }

    function renderChanges(changes) {
        if (!Array.isArray(changes) || !changes.length) return `<p class="muted">Decision State 本步骤未记录变化。</p>`;
        return `
            <ul class="trace-change-list readable">
                ${changes.slice(0, 24).map((change) => {
                    const type = String(change.type || "replace");
                    return `
                        <li class="trace-change-${escapeHtml(type)}">
                            <div class="trace-change-head">
                                <b>${escapeHtml(valueLabel(type, "change"))}</b>
                                <span>${escapeHtml(pathLabel(change.path || "$"))}</span>
                            </div>
                            <div class="trace-change-values">
                                ${type !== "add" ? renderChangeValue("原来", change.before) : ""}
                                ${type !== "remove" ? renderChangeValue("现在", change.after) : ""}
                            </div>
                            <details class="trace-json-details"><summary>查看完整变化 JSON</summary><pre class="json-box">${escapeHtml(safeJson({ before: change.before, after: change.after }))}</pre></details>
                        </li>
                    `;
                }).join("")}
                ${changes.length > 24 ? `<li class="muted">还有 ${escapeHtml(changes.length - 24)} 条变化未默认展示，可在原始 Trace JSON 中查看。</li>` : ""}
            </ul>
        `;
    }

    function renderNode(node) {
        const status = String(node.status || "unknown").toLowerCase();
        const shouldOpen = status === "failed" || status === "fallback";
        return `
            <details class="trace-node trace-node-${escapeHtml(status)}" ${shouldOpen ? "open" : ""}>
                <summary>
                    <span class="trace-node-index">${escapeHtml(node.sequence || "")}</span>
                    <span>
                        <strong>${escapeHtml(stageLabel(node.stage))}</strong>
                        <small>${escapeHtml(formatMs(node.durationMs ?? 0))} · ${escapeHtml(node.summary || "未记录摘要")}</small>
                    </span>
                    <b>${escapeHtml(statusLabel(status))}</b>
                </summary>
                <div class="trace-node-body">
                    <section class="trace-node-changes">
                        <h4>Decision State Changes</h4>
                        ${renderChanges(node.changes)}
                    </section>
                    <div class="trace-node-meta">
                        <span>类型：${escapeHtml(node.kind || "-")}</span>
                        <span>阶段：${escapeHtml(node.stage || "-")}</span>
                        <span>耗时：${escapeHtml(formatMs(node.durationMs ?? 0))}</span>
                    </div>
                    ${node.error ? `<div class="trace-alert">${escapeHtml(node.error)}</div>` : ""}
                    <details class="trace-json-details"><summary>输入 JSON</summary><pre class="json-box">${escapeHtml(safeJson(node.input))}</pre></details>
                    <details class="trace-json-details"><summary>输出 JSON</summary><pre class="json-box">${escapeHtml(safeJson(node.output))}</pre></details>
                    ${node.refs && Object.keys(node.refs).length ? `<details class="trace-json-details"><summary>引用 JSON</summary><pre class="json-box">${escapeHtml(safeJson(node.refs))}</pre></details>` : ""}
                </div>
            </details>
        `;
    }

    function render(trace) {
        const { json, nodes } = normalizeTrace(trace);
        const fallbackNodes = nodes.filter((node) => ["fallback", "failed"].includes(String(node.status || "").toLowerCase()));
        return `
            <div class="trace-observability">
                ${renderHero(trace)}
                ${fallbackNodes.length ? `<div class="trace-alert">本轮有 ${escapeHtml(fallbackNodes.length)} 个异常/降级节点：${escapeHtml(fallbackNodes.map((node) => `${stageLabel(node.stage)}：${node.summary || statusLabel(node.status)}`).join("；"))}</div>` : ""}
                <div class="trace-timeline" aria-label="决策过程时间轴">${nodes.map(renderNode).join("")}</div>
                <details class="trace-json-details raw"><summary>原始 Trace JSON</summary><pre class="json-box">${escapeHtml(safeJson(json))}</pre></details>
            </div>
        `;
    }

    function markdownValue(value) {
        if (value === null || value === undefined || value === "") return "-";
        if (typeof value === "string") return value;
        return `\n\`\`\`json\n${safeJson(value)}\n\`\`\``;
    }

    function traceMarkdown(trace, heading = "Trace") {
        const { metadata, summary, nodes, json } = normalizeTrace(trace);
        const lines = [
            `# ${heading} ${trace.traceId || ""}`.trim(),
            "",
            `- Trace ID: ${trace.traceId || "-"}`,
            `- Session ID: ${trace.sessionId || "-"}`,
            `- Created At: ${trace.createdAt || "-"}`,
            `- Status: ${statusLabel(trace.status || summary.status)}`,
            `- Duration: ${formatMs(trace.durationMs ?? json.durationMs)}`,
            `- Intent / Domain: ${valueLabel(summary.intent || "", "intent")} / ${valueLabel(metadata.domain || "", "domain")}`,
            `- Revision: ${metadata.revisionBefore ?? "-"} -> ${metadata.revisionAfter ?? "-"}`,
            `- Recommendation Change: ${recommendationChangeText(trace)}`,
            "",
            "## 用户输入",
            "",
            summary.userMessage || "未记录用户输入",
            "",
            "## Timeline",
            ""
        ];
        nodes.forEach((node) => {
            lines.push(`### ${node.sequence || ""}. ${stageLabel(node.stage)} · ${statusLabel(node.status)} · ${formatMs(node.durationMs ?? 0)}`.trim());
            lines.push("", node.summary || "未记录摘要", "");
            if (Array.isArray(node.changes) && node.changes.length) {
                lines.push("Decision State Changes:");
                node.changes.forEach((change) => lines.push(`- ${valueLabel(change.type || "replace", "change")} ${pathLabel(change.path || "$")}: ${summarizeText(change.before, "-")} -> ${summarizeText(change.after, "-")}`));
                lines.push("");
            }
            lines.push("Input:", markdownValue(node.input), "", "Output:", markdownValue(node.output), "");
            if (node.refs && Object.keys(node.refs).length) lines.push("Refs:", markdownValue(node.refs), "");
            if (node.error) lines.push(`Error: ${node.error}`, "");
        });
        lines.push("## Initial DecisionState", markdownValue(json.initialSnapshot), "");
        lines.push("## Recommendation Change", markdownValue(json.recommendationChange || summary.recommendationChange), "");
        lines.push("## Observability Events", markdownValue(json.events || []), "");
        lines.push("## 人工标注", markdownValue({ expectedIntent: trace.expectedIntent, expectedSlots: trace.expectedSlots, expectedClarifyAction: trace.expectedClarifyAction, labeledBy: trace.labeledBy, labeledAt: trace.labeledAt, labelNote: trace.labelNote }), "");
        return lines.join("\n");
    }

    function exportTraceJson(trace) {
        return JSON.stringify({ exportType: "trace", exportedAt: new Date().toISOString(), trace }, null, 2);
    }

    function exportTraceMarkdown(trace) {
        return traceMarkdown(trace, "Trace 导出");
    }

    function sortTracesChronologically(traces) {
        return [...(traces || [])].sort((a, b) => new Date(a.createdAt || 0) - new Date(b.createdAt || 0));
    }

    function exportSessionJson(sessionId, traces, limit) {
        const sorted = sortTracesChronologically(traces);
        return JSON.stringify({ exportType: "session", exportedAt: new Date().toISOString(), sessionId, traceCount: sorted.length, limit, traces: sorted }, null, 2);
    }

    function exportSessionMarkdown(sessionId, traces, limit) {
        const sorted = sortTracesChronologically(traces);
        const lines = [`# Session Trace 导出 ${sessionId}`, "", `- Exported At: ${new Date().toISOString()}`, `- Trace Count: ${sorted.length}`, `- Limit: ${limit}`, "", "## Trace 目录", ""];
        sorted.forEach((trace, index) => {
            const item = traceListSummary(trace);
            lines.push(`${index + 1}. ${item.createdLabel} · ${item.statusLabel} · ${item.intent} / ${item.domain} · ${item.duration} · ${trace.traceId}`);
        });
        sorted.forEach((trace, index) => lines.push("", "---", "", traceMarkdown(trace, `Trace ${index + 1}`)));
        return lines.join("\n");
    }

    window.TraceTimeline = {
        render,
        traceJson,
        traceListSummary,
        valueLabel,
        recommendationChangeText,
        exportTraceJson,
        exportTraceMarkdown,
        exportSessionJson,
        exportSessionMarkdown,
        sortTracesChronologically
    };
})();