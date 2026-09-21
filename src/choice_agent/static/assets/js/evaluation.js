(function () {
    "use strict";

    window.createEvaluationDashboard = function (deps) {
        const {state, app, showToast, escapeHtml, safeJson, statCard, formatScore} = deps;
        const evaluation = state.evaluation;

        function selectedCase() {
            return (evaluation.dashboard?.cases || []).find(item => item.id === evaluation.selectedCaseId) || null;
        }

        function selectedRun() {
            return evaluation.selectedRun || evaluation.dashboard?.latestRun || null;
        }

        function render() {
            if (!evaluation.dashboard && !evaluation.loading) {
                loadDashboard();
            }
            const dashboard = evaluation.dashboard;
            if (evaluation.loading && !dashboard) {
                app.innerHTML = `<section class="section evaluation-shell"><div class="empty">正在加载 Evaluation Dashboard...</div></section>`;
                return;
            }
            if (!dashboard) {
                app.innerHTML = `<section class="section evaluation-shell"><div class="empty">Evaluation Dashboard 暂不可用。</div></section>`;
                return;
            }
            const run = selectedRun();
            app.innerHTML = `
                <section class="evaluation-shell">
                    <div class="evaluation-header">
                        <div>
                            <span class="eyebrow">Evaluation Dashboard</span>
                            <h2>评估闭环</h2>
                            <p>Bad Case → 归因 → 修改 → 离线评测 → 回归集 → 持续监控</p>
                        </div>
                        <div class="inline-actions">
                            <button class="btn soft" type="button" data-eval-action="refresh">刷新</button>
                            <a class="btn ghost" href="#/admin/traces">Trace</a>
                        </div>
                    </div>
                    ${renderOverview(dashboard, run)}
                    <div class="evaluation-tabs" role="tablist" aria-label="评估视图">
                        ${tabButton("dashboard", "总览")}
                        ${tabButton("bad-cases", "Bad Case")}
                        ${tabButton("datasets", "Regression Dataset")}
                        ${tabButton("legacy", "旧 Trace 报告")}
                    </div>
                    ${evaluation.mode === "bad-cases" ? renderBadCases(dashboard) : ""}
                    ${evaluation.mode === "datasets" ? renderDatasets(dashboard) : ""}
                    ${evaluation.mode === "legacy" ? renderLegacyNotice() : ""}
                    ${evaluation.mode === "dashboard" ? renderDashboardBody(dashboard, run) : ""}
                </section>
            `;
        }

        function renderOverview(dashboard, run) {
            const summary = run?.summary || {};
            const coverage = summary.coverage || {};
            const comparison = dashboard.comparison;
            return `
                <div class="grid four evaluation-overview">
                    ${statCard("当前版本得分", summary.overallScore === null || summary.overallScore === undefined ? "未评测" : `${summary.overallScore}`, `确定性覆盖 ${coverage.deterministicEvaluatedMetricCount || 0}/${coverage.deterministicMetricCount || 16}；人工 ${coverage.manualReviewMetricIds?.length || 0}`)}
                    ${statCard("与上一版本差异", comparison ? `${comparison.scoreDelta > 0 ? "+" : ""}${comparison.scoreDelta}` : "不可比", comparison ? `基线 ${comparison.baselineRunId.slice(0, 8)}` : "需相同数据集/评估器/模式")}
                    ${statCard("失败 Case", summary.caseCounts?.failed || 0, `错误 ${summary.caseCounts?.error || 0}，未评测 ${summary.caseCounts?.notEvaluated || 0}`)}
                    ${statCard("Regression Dataset", dashboard.datasets.length, `${dashboard.cases.filter(item => item.status === "verified").length} 个已验证 Case`)}
                </div>
            `;
        }

        function renderDashboardBody(dashboard, run) {
            return `
                <div class="evaluation-grid">
                    <section class="section evaluation-panel">
                        <div class="card-title">
                            <div>
                                <h3>运行评估</h3>
                                <p>默认使用 fixture/mock；真实模型需要显式选择。</p>
                            </div>
                        </div>
                        ${renderRunForm(dashboard)}
                        ${renderRunList(dashboard.runs || [])}
                    </section>
                    <section class="section evaluation-panel">
                        <div class="card-title">
                            <div>
                                <h3>指标体系</h3>
                                <p>${dashboard.evaluatorVersion}，低优错误率已反向计分，响应时间单独展示。</p>
                            </div>
                        </div>
                        ${renderMetricGroups(run?.summary?.metrics || dashboard.metricDefinitions.map(def => ({...def, value: null, missingReason: "not_evaluated"})))}
                    </section>
                </div>
                ${run ? renderRunDetail(run) : `<section class="section evaluation-panel"><div class="empty">还没有运行记录。</div></section>`}
            `;
        }

        function renderRunForm(dashboard) {
            return `
                <form id="evaluationRunForm" class="form-grid evaluation-form">
                    <label class="field">
                        <span>版本标签</span>
                        <input name="versionLabel" value="local-${new Date().toISOString().slice(0, 10)}" required>
                    </label>
                    <label class="field">
                        <span>数据集</span>
                        <select name="datasetId">
                            <option value="">Bad Case Center 当前快照</option>
                            ${dashboard.datasets.map(item => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.name)} / ${escapeHtml(item.version)}</option>`).join("")}
                        </select>
                    </label>
                    <label class="field">
                        <span>模式</span>
                        <select name="mode">
                            <option value="fixture">fixture/mock</option>
                            <option value="historical">historical</option>
                            <option value="live_model">live_model</option>
                        </select>
                    </label>
                    <label class="field">
                        <span>重复次数</span>
                        <input name="repeat" type="number" min="1" max="3" value="1">
                    </label>
                    <div class="field full">
                        <button class="btn primary" type="submit" ${evaluation.loading ? "disabled" : ""}>${evaluation.loading ? "运行中..." : "运行离线评测"}</button>
                    </div>
                </form>
            `;
        }

        function renderRunList(runs) {
            if (!runs.length) {
                return `<div class="empty compact">暂无运行记录。</div>`;
            }
            return `<div class="evaluation-run-list">${runs.slice(0, 8).map(run => `
                <button type="button" class="evaluation-run-row ${selectedRun()?.id === run.id ? "active" : ""}" data-eval-action="select-run" data-run-id="${escapeHtml(run.id)}">
                    <span>${escapeHtml(run.versionLabel)}</span>
                    <strong>${run.summary?.overallScore ?? "未评测"}</strong>
                    <small>${escapeHtml(run.status)} · ${escapeHtml(run.datasetName)} ${escapeHtml(run.datasetVersion)}</small>
                </button>
            `).join("")}</div>`;
        }

        function renderMetricGroups(metrics) {
            const groups = {};
            (metrics || []).forEach(metric => {
                const category = metric.category || "其他";
                groups[category] = [...(groups[category] || []), metric];
            });
            return `<div class="metric-groups">${Object.entries(groups).map(([category, items]) => `
                <div class="metric-group">
                    <h4>${escapeHtml(category)}</h4>
                    ${items.map(renderMetric).join("")}
                </div>
            `).join("")}</div>`;
        }

        function renderMetric(metric) {
            const value = metric.value === null || metric.value === undefined
                ? "未评测"
                : metric.unit === "ms" ? `${Math.round(metric.value)}ms` : `${Math.round(metric.value * 100)}%`;
            const evaluationMethod = metric.evaluationMethod || (metric.value === null || metric.value === undefined ? "not_evaluated" : "deterministic");
            const methodLabel = {
                deterministic: "deterministic",
                manual: "manual review",
                not_evaluated: "not evaluated",
            }[evaluationMethod] || evaluationMethod;
            return `
                <div class="metric-row">
                    <div>
                        <strong>${escapeHtml(metric.label)}</strong>
                        <small>${escapeHtml(`${methodLabel} · ${metric.description || metric.missingReason || ""}`)}</small>
                    </div>
                    <span>${escapeHtml(value)}</span>
                </div>
            `;
        }

        function renderRunDetail(run) {
            const results = run.results || [];
            return `
                <section class="section evaluation-panel">
                    <div class="card-title">
                        <div>
                            <h3>运行详情</h3>
                            <p>${escapeHtml(run.versionLabel)} · ${escapeHtml(run.datasetName)} / ${escapeHtml(run.datasetVersion)} · ${escapeHtml(run.status)}</p>
                        </div>
                    </div>
                    ${results.length ? `<div class="table-wrap">
                        <table>
                            <thead><tr><th>Case</th><th>状态</th><th>轮次</th><th>失败断言</th><th>Trace</th></tr></thead>
                            <tbody>${results.map(result => {
                                const failed = (result.assertions || []).filter(item => item.passed === false);
                                const traceId = result.traceSnapshot?.traceId || result.outputs?.traceId;
                                return `<tr>
                                    <td>${escapeHtml(result.caseId.slice(0, 8))}</td>
                                    <td><span class="status-pill ${escapeHtml(result.status)}">${escapeHtml(result.status)}</span></td>
                                    <td>${escapeHtml(result.repetition)}</td>
                                    <td>${failed.length ? failed.map(item => escapeHtml(item.metricId)).join("<br>") : "无"}</td>
                                    <td>${traceId ? `<button class="btn ghost compact" data-action="open-trace" data-trace-id="${escapeHtml(traceId)}">打开 Trace</button>` : "快照不可用"}</td>
                                </tr>`;
                            }).join("")}</tbody>
                        </table>
                    </div>` : `<div class="empty">这个运行还没有结果。</div>`}
                    ${results[0] ? `<details class="evaluation-json"><summary>查看首个结果 Trace / 输出 JSON</summary><pre class="json-box">${escapeHtml(safeJson({outputs: results[0].outputs, trace: results[0].traceSnapshot, assertions: results[0].assertions}))}</pre></details>` : ""}
                </section>
            `;
        }

        function renderBadCases(dashboard) {
            const selected = selectedCase() || dashboard.cases[0] || null;
            if (selected && !evaluation.selectedCaseId) {
                evaluation.selectedCaseId = selected.id;
            }
            return `
                <div class="evaluation-grid">
                    <section class="section evaluation-panel">
                        <div class="card-title">
                            <div>
                                <h3>Bad Case Center</h3>
                                <p>记录原问题、预期/实际、错误类型、归因、涉及模块和修复版本。</p>
                            </div>
                        </div>
                        ${renderCaseFilters(dashboard)}
                        ${renderCaseList(dashboard.cases)}
                        ${renderCaseCreateForm(dashboard)}
                    </section>
                    <section class="section evaluation-panel">
                        ${selected ? renderCaseDetail(selected) : `<div class="empty">暂无 Case。</div>`}
                    </section>
                </div>
            `;
        }

        function renderCaseFilters(dashboard) {
            return `
                <form id="evaluationCaseFilterForm" class="form-grid evaluation-form">
                    <label class="field"><span>状态</span><select name="status"><option value="">全部</option>${dashboard.lifecycle.map(item => `<option value="${escapeHtml(item)}" ${evaluation.filters.status === item ? "selected" : ""}>${escapeHtml(item)}</option>`).join("")}</select></label>
                    <label class="field"><span>错误类型</span><select name="errorType"><option value="">全部</option>${dashboard.taxonomy.map(item => `<option value="${escapeHtml(item)}" ${evaluation.filters.errorType === item ? "selected" : ""}>${escapeHtml(item)}</option>`).join("")}</select></label>
                    <label class="field"><span>模块</span><input name="module" value="${escapeHtml(evaluation.filters.module)}" placeholder="decision.assistance"></label>
                    <label class="field"><span>搜索</span><input name="q" value="${escapeHtml(evaluation.filters.q)}" placeholder="原问题 / 标题"></label>
                    <div class="field full"><button class="btn soft" type="submit">筛选</button></div>
                </form>
            `;
        }

        function renderCaseList(cases) {
            if (!cases.length) {
                return `<div class="empty compact">暂无匹配 Case。</div>`;
            }
            return `<div class="evaluation-case-list">${cases.map(item => `
                <button type="button" class="evaluation-case-row ${evaluation.selectedCaseId === item.id ? "active" : ""}" data-eval-action="select-case" data-case-id="${escapeHtml(item.id)}">
                    <span>${escapeHtml(item.title)}</span>
                    <small>${escapeHtml(item.errorType)} · ${escapeHtml(item.status)} · v${escapeHtml(item.revision)}</small>
                </button>
            `).join("")}</div>`;
        }

        function renderCaseCreateForm(dashboard) {
            return `
                <details class="evaluation-editor">
                    <summary>新增 Bad Case</summary>
                    <form id="evaluationCaseCreateForm" class="form-grid evaluation-form">
                        <label class="field full"><span>标题</span><input name="title" required></label>
                        <label class="field full"><span>原始用户问题</span><textarea name="originalQuestion" required></textarea></label>
                        <label class="field full"><span>预期行为</span><textarea name="expectedBehavior" required></textarea></label>
                        <label class="field full"><span>实际行为</span><textarea name="actualBehavior"></textarea></label>
                        <label class="field"><span>错误类型</span><select name="errorType">${dashboard.taxonomy.map(item => `<option>${escapeHtml(item)}</option>`).join("")}</select></label>
                        <label class="field"><span>涉及模块</span><input name="modules" placeholder="逗号分隔"></label>
                        <label class="field full"><span>Case Data JSON</span><textarea name="caseData" placeholder='{"domain":"generic","assertions":[]}'></textarea></label>
                        <div class="field full"><button class="btn primary" type="submit">保存 Case</button></div>
                    </form>
                </details>
            `;
        }

        function renderCaseDetail(item) {
            return `
                <div class="card-title">
                    <div>
                        <h3>${escapeHtml(item.title)}</h3>
                        <p>${escapeHtml(item.errorType)} · ${escapeHtml(item.status)} · revision ${escapeHtml(item.revision)}</p>
                    </div>
                </div>
                <div class="case-detail-grid">
                    <div><span class="muted">原始问题</span><p>${escapeHtml(item.originalQuestion)}</p></div>
                    <div><span class="muted">预期行为</span><p>${escapeHtml(item.expectedBehavior)}</p></div>
                    <div><span class="muted">实际行为</span><p>${escapeHtml(item.actualBehavior || "未记录")}</p></div>
                    <div><span class="muted">问题归因</span><p>${escapeHtml(item.diagnosis || "待归因")}</p></div>
                    <div><span class="muted">涉及模块</span><p>${escapeHtml((item.modules || []).join(", ") || "未标注")}</p></div>
                    <div><span class="muted">修复方案 / 版本</span><p>${escapeHtml(item.fixPlan || "待填写")} ${item.fixVersion ? `· ${escapeHtml(item.fixVersion)}` : ""}</p></div>
                </div>
                <form id="evaluationCaseUpdateForm" class="form-grid evaluation-form" data-case-id="${escapeHtml(item.id)}">
                    <input type="hidden" name="revision" value="${escapeHtml(item.revision)}">
                    <label class="field"><span>状态</span><select name="status">${["open", "diagnosed", "fix_pending", "awaiting_regression", "verified", "reopened"].map(status => `<option value="${status}" ${item.status === status ? "selected" : ""}>${status}</option>`).join("")}</select></label>
                    <label class="field"><span>修复版本</span><input name="fixVersion" value="${escapeHtml(item.fixVersion || "")}"></label>
                    <label class="field full"><span>问题归因</span><textarea name="diagnosis">${escapeHtml(item.diagnosis || "")}</textarea></label>
                    <label class="field full"><span>修改方案</span><textarea name="fixPlan">${escapeHtml(item.fixPlan || "")}</textarea></label>
                    <div class="field full"><button class="btn primary" type="submit">更新 Case</button></div>
                </form>
                <details class="evaluation-json"><summary>Case Data / 审计</summary><pre class="json-box">${escapeHtml(safeJson({caseData: item.caseData, audit: item.auditEvents}))}</pre></details>
            `;
        }

        function renderDatasets(dashboard) {
            return `
                <div class="evaluation-grid">
                    <section class="section evaluation-panel">
                        <div class="card-title"><div><h3>Regression Dataset</h3><p>数据集保存 Case 输入和断言快照，版本不可变。</p></div></div>
                        ${dashboard.datasets.length ? `<div class="table-wrap"><table><thead><tr><th>名称</th><th>版本</th><th>Case</th><th>Hash</th></tr></thead><tbody>${dashboard.datasets.map(item => `<tr><td>${escapeHtml(item.name)}</td><td>${escapeHtml(item.version)}</td><td>${item.caseCount}</td><td><code>${escapeHtml(item.datasetHash.slice(0, 12))}</code></td></tr>`).join("")}</tbody></table></div>` : `<div class="empty">暂无 Regression Dataset。</div>`}
                    </section>
                    <section class="section evaluation-panel">
                        <div class="card-title"><div><h3>创建数据集版本</h3><p>选择已归因或待回归 Case，生成固定版本。</p></div></div>
                        <form id="evaluationDatasetForm" class="form-grid evaluation-form">
                            <label class="field"><span>名称</span><input name="name" value="core-regression" required></label>
                            <label class="field"><span>版本</span><input name="version" value="v${new Date().toISOString().slice(0, 10)}" required></label>
                            <label class="field full"><span>说明</span><textarea name="description">核心 Bad Case 回归集</textarea></label>
                            <div class="dataset-case-picker field full">
                                ${(dashboard.cases || []).map(item => `<label><input type="checkbox" name="caseIds" value="${escapeHtml(item.id)}" ${["diagnosed", "awaiting_regression", "verified", "reopened"].includes(item.status) ? "checked" : ""}> <span>${escapeHtml(item.title)} · ${escapeHtml(item.status)}</span></label>`).join("")}
                            </div>
                            <div class="field full"><button class="btn primary" type="submit">创建 Dataset Version</button></div>
                        </form>
                    </section>
                </div>
            `;
        }

        function renderLegacyNotice() {
            return `
                <section class="section evaluation-panel">
                    <div class="card-title"><div><h3>旧版 Trace 报告</h3><p>保留原有 `/api/v1/diet/evaluations` 口径，用于饮食 Trace 规则评分、反馈和可选 LLM Judge。</p></div></div>
                    <form id="evaluationForm" class="form-grid">
                        <div class="field"><label>开始时间</label><input type="datetime-local" name="startAt" value="${escapeHtml(evaluation.form.startAt)}" required></div>
                        <div class="field"><label>结束时间</label><input type="datetime-local" name="endAt" value="${escapeHtml(evaluation.form.endAt)}" required></div>
                        <div class="field"><label>数量上限</label><input type="number" min="1" max="500" name="limit" value="${escapeHtml(evaluation.form.limit)}"></div>
                        <div class="field"><label>LLM Judge</label><select name="includeLlmJudge"><option value="false" ${!evaluation.form.includeLlmJudge ? "selected" : ""}>关闭</option><option value="true" ${evaluation.form.includeLlmJudge ? "selected" : ""}>开启</option></select></div>
                        <div class="field full"><button class="btn primary" type="submit">${evaluation.loading ? "评估中..." : "生成旧版报告"}</button></div>
                    </form>
                    ${renderLegacyReport()}
                </section>
            `;
        }

        function renderLegacyReport() {
            const report = evaluation.report;
            if (!report) {
                return `<div class="empty">暂无旧版报告。</div>`;
            }
            return `<details class="evaluation-json" open><summary>旧版报告 JSON</summary><pre class="json-box">${escapeHtml(safeJson(report))}</pre></details>`;
        }

        function tabButton(mode, label) {
            return `<button type="button" class="${evaluation.mode === mode ? "active" : ""}" data-eval-action="set-mode" data-mode="${mode}">${escapeHtml(label)}</button>`;
        }

        async function loadDashboard() {
            evaluation.loading = true;
            try {
                evaluation.dashboard = await EvaluationApi.dashboard();
                if (!evaluation.selectedRun && evaluation.dashboard.latestRun?.id) {
                    evaluation.selectedRun = evaluation.dashboard.latestRun.results ? evaluation.dashboard.latestRun : await EvaluationApi.getRun(evaluation.dashboard.latestRun.id);
                }
            } catch (error) {
                showToast(error.message || "Evaluation Dashboard 加载失败", "error");
            } finally {
                evaluation.loading = false;
                render();
            }
        }

        async function reloadDashboard() {
            evaluation.dashboard = null;
            evaluation.selectedRun = null;
            await loadDashboard();
        }

        function handleClick(event) {
            const target = event.target.closest("[data-eval-action]");
            if (!target) {
                return false;
            }
            const action = target.dataset.evalAction;
            if (action === "refresh") {
                reloadDashboard();
            } else if (action === "set-mode") {
                evaluation.mode = target.dataset.mode || "dashboard";
                render();
            } else if (action === "select-case") {
                evaluation.selectedCaseId = target.dataset.caseId;
                render();
            } else if (action === "select-run") {
                selectRun(target.dataset.runId);
            }
            return true;
        }

        function handleChange() {
            return false;
        }

        function handleSubmit(event) {
            const form = event.target;
            if (!["evaluationRunForm", "evaluationCaseCreateForm", "evaluationCaseUpdateForm", "evaluationDatasetForm", "evaluationCaseFilterForm"].includes(form.id)) {
                return false;
            }
            event.preventDefault();
            if (form.id === "evaluationRunForm") runEvaluationDashboard(form);
            if (form.id === "evaluationCaseCreateForm") createCase(form);
            if (form.id === "evaluationCaseUpdateForm") updateCase(form);
            if (form.id === "evaluationDatasetForm") createDataset(form);
            if (form.id === "evaluationCaseFilterForm") filterCases(form);
            return true;
        }

        async function selectRun(runId) {
            try {
                evaluation.selectedRun = await EvaluationApi.getRun(runId);
                evaluation.mode = "dashboard";
                render();
            } catch (error) {
                showToast(error.message || "Run 加载失败", "error");
            }
        }

        async function runEvaluationDashboard(form) {
            const formData = new FormData(form);
            evaluation.loading = true;
            render();
            try {
                evaluation.selectedRun = await EvaluationApi.createRun({
                    versionLabel: formData.get("versionLabel"),
                    datasetId: formData.get("datasetId") || null,
                    mode: formData.get("mode"),
                    repeat: Number(formData.get("repeat") || 1),
                    requestId: crypto.randomUUID()
                });
                evaluation.dashboard = await EvaluationApi.dashboard();
                evaluation.mode = "dashboard";
                showToast("离线评测已完成");
            } catch (error) {
                showToast(error.message || "评测运行失败", "error");
            } finally {
                evaluation.loading = false;
                render();
            }
        }

        async function createCase(form) {
            const formData = new FormData(form);
            let caseData = {};
            const rawCaseData = String(formData.get("caseData") || "").trim();
            if (rawCaseData) {
                try {
                    caseData = JSON.parse(rawCaseData);
                } catch (error) {
                    showToast("Case Data JSON 不合法", "error");
                    return;
                }
            }
            try {
                const created = await EvaluationApi.createCase({
                    title: formData.get("title"),
                    originalQuestion: formData.get("originalQuestion"),
                    expectedBehavior: formData.get("expectedBehavior"),
                    actualBehavior: formData.get("actualBehavior") || null,
                    errorType: formData.get("errorType"),
                    modules: String(formData.get("modules") || "").split(",").map(item => item.trim()).filter(Boolean),
                    caseData
                });
                evaluation.selectedCaseId = created.id;
                evaluation.dashboard = await EvaluationApi.dashboard();
                showToast("Bad Case 已保存");
                render();
            } catch (error) {
                showToast(error.message || "Case 保存失败", "error");
            }
        }

        async function updateCase(form) {
            const formData = new FormData(form);
            try {
                const updated = await EvaluationApi.updateCase(form.dataset.caseId, {
                    revision: Number(formData.get("revision")),
                    status: formData.get("status"),
                    fixVersion: formData.get("fixVersion") || null,
                    diagnosis: formData.get("diagnosis") || null,
                    fixPlan: formData.get("fixPlan") || null
                });
                evaluation.selectedCaseId = updated.id;
                evaluation.dashboard = await EvaluationApi.dashboard();
                showToast("Case 已更新");
                render();
            } catch (error) {
                showToast(error.message || "Case 更新失败", "error");
            }
        }

        async function createDataset(form) {
            const formData = new FormData(form);
            const caseIds = formData.getAll("caseIds");
            if (!caseIds.length) {
                showToast("至少选择一个 Case", "error");
                return;
            }
            try {
                await EvaluationApi.createDataset({
                    name: formData.get("name"),
                    version: formData.get("version"),
                    description: formData.get("description") || null,
                    caseIds
                });
                evaluation.dashboard = await EvaluationApi.dashboard();
                showToast("Regression Dataset 已创建");
                render();
            } catch (error) {
                showToast(error.message || "Dataset 创建失败", "error");
            }
        }

        async function filterCases(form) {
            const formData = new FormData(form);
            evaluation.filters = {
                status: formData.get("status") || "",
                errorType: formData.get("errorType") || "",
                module: formData.get("module") || "",
                q: formData.get("q") || ""
            };
            try {
                const result = await EvaluationApi.listCases(evaluation.filters);
                evaluation.dashboard = {...evaluation.dashboard, cases: result.cases};
                evaluation.selectedCaseId = result.cases[0]?.id || null;
                render();
            } catch (error) {
                showToast(error.message || "Case 筛选失败", "error");
            }
        }

        return {render, handleClick, handleSubmit, handleChange};
    };
})();
