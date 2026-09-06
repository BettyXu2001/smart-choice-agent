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
        if (value === null || value === undefined || value === "") {
            return "";
        }
        try {
            const parsed = typeof value === "string" ? JSON.parse(value) : value;
            return JSON.stringify(parsed, null, 2);
        } catch (error) {
            return String(value);
        }
    }

    function traceJson(trace) {
        const value = trace && trace.traceJson;
        if (!value) {
            return {};
        }
        if (typeof value === "string") {
            try {
                return JSON.parse(value);
            } catch (error) {
                return {};
            }
        }
        return value;
    }

    function candidateLabel(trace, candidateId) {
        if (!candidateId) {
            return "-";
        }
        const json = traceJson(trace);
        const candidates = []
            .concat(json?.initialSnapshot?.candidates || [])
            .concat(json?.timeline?.flatMap((node) => node?.output?.candidates || node?.output?.ranked || []) || []);
        const found = candidates.find((item) => String(item.id || item.candidateId) === String(candidateId));
        return found ? `${found.name || candidateId} (${candidateId})` : candidateId;
    }

    function statusLabel(status) {
        return {
            success: "成功",
            failed: "失败",
            fallback: "降级",
            skipped: "跳过",
            running: "运行中",
            unknown: "未拆分",
        }[String(status || "").toLowerCase()] || String(status || "unknown");
    }

    function stageLabel(stage) {
        return {
            "User Message": "User Message",
            "IntentAgent": "Intent Understanding",
            "UnderstandingAgent": "Constraint Update",
            "ClarificationAgent": "Clarification",
            "CandidateAgent": "Candidate Retrieval",
            "RankAgent": "Ranking",
            "PlanningAgent": "Planning",
            "CriticAgent": "Critic Check",
            "ExplanationAgent": "Explanation",
            "RiskAgent": "Risk Check",
        }[stage] || stage || "Trace Step";
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

    function renderMetricCards(trace) {
        const json = traceJson(trace);
        const summary = json.turnSummary || {};
        const change = json.recommendationChange || summary.recommendationChange || {};
        const metadata = json.metadata || {};
        const before = change.before?.primaryCandidateId;
        const after = change.after?.primaryCandidateId;
        const changeText = {
            initial: `首次推荐 ${candidateLabel(trace, after)}`,
            changed: `${candidateLabel(trace, before)} → ${candidateLabel(trace, after)}`,
            unchanged: `保持 ${candidateLabel(trace, after || before)}`,
            cleared: `清空 ${candidateLabel(trace, before)}`,
            no_recommendation: "本轮没有生成推荐",
        }[change.status] || "未记录推荐变化";
        return `
            <div class="trace-summary-grid">
                <div class="trace-summary-card">
                    <span>用户输入</span>
                    <strong>${escapeHtml(summary.userMessage || "-")}</strong>
                </div>
                <div class="trace-summary-card">
                    <span>意图 / 领域</span>
                    <strong>${escapeHtml(summary.intent || metadata.domain || "-")}</strong>
                </div>
                <div class="trace-summary-card">
                    <span>Revision</span>
                    <strong>${escapeHtml(metadata.revisionBefore ?? "-")} → ${escapeHtml(metadata.revisionAfter ?? "-")}</strong>
                </div>
                <div class="trace-summary-card">
                    <span>推荐变化</span>
                    <strong>${escapeHtml(changeText)}</strong>
                </div>
            </div>
        `;
    }

    function renderChanges(changes) {
        if (!Array.isArray(changes) || !changes.length) {
            return `<p class="muted">Decision State 未记录变化。</p>`;
        }
        return `
            <ul class="trace-change-list">
                ${changes.slice(0, 20).map((change) => `
                    <li>
                        <code>${escapeHtml(change.path || "$")}</code>
                        <span>${escapeHtml(change.type || "replace")}</span>
                        <pre class="json-box">${escapeHtml(safeJson({ before: change.before, after: change.after }))}</pre>
                    </li>
                `).join("")}
            </ul>
        `;
    }

    function renderNode(node) {
        const status = String(node.status || "unknown").toLowerCase();
        const hasPrompt = node.input && (node.input.systemPrompt || node.input.userPrompt);
        return `
            <details class="trace-node trace-node-${escapeHtml(status)}" ${node.sequence <= 2 ? "open" : ""}>
                <summary>
                    <span class="trace-node-index">${escapeHtml(node.sequence || "")}</span>
                    <span>
                        <strong>${escapeHtml(stageLabel(node.stage))}</strong>
                        <small>${escapeHtml(node.summary || "")}</small>
                    </span>
                    <b>${escapeHtml(statusLabel(status))}</b>
                </summary>
                <div class="trace-node-body">
                    <div class="trace-node-meta">
                        <span>Kind: ${escapeHtml(node.kind || "-")}</span>
                        <span>Duration: ${escapeHtml(node.durationMs ?? 0)} ms</span>
                        ${node.refs && Object.keys(node.refs).length ? `<span>Refs: ${escapeHtml(Object.keys(node.refs).join(", "))}</span>` : ""}
                    </div>
                    ${hasPrompt ? `
                        <div class="trace-detail-grid">
                            <section>
                                <h4>Prompt</h4>
                                <pre class="json-box">${escapeHtml(safeJson({ systemPrompt: node.input.systemPrompt, userPrompt: node.input.userPrompt }))}</pre>
                            </section>
                            <section>
                                <h4>模型结果</h4>
                                <pre class="json-box">${escapeHtml(safeJson(node.output))}</pre>
                            </section>
                        </div>
                    ` : `
                        <div class="trace-detail-grid">
                            <section>
                                <h4>输入</h4>
                                <pre class="json-box">${escapeHtml(safeJson(node.input))}</pre>
                            </section>
                            <section>
                                <h4>输出</h4>
                                <pre class="json-box">${escapeHtml(safeJson(node.output))}</pre>
                            </section>
                        </div>
                    `}
                    <section>
                        <h4>Decision State 变化</h4>
                        ${renderChanges(node.changes)}
                    </section>
                    ${node.refs && Object.keys(node.refs).length ? `
                        <section>
                            <h4>引用</h4>
                            <pre class="json-box">${escapeHtml(safeJson(node.refs))}</pre>
                        </section>
                    ` : ""}
                </div>
            </details>
        `;
    }

    function render(trace) {
        const json = traceJson(trace);
        const nodes = timeline(trace);
        const fallbackNodes = nodes.filter((node) => String(node.status || "").toLowerCase() === "fallback");
        return `
            <div class="trace-observability">
                ${renderMetricCards(trace)}
                ${fallbackNodes.length ? `<div class="trace-alert">本轮触发 ${fallbackNodes.length} 次 fallback：${escapeHtml(fallbackNodes.map((node) => node.summary).join("；"))}</div>` : ""}
                <div class="trace-timeline" aria-label="决策过程时间轴">
                    ${nodes.map(renderNode).join("")}
                </div>
                <details>
                    <summary>Trace JSON</summary>
                    <pre class="json-box">${escapeHtml(safeJson(json))}</pre>
                </details>
            </div>
        `;
    }

    window.TraceTimeline = { render };
})();
