(function () {
    "use strict";
    const app = document.getElementById("app");
    const toast = document.getElementById("toast");
    const userIdInput = document.getElementById("userIdInput");
    const THEME_STORAGE_KEY = "choiceAgentTheme";
    const DEVELOPER_MODE_KEY = "choiceAgentDeveloperMode";
    const THEMES = {
        mint: "清新绿",
        pop: "活力橙"
    };
    const SLOT_LABELS = {
        mealTime: "用餐时间",
        mood: "心情状态",
        scene: "用餐场景",
        healthGoal: "健康目标",
        cuisine: "菜系偏好",
        taste: "口味偏好",
        convenience: "便利程度"
    };
    const INTENTS = [
        "MEAL_RECOMMENDATION",
        "CLARIFY_NEEDED",
        "MEAL_ADJUST",
        "MEAL_PLAN",
        "HEALTH_RISK",
        "OTHER"
    ];
    const state = {
        theme: getSavedTheme(),
        developerMode: getSavedDeveloperMode(),
        settings: { model: DietApi.getModelSettings() },
        home: { loaded: false, personalCount: 0, publicCount: 0, generalPrompt: "", notice: "", searchCapabilities: null, capabilitiesLoading: false, realtimeSearch: true, progress: [] },
        history: { items: [], detail: null, loading: false, error: "" },
        profile: { data: null, loading: false, error: "" },
        slotOptions: null,
        personalMeals: [],
        publicMeals: [],
        editingMeal: null,
        chat: {
            domain: "DIET",
            mode: "diet",
            routeId: null,
            sourceMode: "PERSONAL",
            sessionId: null,
            sending: false,
            pendingPrompt: "",
            autoSending: false,
            messages: defaultChatMessages(),
            decision: null, draft: "", editFields: null, panelOpen: false,
            initialized: false, generation: 0, retry: null, error: ""
        },
        traces: {
            rows: [],
            selected: null,
            loading: false,
            filters: defaultTraceFilters()
        },
        evaluation: {
            report: null,
            loading: false,
            form: defaultRangeForm(),
            dashboard: null,
            selectedRun: null,
            selectedCaseId: null,
            filters: { status: "", errorType: "", module: "", q: "" },
            mode: "dashboard"
        },
        demo: {
            decision: null
        },
        generic: {
            decision: null,
            loading: false
        }
    };
    function isKnownTheme(theme) {
        return Object.prototype.hasOwnProperty.call(THEMES, theme);
    }
    function getSavedTheme() {
        try {
            const theme = window.localStorage.getItem(THEME_STORAGE_KEY);
            return isKnownTheme(theme) ? theme : "mint";
        } catch (error) {
            return "mint";
        }
    }
    function saveTheme(theme) {
        try {
            window.localStorage.setItem(THEME_STORAGE_KEY, theme);
            return true;
        } catch (error) {
            return false;
        }
    }
    function getSavedDeveloperMode() {
        try {
            return window.localStorage.getItem(DEVELOPER_MODE_KEY) === "true";
        } catch (error) {
            return false;
        }
    }
    function saveDeveloperMode(enabled) {
        try {
            window.localStorage.setItem(DEVELOPER_MODE_KEY, enabled ? "true" : "false");
            return true;
        } catch (error) {
            return false;
        }
    }
    function applyDeveloperMode() {
        document.body.dataset.developerMode = state.developerMode ? "on" : "off";
        document.querySelectorAll('[data-action="toggle-developer-mode"]').forEach((input) => {
            input.checked = state.developerMode;
        });
    }
    function applyTheme(theme) {
        const nextTheme = isKnownTheme(theme) ? theme : "mint";
        document.body.dataset.theme = nextTheme;
        document.querySelectorAll('[data-action="set-theme"]').forEach((button) => {
            const active = button.dataset.themeValue === nextTheme;
            button.setAttribute("aria-checked", active ? "true" : "false");
        });
    }
    function closeThemeMenu() {
        const menu = document.querySelector("#themeMenu .theme-menu-list");
        const button = document.getElementById("themeMenuButton");
        if (menu) {
            menu.classList.add("hidden");
        }
        if (button) {
            button.setAttribute("aria-expanded", "false");
        }
    }
    function closeDeveloperMenu() {
        const menu = document.querySelector(".developer-menu-list");
        const button = document.getElementById("developerMenuButton");
        if (menu) {
            menu.classList.add("hidden");
        }
        if (button) {
            button.setAttribute("aria-expanded", "false");
        }
    }
    function toggleThemeMenu() {
        const menu = document.querySelector("#themeMenu .theme-menu-list");
        const button = document.getElementById("themeMenuButton");
        if (!menu || !button) {
            return;
        }
        const willOpen = menu.classList.contains("hidden");
        closeDeveloperMenu();
        menu.classList.toggle("hidden", !willOpen);
        button.setAttribute("aria-expanded", willOpen ? "true" : "false");
    }
    function toggleDeveloperMenu() {
        const menu = document.querySelector(".developer-menu-list");
        const button = document.getElementById("developerMenuButton");
        if (!menu || !button) {
            return;
        }
        const willOpen = menu.classList.contains("hidden");
        closeThemeMenu();
        menu.classList.toggle("hidden", !willOpen);
        button.setAttribute("aria-expanded", willOpen ? "true" : "false");
    }
    function setTheme(theme) {
        if (!isKnownTheme(theme)) {
            showToast("未知皮肤", "error");
            return;
        }
        state.theme = theme;
        const saved = saveTheme(theme);
        applyTheme(theme);
        showToast(saved ? "皮肤已切换" : "皮肤已切换，但无法保存偏好", saved ? undefined : "error");
        closeThemeMenu();
    }
    function setDeveloperMode(enabled) {
        state.developerMode = Boolean(enabled);
        const saved = saveDeveloperMode(state.developerMode);
        applyDeveloperMode();
        showToast(saved ? "Developer Mode 已更新" : "Developer Mode 已更新，但无法保存", saved ? undefined : "error");
        if (currentRoute() === "/developer/debug") {
            renderDeveloperDebug();
        }
    }
    function defaultRangeForm() {
        const end = new Date();
        const start = new Date(end.getTime() - 24 * 60 * 60 * 1000);
        return {
            startAt: toLocalInputValue(start),
            endAt: toLocalInputValue(end),
            limit: 50,
            includeLlmJudge: false
        };
    }
    function defaultTraceFilters() {
        const range = defaultRangeForm();
        return {
            startAt: range.startAt,
            endAt: range.endAt,
            onlyUnlabeled: false,
            limit: 50,
            sessionId: ""
        };
    }
    function toLocalInputValue(date) {
        const pad = (value) => String(value).padStart(2, "0");
        return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
    }
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
    function showToast(message, type) {
        toast.textContent = message;
        toast.className = `toast show ${type === "error" ? "error" : ""}`;
        window.clearTimeout(showToast.timer);
        showToast.timer = window.setTimeout(() => {
            toast.className = "toast";
        }, 3200);
    }
    function setLoading(button, loadingText) {
        if (!button) {
            return () => {};
        }
        const oldText = button.textContent;
        button.disabled = true;
        button.textContent = loadingText || "处理中...";
        return () => {
            button.disabled = false;
            button.textContent = oldText;
        };
    }
    async function guard(action, successMessage) {
        try {
            const result = await action();
            if (successMessage) {
                showToast(successMessage);
            }
            return result;
        } catch (error) {
            showToast(error.message || "操作失败", "error");
            throw error;
        }
    }
    function currentRoute() {
        const route = (location.hash || "#/").slice(1).split("?")[0];
        return route || "/";
    }
    function navigate(route) {
        location.hash = route;
    }
    function setActiveNav(route) {
        let navRoute = route;
        if (route.startsWith("/diet/meals")) {
            navRoute = "/profile";
        } else if (route.startsWith("/history")) {
            navRoute = "/history";
        } else if (route === "/diet/chat" || route.startsWith("/demo") || route.startsWith("/decisions/") || route.startsWith("/admin") || route === "/settings" || route.startsWith("/developer")) {
            navRoute = "/";
        }
        document.querySelectorAll("[data-nav]").forEach((item) => {
            item.classList.toggle("active", item.dataset.nav === navRoute);
        });
    }
    function render() {
        const route = currentRoute();
        setActiveNav(route);
        if (route === "/") {
            renderGeneralHome();
        } else if (route === "/diet") {
            navigate("/diet/chat");
        } else if (route === "/diet/chat") {
            conversation.enter("diet");
        } else if (route === "/demo" || route.startsWith("/demo/decision/")) {
            renderDemoWorkbench(route);
        } else if (route.startsWith("/decisions/")) {
            renderGenericDecision(route);
        } else if (route === "/diet/meals/personal") {
            renderPersonalMeals();
        } else if (route === "/diet/meals/public") {
            renderPublicMeals();
        } else if (route === "/history") {
            renderDecisionHistory();
        } else if (route.startsWith("/history/")) {
            renderDecisionHistoryDetail(route);
        } else if (route === "/profile") {
            renderProfile();
        } else if (route === "/admin/traces") {
            renderTraces();
        } else if (route === "/admin/evaluations") {
            renderEvaluations();
        } else if (route === "/settings") {
            renderSettings();
        } else if (route === "/developer/debug") {
            renderDeveloperDebug();
        } else {
            navigate("/");
        }
        applyDeveloperMode();
        app.focus({ preventScroll: true });
    }
    function renderHomeProgress() {
        const events = state.home.progress || [];
        if (!events.length) {
            return "";
        }
        return `<div class="search-progress" role="status" aria-live="polite">${events.map((event, index) => `<div class="search-progress-row ${index === events.length - 1 ? "active" : ""}"><span></span><p>${escapeHtml(event.message || "正在处理")}</p></div>`).join("")}</div>`;
    }
    function loadSearchCapabilities() {
        if (state.home.searchCapabilities || state.home.capabilitiesLoading) {
            return;
        }
        state.home.capabilitiesLoading = true;
        DecisionApi.searchCapabilities().then((capabilities) => {
            state.home.searchCapabilities = capabilities;
            if (!capabilities.webSearchConfigured) {
                state.home.realtimeSearch = false;
            }
            if (currentRoute() === "/") renderGeneralHome();
        }).catch(() => {
            state.home.searchCapabilities = {supportedDomains:["shopping","travel"], webSearchConfigured:false, defaultSearchMode:"fixture"};
            state.home.realtimeSearch = false;
            if (currentRoute() === "/") renderGeneralHome();
        }).finally(() => {
            state.home.capabilitiesLoading = false;
        });
    }

    function renderGeneralHome() {
        loadSearchCapabilities();
        const searchCapabilities = state.home.searchCapabilities;
        const searchConfigured = Boolean(searchCapabilities?.webSearchConfigured);
        const realtimeChecked = searchConfigured && state.home.realtimeSearch !== false;
        const searchHint = searchCapabilities ? (searchConfigured ? "购物和旅行场景会使用实时搜索；其他场景继续使用已有候选。" : "当前服务端未配置实时搜索，仍可使用演示候选体验流程。") : "正在检查实时搜索配置。";
        const flagshipExample = {
            text: "A 公司工作稳定、离家近，B 公司成长更快但每天通勤两小时，我应该怎么选？",
            domain: "career"
        };
        const examples = [
            { label: "规划一次不累的周末旅行", text: "周末想出去走走，但不想太累，应该去哪里？", domain: "travel" },
            { label: "挑一台通勤电脑", text: "想换一台适合通勤的轻便电脑，预算有限，应该怎么选？", domain: "shopping" },
            { label: "选择 AI Agent 学习路径", text: "想系统学 AI Agent，但不知道先选哪条学习路径。", domain: "learning" },
            { label: "决定今晚吃什么", text: "今晚不知道吃什么，想要清淡一点。", domain: "diet" }
        ];
        app.innerHTML = `
            <section class="hero general-home">
                <div class="hero-panel decision-entry">
                    <span class="badge">Choice Agent</span>
                    <h1>把选择题想清楚</h1>
                    <p>说出你正在纠结的选择。Choice Agent 会帮你补齐关键条件、整理候选、过滤硬约束、比较取舍，并告诉你为什么推荐、需要接受什么代价，以及什么变化会改变当前结论。</p>
                    <form id="generalDecisionForm" class="decision-entry-form">
                        <label class="field full">
                            <span>你最近在纠结什么？</span>
                            <textarea name="prompt" placeholder="比如：我拿到了两个 Offer，一个稳定但成长慢，一个机会更多但通勤很远，我该怎么选？">${escapeHtml(state.home.generalPrompt)}</textarea>
                        </label>
                        <label class="toggle-row realtime-search-toggle">
                            <input type="checkbox" name="realTimeSearch" data-action="real-search-toggle" ${realtimeChecked ? "checked" : ""} ${searchConfigured ? "" : "disabled"}>
                            <span>使用实时信息寻找候选</span>
                            <small>${escapeHtml(searchHint)}</small>
                        </label>
                        ${renderHomeProgress()}
                        <div class="button-row">
                            <button class="btn primary" type="submit">开始决策</button>
                        </div>
                    </form>
                    ${state.home.notice ? `<div class="mode-notice">${escapeHtml(state.home.notice)}</div>` : ""}
                    <button class="flagship-example" type="button" data-action="general-example" data-example="${escapeHtml(flagshipExample.text)}" data-demo-domain="${escapeHtml(flagshipExample.domain)}">
                        <span>推荐体验</span>
                        <strong>帮我比较两个 Offer</strong>
                        <small>${escapeHtml(flagshipExample.text)}</small>
                    </button>
                    <div class="example-grid" aria-label="决策示例">
                        ${examples.map((example) => `<button class="example-button" type="button" data-action="general-example" data-example="${escapeHtml(example.text)}" data-demo-domain="${escapeHtml(example.domain)}">${escapeHtml(example.label)}</button>`).join("")}
                    </div>
                </div>
                <aside class="grid stats workflow-stats">
                    ${statCard("不用先整理", "一句话开始", "先描述你在纠结什么，目标、候选和顾虑可以边聊边补齐。")}
                    ${statCard("看清决策条件", "自动拆解", "识别目标、候选、偏好和硬约束，让模糊问题变成可检查的结构。")}
                    ${statCard("先补关键缺口", "追问重点", "信息不足时优先问真正影响结论的问题，而不是马上给答案。")}
                    ${statCard("理解推荐边界", "可解释结论", "说明为什么推荐、要接受什么代价，以及哪些条件变化会改变结果。")}
                </aside>
            </section>
            ${renderHomeDecisionProcess()}
        `;
    }
    function formatDateTime(value) {
        if (!value) {
            return "-";
        }
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) {
            return String(value);
        }
        return `${date.getFullYear()}/${String(date.getMonth() + 1).padStart(2, "0")}/${String(date.getDate()).padStart(2, "0")} ${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
    }
    function historyRouteId(route) {
        return decodeURIComponent(route.replace("/history/", "").split("/")[0] || "");
    }
    async function renderDecisionHistory() {
        if (!state.history.loading) {
            state.history.loading = true;
            state.history.error = "";
            app.innerHTML = `<section class="section"><div class="empty">历史决策加载中...</div></section>`;
            try {
                const response = await DecisionHistoryApi.list({limit: 50});
                state.history.items = response.items || [];
            } catch (error) {
                state.history.error = error.message || "历史决策加载失败";
            } finally {
                state.history.loading = false;
            }
            if (currentRoute() !== "/history") {
                return;
            }
        }
        const items = state.history.items || [];
        app.innerHTML = `
            <section class="section">
                <div class="card-title">
                    <div>
                        <h2>历史决策</h2>
                        <p>查看过去做过的选择、当时条件、推荐结论和最后实际选择。</p>
                    </div>
                    <a class="btn primary" href="#/">开始新决策</a>
                </div>
                ${state.history.error ? `<div class="diet-error">${escapeHtml(state.history.error)}</div>` : ""}
                ${items.length ? `<div class="history-list">${items.map(renderHistoryCard).join("")}</div>` : `<div class="empty">暂无历史决策。完成一次选择后，这里会自动出现记录。</div>`}
            </section>
        `;
    }
    function outcomeReviewLabel(status) {
        return {
            no_outcome: "尚未记录选择",
            not_due: "可随时复盘",
            due: "待复盘实际结果",
            reviewed: "已复盘"
        }[status] || "可随时复盘";
    }
    function renderHistoryCard(item) {
        const consistency = historyConsistency(item.currentRecommendation, item.finalChoice);
        return `
            <a class="history-card" href="#/history/${encodeURIComponent(item.decisionId)}">
                <div>
                    <strong>${escapeHtml(item.title)}</strong>
                    <p>${escapeHtml(formatDateTime(item.updatedAt || item.createdAt))} · ${escapeHtml(item.domain || "generic")}</p>
                </div>
                <div class="history-card-meta">
                    <span>当前推荐：${escapeHtml(item.currentRecommendation || "未形成推荐")}</span>
                    <span>最终选择：${escapeHtml(item.finalChoice || "未记录")}</span>
                    <span>结果复盘：${escapeHtml(outcomeReviewLabel(item.outcomeReviewStatus))}</span>
                    <span class="history-match ${consistency.className}">${escapeHtml(consistency.label)}</span>
                </div>
            </a>
        `;
    }
    function historyConsistency(recommendation, finalChoice) {
        if (!recommendation || !finalChoice) {
            return {className: "unknown", label: "尚未判断一致性"};
        }
        const clean = value => String(value || "").trim().toLowerCase();
        return clean(recommendation) === clean(finalChoice)
            ? {className: "match", label: "与推荐一致"}
            : {className: "mismatch", label: "与推荐不同"};
    }
    function decisionConsistency(decision, summary = {}) {
        const recommendedId = decision.recommendation?.primaryCandidateId;
        const outcome = decision.outcome || {};
        if (recommendedId && outcome.candidateId) {
            return outcome.candidateId === recommendedId
                ? {className: "match", label: "最终选择与系统推荐一致"}
                : {className: "mismatch", label: "最终选择与系统推荐不同"};
        }
        return historyConsistency(summary.currentRecommendation, summary.finalChoice);
    }
    async function renderDecisionHistoryDetail(route) {
        const id = historyRouteId(route);
        if (!id) {
            navigate("/history");
            return;
        }
        if (!state.history.detail || state.history.detail.summary?.decisionId !== id) {
            state.history.detail = null;
            state.history.error = "";
            app.innerHTML = `<section class="section"><div class="empty">历史详情加载中...</div></section>`;
            try {
                state.history.detail = await DecisionHistoryApi.get(id);
            } catch (error) {
                state.history.error = error.message || "历史详情加载失败";
            }
            if (currentRoute() !== route) {
                return;
            }
        }
        if (state.history.error || !state.history.detail) {
            app.innerHTML = `<section class="section"><div class="card-title"><div><h2>历史决策</h2></div><a class="btn ghost" href="#/history">返回历史</a></div><div class="diet-error">${escapeHtml(state.history.error || "历史详情不存在")}</div></section>`;
            return;
        }
        const detail = state.history.detail;
        const decision = detail.decision || {};
        const summary = detail.summary || {};
        const consistency = decisionConsistency(decision, summary);
        app.innerHTML = `
            <section class="history-detail">
                <div class="section">
                    <div class="card-title">
                        <div>
                            <h2>${escapeHtml(summary.title || decision.userGoal || "未命名决策")}</h2>
                            <p>${escapeHtml(formatDateTime(summary.updatedAt || summary.createdAt))} · ${escapeHtml(summary.domain || decision.domain || "generic")}</p>
                        </div>
                        <div class="inline-actions">
                            <a class="btn ghost" href="#/history">返回历史</a>
                            <a class="btn primary" href="#/decisions/${encodeURIComponent(decision.decisionId || id)}">继续决策</a>
                        </div>
                    </div>
                    <div class="grid three">
                        ${statCard("当前推荐", summary.currentRecommendation || "未形成推荐", "系统基于当前条件形成的倾向")}
                        ${statCard("最终选择", summary.finalChoice || "未记录", "你最后实际做出的选择")}
                        ${statCard("推荐一致性", consistency.label, "最终选择是否跟当时建议一致")}
                    </div>
                </div>
                <div class="grid two history-detail-grid">
                    <section class="section">
                        <h3>当时条件</h3>
                        ${renderHistoryFacts(decision)}
                    </section>
                    <section class="section">
                        <h3>最终选择</h3>
                        ${renderOutcomeForm(decision)}
                        ${renderOutcomeReview(decision, summary)}
                    </section>
                </div>
                <section class="section">
                    <div class="card-title"><div><h3>候选和推荐理由</h3><p>保留当时系统整理出的候选、推荐和关键取舍。</p></div></div>
                    <div class="demo-candidates">${(decision.candidates || []).map((candidate) => renderHistoryCandidate(candidate, decision)).join("") || `<div class="empty">暂无候选</div>`}</div>
                </section>
            </section>
        `;
    }
    function renderHistoryFacts(decision) {
        const constraints = decision.constraints || [];
        const criteria = decision.criteria || [];
        const questions = decision.unansweredQuestions || [];
        const reasons = decision.recommendation?.reasons || [];
        return `
            <div class="demo-list">
                <div><strong>目标</strong><span>${escapeHtml(decision.userGoal || "未记录")}</span></div>
                ${constraints.map((item) => `<div><strong>${escapeHtml(item.label || item.key)}</strong><span>${escapeHtml(item.value != null ? `${item.operator} ${item.value}` : (item.values || []).join("、"))}</span></div>`).join("")}
                ${criteria.map((item) => `<div><strong>${escapeHtml(item.label)}</strong><span>权重 ${escapeHtml(item.weight)}</span></div>`).join("")}
                ${reasons.map((item) => `<div><strong>关键理由</strong><span>${escapeHtml(item.text)}</span></div>`).join("")}
                ${questions.map((item) => `<div><strong>未确定信息</strong><span>${escapeHtml(item.question || item)}</span></div>`).join("")}
            </div>
        `;
    }
    function renderOutcomeForm(decision) {
        const candidates = decision.candidates || [];
        const outcome = decision.outcome || {};
        return `
            <form id="decisionOutcomeForm" class="settings-form">
                <label class="field full">
                    <span>从候选中选择</span>
                    <select name="candidateId">
                        <option value="">自由输入 / 未匹配候选</option>
                        ${candidates.map((candidate) => `<option value="${escapeHtml(candidate.candidateId)}" ${outcome.candidateId === candidate.candidateId ? "selected" : ""}>${escapeHtml(candidate.name)}</option>`).join("")}
                    </select>
                </label>
                <label class="field full">
                    <span>最终选择</span>
                    <input name="label" required value="${escapeHtml(outcome.label || "")}" placeholder="例如：A 公司、莫干山、ThinkPad">
                </label>
                <label class="field full">
                    <span>原因</span>
                    <textarea name="reason" placeholder="可选：为什么最后这么选？">${escapeHtml(outcome.reason || "")}</textarea>
                </label>
                <input type="hidden" name="decisionId" value="${escapeHtml(decision.decisionId)}">
                <input type="hidden" name="revision" value="${escapeHtml(decision.revision)}">
                <div class="button-row">
                    <button class="btn primary" type="submit">保存最终选择</button>
                    ${decision.outcome ? `<button class="btn ghost" type="button" data-action="clear-outcome" data-decision-id="${escapeHtml(decision.decisionId)}" data-revision="${escapeHtml(decision.revision)}">清除记录</button>` : ""}
                </div>
            </form>
        `;
    }
    function renderOutcomeReview(decision, summary = {}) {
        if (!decision.outcome) {
            return `<p class="muted">记录最终选择后，可以回来复盘实际结果。</p>`;
        }
        const review = decision.outcome.review || {};
        return `
            <section class="outcome-review">
                <div class="card-title">
                    <div><h4>实际结果复盘</h4><p>${escapeHtml(outcomeReviewLabel(summary.outcomeReviewStatus))} · 可以随时更新。</p></div>
                </div>
                <form id="decisionOutcomeReviewForm" class="settings-form">
                    <label class="field full"><span>结果状态</span>
                        <select name="status" required>
                            <option value="">请选择</option>
                            ${Object.entries({successful:"结果不错",mixed:"有得有失",unsuccessful:"结果不理想",changed:"后来改选"}).map(([value, label]) => `<option value="${value}" ${review.status === value ? "selected" : ""}>${label}</option>`).join("")}
                        </select>
                    </label>
                    <label class="field full"><span>满意度（1–5）</span><input name="satisfaction" type="number" min="1" max="5" value="${escapeHtml(review.satisfaction ?? "")}" placeholder="可选"></label>
                    <label class="field full"><span>如果重来还会这样选吗？</span>
                        <select name="wouldChooseAgain">
                            <option value="">暂不确定</option>
                            <option value="true" ${review.wouldChooseAgain === true ? "selected" : ""}>会</option>
                            <option value="false" ${review.wouldChooseAgain === false ? "selected" : ""}>不会</option>
                        </select>
                    </label>
                    <label class="field full"><span>实际结果</span><textarea name="note" placeholder="可选：后来发生了什么？">${escapeHtml(review.note || "")}</textarea></label>
                    <input type="hidden" name="decisionId" value="${escapeHtml(decision.decisionId)}">
                    <input type="hidden" name="revision" value="${escapeHtml(decision.revision)}">
                    <div class="button-row">
                        <button class="btn primary" type="submit">保存复盘</button>
                        ${decision.outcome.review ? `<button class="btn ghost" type="button" data-action="clear-outcome-review" data-decision-id="${escapeHtml(decision.decisionId)}" data-revision="${escapeHtml(decision.revision)}">清除复盘</button>` : ""}
                    </div>
                </form>
            </section>
        `;
    }
    function renderHistoryCandidate(candidate, decision) {
        const recommendation = decision.recommendation || {};
        const primary = recommendation.primaryCandidateId === candidate.candidateId;
        const reasons = (recommendation.reasons || []).filter((item) => !item.candidateId || item.candidateId === candidate.candidateId);
        return `
            <article class="demo-candidate${primary ? " history-primary" : ""}">
                <div class="demo-candidate-head">
                    <div>
                        <h3>${escapeHtml(candidate.name)}${primary ? " · 当前推荐" : ""}</h3>
                        <p>${escapeHtml(candidate.summary || "")}</p>
                    </div>
                    <span class="score">${Number.isFinite(Number(candidate.score)) ? "匹配分 " + Math.round(Number(candidate.score) * 100) + "%" : "待比较"}</span>
                </div>
                <div class="attribute-grid">${Object.entries(candidate.attributes || {}).map(([key, value]) => `<span><strong>${escapeHtml(key)}</strong>${escapeHtml(Array.isArray(value) ? value.join("、") : value)}</span>`).join("")}</div>
                ${reasons.length ? `<div class="demo-list">${reasons.map((item) => `<div><strong>理由</strong><span>${escapeHtml(item.text)}</span></div>`).join("")}</div>` : ""}
            </article>
        `;
    }
    async function saveDecisionOutcome(form) {
        const formData = new FormData(form);
        const decisionId = formData.get("decisionId");
        const payload = {
            candidateId: formData.get("candidateId") || null,
            label: String(formData.get("label") || "").trim(),
            reason: String(formData.get("reason") || "").trim() || null,
            revision: Number(formData.get("revision"))
        };
        if (!payload.label) {
            showToast("请填写最终选择", "error");
            return;
        }
        await guard(async () => {
            state.history.detail = await DecisionHistoryApi.saveOutcome(decisionId, payload);
            state.history.items = [];
            renderDecisionHistoryDetail(`/history/${encodeURIComponent(decisionId)}`);
        }, "最终选择已保存");
    }
    async function clearDecisionOutcome(button) {
        const decisionId = button.dataset.decisionId;
        const revision = Number(button.dataset.revision);
        await guard(async () => {
            state.history.detail = await DecisionHistoryApi.clearOutcome(decisionId, revision);
            state.history.items = [];
            renderDecisionHistoryDetail(`/history/${encodeURIComponent(decisionId)}`);
        }, "最终选择已清除");
    }
    async function saveDecisionOutcomeReview(form) {
        const formData = new FormData(form);
        const decisionId = formData.get("decisionId");
        const chooseAgain = formData.get("wouldChooseAgain");
        const satisfaction = String(formData.get("satisfaction") || "").trim();
        const payload = {
            status: formData.get("status"),
            satisfaction: satisfaction ? Number(satisfaction) : null,
            wouldChooseAgain: chooseAgain === "" ? null : chooseAgain === "true",
            note: String(formData.get("note") || "").trim() || null,
            revision: Number(formData.get("revision"))
        };
        await guard(async () => {
            state.history.detail = await DecisionHistoryApi.saveOutcomeReview(decisionId, payload);
            state.history.items = [];
            renderDecisionHistoryDetail(`/history/${encodeURIComponent(decisionId)}`);
        }, "实际结果复盘已保存");
    }
    async function clearDecisionOutcomeReview(button) {
        const decisionId = button.dataset.decisionId;
        const revision = Number(button.dataset.revision);
        await guard(async () => {
            state.history.detail = await DecisionHistoryApi.clearOutcomeReview(decisionId, revision);
            state.history.items = [];
            renderDecisionHistoryDetail(`/history/${encodeURIComponent(decisionId)}`);
        }, "实际结果复盘已清除");
    }
    async function renderProfile() {
        if (!state.profile.data && !state.profile.loading) {
            state.profile.loading = true;
            state.profile.error = "";
            app.innerHTML = `<section class="section"><div class="empty">我的资料加载中...</div></section>`;
            try {
                state.profile.data = await ProfileApi.get();
            } catch (error) {
                state.profile.error = error.message || "我的资料加载失败";
                state.profile.data = {};
            } finally {
                state.profile.loading = false;
            }
            if (currentRoute() !== "/profile") {
                return;
            }
        }
        const profile = state.profile.data || {};
        app.innerHTML = `
            <section class="settings-layout">
                <div class="section settings-panel">
                    <div class="card-title">
                        <div>
                            <h2>我的资料</h2>
                            <p>保存长期偏好，后续决策可以复用这些信息。</p>
                        </div>
                    </div>
                    ${state.profile.error ? `<div class="diet-error">${escapeHtml(state.profile.error)}</div>` : ""}
                    <form id="profileForm" class="settings-form">
                        <label class="field full">
                            <span>预算习惯</span>
                            <textarea name="budgetHabit" placeholder="例如：电子产品更重视长期使用价值，旅行预算偏保守。">${escapeHtml(profile.budgetHabit || "")}</textarea>
                        </label>
                        <label class="field full">
                            <span>城市偏好</span>
                            <input name="preferredCities" value="${escapeHtml((profile.preferredCities || []).join("、"))}" placeholder="上海、杭州、苏州">
                        </label>
                        <label class="field full">
                            <span>饮食偏好</span>
                            <input name="dietPreferences" value="${escapeHtml((profile.dietPreferences || []).join("、"))}" placeholder="清淡、少油、不吃辣">
                        </label>
                        <label class="field full">
                            <span>其他长期偏好</span>
                            <textarea name="notes" placeholder="例如：更看重稳定性，不喜欢复杂准备。">${escapeHtml(profile.notes || "")}</textarea>
                        </label>
                        <div class="button-row">
                            <button class="btn primary" type="submit">保存资料</button>
                        </div>
                    </form>
                </div>
                <aside class="grid settings-side">
                    ${statCard("用户 ID", DietApi.getUserId(), "当前本地资料归属")}
                    ${statCard("个人餐食库", "已保留", "饮食场景仍可维护常吃餐食")}
                    <a class="btn soft" href="#/diet/meals/personal">管理个人餐食库</a>
                </aside>
            </section>
        `;
    }
    function splitProfileList(value) {
        return String(value || "").split(/[、,，\n]/).map((item) => item.trim()).filter(Boolean);
    }
    async function saveProfile(form) {
        const formData = new FormData(form);
        const payload = {
            budgetHabit: String(formData.get("budgetHabit") || "").trim() || null,
            preferredCities: splitProfileList(formData.get("preferredCities")),
            dietPreferences: splitProfileList(formData.get("dietPreferences")),
            notes: String(formData.get("notes") || "").trim() || null
        };
        await guard(async () => {
            state.profile.data = await ProfileApi.save(payload);
            renderProfile();
        }, "资料已保存");
    }
    function renderDeveloperDebug() {
        const model = DietApi.getModelSettings();
        const decision = state.chat.decision || state.history.detail?.decision || state.generic.decision;
        app.innerHTML = `
            <section class="settings-layout">
                <div class="section settings-panel">
                    <div class="card-title">
                        <div>
                            <h2>Debug 信息</h2>
                            <p>开发者模式下查看当前本地运行状态。</p>
                        </div>
                    </div>
                    <div class="demo-list">
                        <div><strong>用户 ID</strong><span>${escapeHtml(DietApi.getUserId())}</span></div>
                        <div><strong>当前路由</strong><span>${escapeHtml(currentRoute())}</span></div>
                        <div><strong>Developer Mode</strong><span>${state.developerMode ? "开启" : "关闭"}</span></div>
                        <div><strong>真实 API</strong><span>${model.enabled && model.apiKey ? "模型已启用" : "演示模式"}</span></div>
                        <div><strong>主模型</strong><span>${escapeHtml(model.mainModel || "-")}</span></div>
                        <div><strong>实时搜索</strong><span>${model.searchEnabled && model.searchApiKey ? "已启用" : "未启用"}</span></div>
                        <div><strong>当前决策</strong><span>${escapeHtml(decision?.decisionId || "-")}</span></div>
                        <div><strong>Session</strong><span>${escapeHtml(decision?.sessionId || state.chat.sessionId || "-")}</span></div>
                        <div><strong>Revision</strong><span>${escapeHtml(decision?.revision ?? "-")}</span></div>
                    </div>
                </div>
                <aside class="grid settings-side">
                    ${statCard("Trace", "保留", "查看 Agent 运行链路")}
                    ${statCard("Evaluation", "保留", "生成评估报告")}
                    <a class="btn soft" href="#/admin/traces">Trace</a>
                    <a class="btn soft" href="#/admin/evaluations">Evaluation</a>
                    <a class="btn ghost" href="#/settings">真实 API 设置</a>
                </aside>
            </section>
        `;
    }
    function renderSettings() {
        const settings = DietApi.getModelSettings();
        state.settings.model = settings;
        const modelConfigured = settings.enabled && Boolean(settings.apiKey);
        const searchConfigured = settings.searchEnabled && Boolean(settings.searchApiKey);
        const configured = modelConfigured || searchConfigured;
        app.innerHTML = `
            <section class="settings-layout">
                <div class="section settings-panel">
                    <div class="card-title">
                        <div>
                            <h2>设置</h2>
                            <p>浏览器真实 API 配置</p>
                        </div>
                        <span class="settings-status" data-mode="${configured ? "model" : "demo"}">${configured ? "真实 API" : "演示模式"}</span>
                    </div>
                    <form id="modelSettingsForm" class="settings-form">
                        <label class="toggle-row">
                            <input type="checkbox" name="enabled" ${settings.enabled ? "checked" : ""}>
                            <span>使用真实 API 生成理解和解释</span>
                        </label>
                        <label class="field full secret-field">
                            <span>模型 API Key</span>
                            <input type="password" name="apiKey" value="${escapeHtml(settings.apiKey)}" autocomplete="off" placeholder="sk-...">
                        </label>
                        <label class="field full">
                            <span>模型 Base URL</span>
                            <input type="url" name="baseUrl" value="${escapeHtml(settings.baseUrl)}" placeholder="https://api.openai.com/v1">
                        </label>
                        <div class="form-grid two">
                            <label class="field">
                                <span>主模型</span>
                                <input type="text" name="mainModel" value="${escapeHtml(settings.mainModel)}" placeholder="gpt-5">
                            </label>
                            <label class="field">
                                <span>轻量模型</span>
                                <input type="text" name="lightModel" value="${escapeHtml(settings.lightModel)}" placeholder="gpt-5-mini">
                            </label>
                        </div>
                        <label class="toggle-row">
                            <input type="checkbox" name="searchEnabled" ${settings.searchEnabled ? "checked" : ""}>
                            <span>启用真实实时搜索</span>
                        </label>
                        <label class="field full secret-field">
                            <span>搜索 API Key</span>
                            <input type="password" name="searchApiKey" value="${escapeHtml(settings.searchApiKey)}" autocomplete="off" placeholder="sk-...">
                        </label>
                        <div class="form-grid two">
                            <label class="field">
                                <span>搜索 Base URL</span>
                                <input type="url" name="searchBaseUrl" value="${escapeHtml(settings.searchBaseUrl)}" placeholder="https://api.openai.com/v1">
                            </label>
                            <label class="field">
                                <span>搜索模型</span>
                                <input type="text" name="searchModel" value="${escapeHtml(settings.searchModel)}" placeholder="gpt-5-mini">
                            </label>
                        </div>
                        <p class="field-hint">API Key 只保存在当前浏览器的 localStorage 中，请不要在共享设备上保存个人密钥。启用后配置会通过请求头发送给本地后端，不会写入请求 body 或服务端配置。</p>
                        <div class="button-row">
                            <button class="btn primary" type="submit">保存设置</button>
                            <button class="btn ghost" type="button" data-action="clear-model-settings">清除设置</button>
                        </div>
                    </form>
                </div>
                <aside class="grid settings-side">
                    ${statCard("模型", modelConfigured ? "真实 API" : "演示模式", modelConfigured ? "请求会使用浏览器配置的模型。" : "本地规则与离线数据")}
                    ${statCard("实时搜索", searchConfigured ? "已启用" : "未启用", searchConfigured ? "旅行和购物可使用 Web Search。" : "继续使用演示候选")}
                    ${statCard("服务端配置", ".env 保留", "后端环境变量仍可作为部署配置。")}
                </aside>
            </section>
        `;
    }
    function renderDietModeHome() {
        app.innerHTML = `
            <section class="hero">
                <div class="hero-panel">
                    <span class="badge">饮食决策</span>
                    <h1>决定今天吃什么</h1>
                    <p>这是 Choice Agent 当前已增强的决策场景。你可以维护个人餐食库，也可以从公共餐食库开始；助手会根据时间、心情、场景、健康目标、口味和便利程度给出推荐，并在信息不足时主动追问。</p>
                    <div class="hero-actions">
                        <a class="btn primary" href="#/diet/chat">开始决策</a>
                        <a class="btn soft" href="#/diet/meals/personal">管理个人餐食</a>
                        <a class="btn ghost" href="#/diet/meals/public">查看公共餐食</a>
                    </div>
                </div>
                <aside class="grid stats">
                    ${statCard("个人餐食", state.home.loaded ? state.home.personalCount : "加载中", "你的私有餐食库，用于个性化推荐")}
                    ${statCard("公共餐食", state.home.loaded ? state.home.publicCount : "加载中", "系统预置餐食，适合快速体验")}
                    ${statCard("调试与评估", "Trace", "可查看每轮推荐的 Agent 运行链路")}
                </aside>
            </section>
            <section class="grid three" style="margin-top: 18px;">
                ${featureCard("决策助手", "按自然语言表达需求，页面会展示澄清问题、推荐卡片和反馈入口。", "#/diet/chat")}
                ${featureCard("餐食维护", "用标签多选维护自己的常吃餐食，后续决策会优先参考。", "#/diet/meals/personal")}
                ${featureCard("评测后台", "查看请求 Trace，标注预期结果，并生成批量评估报告。", "#/admin/evaluations")}
            </section>
        `;
        loadHomeStats();
    }
    function statCard(label, value, desc) {
        return `
            <div class="stat-card">
                <span class="muted">${escapeHtml(label)}</span>
                <strong>${escapeHtml(value)}</strong>
                <p class="muted">${escapeHtml(desc)}</p>
            </div>
        `;
    }
    function featureCard(title, desc, href) {
        return `
            <article class="card">
                <div class="card-title">
                    <div>
                        <h3>${escapeHtml(title)}</h3>
                        <p>${escapeHtml(desc)}</p>
                    </div>
                </div>
                <a class="btn soft" href="${href}">进入</a>
            </article>
        `;
    }
    async function loadHomeStats() {
        if (state.home.loaded) {
            return;
        }
        try {
            const [personal, publicMeals] = await Promise.all([
                DietApi.listPersonalMeals(),
                DietApi.listPublicMeals()
            ]);
            state.home = {
                loaded: true,
                personalCount: personal.length,
                publicCount: publicMeals.length
            };
        } catch (error) {
            showToast(error.message || "首页数据加载失败", "error");
        }
    }
    function demoRouteId(route) {
        const prefix = "/demo/decision/";
        return route.startsWith(prefix) ? decodeURIComponent(route.slice(prefix.length)) : null;
    }
    function genericRouteId(route) {
        return decodeURIComponent(route.replace("/decisions/", "").split("/")[0] || "");
    }

    function renderHomeDecisionProcess() {
        const steps = [
            ["说出纠结点", "不用先整理成表格，一句话说明目标、候选或顾虑。"],
            ["拆出条件", "识别目标、候选、偏好和硬约束，把模糊问题变成可检查结构。"],
            ["补关键缺口", "只追问会改变结论的问题，其余先作为假设或默认值。"],
            ["召回候选", "按场景整理可选项，并标注来源、证据和实时信息状态。"],
            ["比较取舍", "过滤不合适的候选，解释分数、代价和冲突点。"],
            ["给出建议", "输出当前更推荐什么，以及哪些变化会改变这个结论。"]
        ];
        return `
            <section class="decision-flow value-flow home-process" aria-label="Choice Agent 决策流程">
                <div class="card-title">
                    <div>
                        <span class="eyebrow">Decision Flow</span>
                        <h2>从一句纠结，到一个能解释的选择</h2>
                    </div>
                    <a class="btn soft" href="#/demo">查看完整示例</a>
                </div>
                <div class="home-process-rail">
                    ${steps.map(([title, desc], index) => `
                        <article class="home-process-step">
                            <span>${index + 1}</span>
                            <h3>${escapeHtml(title)}</h3>
                            <p>${escapeHtml(desc)}</p>
                        </article>
                    `).join("")}
                </div>
            </section>
        `;
    }

    function toArray(value) {
        if (Array.isArray(value)) return value.filter(Boolean);
        if (value === null || value === undefined || value === "") return [];
        return [value];
    }
    function displayText(value) {
        if (value === null || value === undefined || value === "") return "";
        if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
        return value.text || value.label || value.name || value.summary || value.question || value.reason || safeJson(value);
    }
    function renderSignalList(items, emptyText) {
        const normalized = toArray(items).map(displayText).filter(Boolean).slice(0, 4);
        if (!normalized.length) return `<p class="muted">${escapeHtml(emptyText)}</p>`;
        return `<ul>${normalized.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
    }
    function evidenceCount(decision, candidates) {
        const ids = new Set();
        for (const item of decision.evidence || []) {
            if (item?.evidenceId) ids.add(item.evidenceId);
        }
        for (const candidate of candidates || []) {
            for (const item of candidate.evidence || []) {
                if (item?.evidenceId) ids.add(item.evidenceId);
            }
        }
        return ids.size;
    }
    function sourceModeText(source) {
        if (source?.realTime || source?.mode === "web") return "实时搜索";
        if (source?.mode === "manual") return "用户输入";
        if (source?.mode === "database") return "数据库";
        return "离线模拟数据";
    }
    function topCriteria(decision) {
        return [...(decision.criteria || [])]
            .sort((a, b) => Number(b.weight || 0) - Number(a.weight || 0))
            .slice(0, 4)
            .map((item) => `${item.label || item.key} · 权重 ${Number(item.weight || 0).toFixed(1)}`);
    }
    function buildDecisionProcess(decision, activeCandidates, candidates, source) {
        const assistance = decision.domainState?.assistance || {};
        const analysis = assistance.currentAnalysis || assistance.analysis || {};
        const questions = toArray(decision.clarifyingQuestions)
            .concat(toArray(assistance.missingInfo), toArray(analysis.missingInfo))
            .map(displayText)
            .filter(Boolean);
        const constraints = (decision.constraints || []).map((item) => {
            const value = item.value != null ? `${item.operator || ""} ${item.value}` : toArray(item.values).join("、");
            return `${item.label || item.key}${value ? `：${value}` : ""}`;
        });
        const assumptions = toArray(assistance.assumptions || analysis.assumptions).map(displayText).filter(Boolean);
        const rankingCounts = decision.domainState?.rankingCounts || {};
        const countValue = (value, fallback = 0) => Number.isFinite(Number(value)) ? Math.max(0, Number(value)) : fallback;
        const poolCount = Array.isArray(decision.domainState?.candidatePool) ? decision.domainState.candidatePool.length : candidates.length;
        const entered = countValue(rankingCounts.remaining, activeCandidates.length);
        const totalEvidence = evidenceCount(decision, candidates);
        const tradeoffs = toArray(decision.recommendation?.tradeoffs || analysis.tradeoffs).map(displayText).filter(Boolean);
        return [
            { key: "understanding", title: "需求理解", status: decision.userGoal ? "active" : "muted", summary: decision.userGoal || "等待你描述正在纠结的选择。", meta: [decision.intentKey || decision.status || "意图待确认", decision.domain || "generic"] },
            { key: "gaps", title: "信息分层", status: questions.length ? "active" : "done", summary: questions.length ? "先补会影响方向的问题。" : "已有信息足够推进首版判断。", groups: [["需要你确认", questions.slice(0, 3), "暂时没有必须追问的问题。"], ["我先做的假设", assumptions.slice(0, 3), "本轮没有记录可展示假设。"], ["已知硬约束", constraints.slice(0, 3), "暂无明确硬约束。"]] },
            { key: "retrieval", title: "候选召回", status: candidates.length ? "done" : "muted", summary: `找到 ${Math.max(poolCount, candidates.length)} 个候选，${entered} 个进入比较。`, meta: [sourceModeText(source), totalEvidence ? `${totalEvidence} 条 Evidence` : "暂无证据记录"] },
            { key: "filtering", title: "过滤与比较", status: candidates.length ? "done" : "muted", summary: "按硬约束、用户排除和缺失数据整理候选池。", meta: [`硬约束排除 ${countValue(rankingCounts.hardConstraintExcluded)} 个`, `用户排除 ${countValue(rankingCounts.userExcluded)} 个`, `缺少数据排除 ${countValue(rankingCounts.missingDataExcluded)} 个`] },
            { key: "ranking", title: "冲突取舍", status: tradeoffs.length || topCriteria(decision).length ? "done" : "muted", summary: tradeoffs[0] || "等待更多候选或评分标准后展示取舍。", meta: topCriteria(decision) },
            { key: "recommendation", title: "最终建议", status: decision.recommendation?.primaryCandidateId ? "active" : "muted", summary: decision.recommendation?.summary || "推荐结论还在整理中。", meta: decision.recommendation?.primaryCandidateId ? [candidateDisplayName(decision, decision.recommendation.primaryCandidateId)] : [] }
        ];
    }
    function renderDecisionProcess(decision, activeCandidates, candidates, source) {
        const steps = buildDecisionProcess(decision, activeCandidates, candidates, source);
        return `
            <section class="decision-process" aria-label="决策流程">
                <div class="card-title"><div><span class="eyebrow">Process</span><h3>这次决策是怎么走到结论的</h3></div></div>
                <div class="process-rail">
                    ${steps.map((step, index) => `
                        <article class="process-step process-step-${escapeHtml(step.status)}">
                            <span class="process-index">${index + 1}</span>
                            <div>
                                <h4>${escapeHtml(step.title)}</h4>
                                <p>${escapeHtml(step.summary)}</p>
                                ${step.groups ? `<div class="process-signal-grid">${step.groups.map(([label, items, empty]) => `<section><strong>${escapeHtml(label)}</strong>${renderSignalList(items, empty)}</section>`).join("")}</div>` : ""}
                                ${step.meta?.length ? `<div class="process-meta">${step.meta.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</div>` : ""}
                            </div>
                        </article>
                    `).join("")}
                </div>
            </section>
        `;
    }
    function renderDecisionResultCard(decision, primaryName) {
        const recommendation = decision.recommendation || {};
        const assistance = decision.domainState?.assistance || {};
        const analysis = assistance.currentAnalysis || assistance.analysis || {};
        const reasons = toArray(recommendation.reasons || analysis.keyReasons || analysis.reasons).map(displayText).filter(Boolean);
        const tradeoffs = toArray(recommendation.tradeoffs || analysis.tradeoffs).map(displayText).filter(Boolean);
        const missing = toArray(assistance.missingInfo || analysis.missingInfo || decision.clarifyingQuestions).map(displayText).filter(Boolean);
        const changeHints = toArray(assistance.whatIfScenarios || analysis.whatIfScenarios || analysis.changeBoundaries).map(displayText).filter(Boolean);
        return `
            <section class="decision-result-card">
                <span class="badge demo-badge">推荐结论</span>
                <h3>${escapeHtml(primaryName || "待定")}</h3>
                <p>${escapeHtml(recommendation.summary || analysis.summary || "暂无结论")}</p>
                <div class="result-grid">
                    <section><h4>为什么是它</h4>${renderSignalList(reasons, "还没有足够理由形成稳定结论。")}</section>
                    <section><h4>需要接受的代价</h4>${renderSignalList(tradeoffs, "本轮没有记录明显代价。")}</section>
                    <section><h4>还缺什么信息</h4>${renderSignalList(missing, "暂无必须补充的信息。")}</section>
                    <section><h4>什么会改变结论</h4>${renderSignalList(changeHints, "暂未记录变化边界，可继续补充偏好后重算。")}</section>
                </div>
            </section>
        `;
    }
    function renderGenericDecision(route) { conversation.enter("general", genericRouteId(route)); }

    function renderGeneralDetails(decision) {
        const container = document.getElementById("generalDetails");
        if (!container || !decision) return;
        const domainLabel = ChoiceAgentDemo.domainLabels[decision.domain] || decision.domain;
        const activeCandidates = decision.candidates || [];
        const excludedIds = new Set(decision.excludedCandidates || []);
        const pool = decision.domainState?.candidatePool || [];
        const excludedCandidates = pool.filter((item) => excludedIds.has(item.candidateId) && !activeCandidates.some((active) => active.candidateId === item.candidateId));
        const candidates = [...activeCandidates, ...excludedCandidates];
        const recommendation = decision.recommendation || {};
        const source = decision.domainState?.source || {};
        const primaryName = candidateDisplayName(decision, recommendation.primaryCandidateId);
        container.innerHTML = `
            <section class="demo-workbench unified-workbench">
                <header class="demo-header">
                    <div>
                        <span class="badge demo-badge">${escapeHtml(domainLabel)}</span>
                        <h2>${escapeHtml(decision.userGoal || "待补充目标")}</h2>
                        <p>${escapeHtml(decision.intentKey || decision.status || "")}</p>
                    </div>
                    <div class="inline-actions">
                        <button class="btn ghost" type="button" data-command="refresh_candidates">刷新候选</button>
                        <button class="btn primary" type="button" data-command="generate_recommendation">重新推荐</button>
                        <a class="btn ghost" href="#/">返回首页</a>
                    </div>
                </header>
                <div class="demo-grid">
                    <aside class="demo-sidebar">
                        <div class="card-title"><div><h3>约束</h3><p>${(decision.constraints || []).length} 项</p></div></div>
                        <div class="demo-list">
                            ${(decision.constraints || []).map((item) => `<div><strong>${escapeHtml(item.label || item.key)}</strong><span>${escapeHtml(item.value != null ? `${item.operator} ${item.value}` : (item.values || []).join("、"))}</span><button class="btn ghost" type="button" data-remove-constraint="${escapeHtml(item.constraintId || item.key)}">移除</button></div>`).join("") || `<div><span>暂无约束</span></div>`}
                        </div>
                        <form id="genericConstraintForm" class="inline-form compact">
                            <input name="key" required placeholder="约束字段">
                            <select name="operator" aria-label="约束条件"><option value="lte">不超过</option><option value="gte">不低于</option><option value="contains_any">包含</option><option value="not_contains">排除</option></select>
                            <input name="value" required placeholder="约束值">
                            <button class="btn ghost" type="submit">添加</button>
                        </form>
                        <div class="subtle-divider"></div>
                        <h4>权重</h4>
                        <div class="weight-stack">
                            ${(decision.criteria || []).map((item) => `<label class="weight-row"><span>${escapeHtml(item.label)}</span><input type="range" min="0" max="3" step="0.1" value="${Number(item.weight || 0)}" data-weight="${escapeHtml(item.key)}"><output>${Number(item.weight || 0).toFixed(1)}</output></label>`).join("") || `<div class="muted">暂无评分标准</div>`}
                        </div>
                        <div class="subtle-divider"></div>
                        <h4>数据来源</h4>
                        <div class="demo-list">
                            <div><strong>${escapeHtml(source.label || "本地状态")}</strong><span>${source.realTime ? "实时搜索" : source.mode === "manual" ? "用户输入" : source.mode === "database" ? "餐食库" : "离线模拟数据"}</span></div>
                            ${(source.warnings || []).map((warning) => `<div><span>${escapeHtml(warning)}</span></div>`).join("")}
                        </div>
                    </aside>
                    <main class="demo-main">
                        ${decision.status === "clarifying" ? `<form id="genericAnswerForm" class="inline-form"><input name="answer" required placeholder="${escapeHtml((decision.clarifyingQuestions || [])[0] || "补充关键信息")}"><button class="btn primary" type="submit">提交</button></form>` : ""}
                        ${renderDecisionResultCard(decision, primaryName)}
                        ${renderDecisionProcess(decision, activeCandidates, candidates, source)}
                        <div class="card-title"><div><h3>候选比较</h3><p>${activeCandidates.length} 个进入比较</p></div></div>
                        ${renderCandidateFunnel(decision, activeCandidates, candidates, source)}
                        <div class="demo-candidates">${candidates.map((candidate) => renderGenericCandidate(candidate, decision)).join("") || `<div class="empty">暂无候选</div>`}</div>
                        ${decision.domain !== "diet" ? `<form id="genericCandidateForm" class="inline-form">
                            <input name="name" required placeholder="候选名称">
                            <input name="summary" placeholder="简短说明">
                            ${(decision.criteria || []).map((item) => `<label class="field"><span>${escapeHtml(item.label)}</span><input type="number" step="any" name="attribute:${escapeHtml(item.key)}" placeholder="${escapeHtml(item.unit || item.label)}"></label>`).join("")}
                            <button class="btn ghost" type="submit">添加候选</button>
                        </form>` : ""}
                    </main>
                </div>
            </section>
        `;
        container.querySelectorAll(".candidate-edit").forEach(form => form.addEventListener("submit", event => {
            event.preventDefault(); sendGenericCommand("update_candidate", {candidateId:form.dataset.candidateId,summary:new FormData(form).get("summary")});
        }));
        document.querySelectorAll("[data-command]").forEach((button) => button.addEventListener("click", () => sendGenericCommand(button.dataset.command, {})));
        document.querySelectorAll("[data-weight]").forEach((input) => {
            input.addEventListener("input", () => { input.nextElementSibling.value = Number(input.value).toFixed(1); });
            input.addEventListener("change", () => sendGenericCommand("set_criterion_weight", { criterionKey: input.dataset.weight, weight: Number(input.value) }));
        });
        document.querySelectorAll("[data-candidate-action]").forEach((button) => button.addEventListener("click", () => sendGenericCommand(button.dataset.candidateAction, { candidateId: button.dataset.candidateId })));
        document.querySelectorAll("[data-remove-constraint]").forEach((button) => button.addEventListener("click", () => sendGenericCommand("remove_constraint", { constraintId: button.dataset.removeConstraint })));
        document.getElementById("genericConstraintForm")?.addEventListener("submit", (event) => {
            event.preventDefault();
            const data = new FormData(event.currentTarget);
            const operator = data.get("operator");
            const value = ["lte", "gte"].includes(operator) ? Number(data.get("value")) : String(data.get("value")).trim();
            if (typeof value === "number" && !Number.isFinite(value)) { showToast("约束值必须是数字", "error"); return; }
            sendGenericCommand("set_constraint", { constraint: { key: data.get("key"), kind: "hard", operator, value, source: "user" } });
        });
        document.getElementById("genericAnswerForm")?.addEventListener("submit", (event) => {
            event.preventDefault();
            const answer = new FormData(event.currentTarget).get("answer");
            sendGenericCommand("answer_question", { answer });
        });
        document.getElementById("genericCandidateForm")?.addEventListener("submit", (event) => {
            event.preventDefault();
            const data = new FormData(event.currentTarget);
            const attributes = {};
            for (const [key, value] of data.entries()) {
                if (key.startsWith("attribute:") && String(value).trim()) {
                    const numeric = Number(value);
                    if (!Number.isFinite(numeric)) { showToast("评分必须是有效数字", "error"); return; }
                    attributes[key.slice(10)] = numeric;
                }
            }
            sendGenericCommand("add_candidate", { candidate: { name: data.get("name"), summary: data.get("summary"), attributes } });
        });
    }

    function sendGenericCommand(type, payload) { return sendDietCommand(type, payload); }

    function candidateDisplayName(decision, candidateId) {
        if (!candidateId) return "";
        const candidates = []
            .concat(decision.candidates || [])
            .concat(decision.domainState?.candidatePool || [])
            .concat(decision.domainState?.displayBlocks || []);
        const found = candidates.find((item) => String(item.candidateId || item.id) === String(candidateId));
        return found?.name || candidateId;
    }

    function renderCandidateFunnel(decision, activeCandidates, candidates, source) {
        const rankingCounts = decision.domainState?.rankingCounts || {};
        const countValue = (value, fallback = 0) => Number.isFinite(Number(value)) ? Math.max(0, Number(value)) : fallback;
        const poolCount = Array.isArray(decision.domainState?.candidatePool) ? decision.domainState.candidatePool.length : 0;
        const hardConstraintExcluded = countValue(rankingCounts.hardConstraintExcluded);
        const userExcluded = countValue(rankingCounts.userExcluded);
        const missingDataExcluded = countValue(rankingCounts.missingDataExcluded);
        const remaining = countValue(rankingCounts.remaining, activeCandidates.length);
        const countedTotal = hardConstraintExcluded + userExcluded + missingDataExcluded + remaining;
        const foundCount = Math.max(poolCount, candidates.length, activeCandidates.length, countedTotal);
        const evidenceIds = new Set();
        for (const item of decision.evidence || []) {
            if (item?.evidenceId) evidenceIds.add(item.evidenceId);
        }
        for (const candidate of candidates) {
            for (const item of candidate.evidence || []) {
                if (item?.evidenceId) evidenceIds.add(item.evidenceId);
            }
        }
        const realtime = source?.realTime || source?.mode === "web";
        return `<div class="candidate-funnel">
            <span>找到 ${escapeHtml(foundCount)} 个候选</span>
            <span>硬约束排除 ${escapeHtml(hardConstraintExcluded)} 个</span>
            <span>用户排除 ${escapeHtml(userExcluded)} 个</span>
            <span>缺少数据排除 ${escapeHtml(missingDataExcluded)} 个</span>
            <span>${escapeHtml(remaining)} 个进入比较</span>
            ${realtime ? `<span class="funnel-live">实时搜索</span><span>${escapeHtml(evidenceIds.size)} 条 Evidence</span>` : ""}
        </div>`;
    }
    function renderGenericCandidate(candidate, decision) {
        const attrs = Object.entries(candidate.attributes || {});
        const excluded = (decision.excludedCandidates || []).includes(candidate.candidateId);
        const breakdown = candidate.scoreBreakdown || [];
        const evidence = candidate.evidence || [];
        const scoreLabel = decision.domainState?.qualitative || !breakdown.some(p => p.rawValue != null) ? "待比较" : Math.round(Number(candidate.score || 0) * 100) + "%";
        return `
            <article class="demo-candidate candidate-compare-card${excluded ? " is-eliminated" : ""}">
                <div class="demo-candidate-head">
                    <div><h3>${escapeHtml(candidate.name)}</h3><p>${escapeHtml(candidate.summary || "")}</p></div>
                    <div class="score-block"><span class="score">${escapeHtml(scoreLabel)}</span><button class="btn ghost" type="button" data-candidate-action="${excluded ? "restore_candidate" : "exclude_candidate"}" data-candidate-id="${escapeHtml(candidate.candidateId)}">${excluded ? "恢复" : "排除"}</button></div>
                </div>
                ${excluded ? `<p class="candidate-status">已从本轮比较中移除。</p>` : ""}
                <div class="attribute-grid">${attrs.slice(0, 4).map(([key, value]) => {
                    const criterion = (decision.criteria || []).find((item) => item.key === key);
                    const unit = value != null && value !== "" ? criterion?.unit || "" : "";
                    return `<span><strong>${escapeHtml(criterion?.label || key)}</strong>${escapeHtml(Array.isArray(value) ? value.join("、") : value)}${escapeHtml(unit)}</span>`;
                }).join("") || `<span><strong>可比信息</strong>暂缺关键属性</span>`}</div>
                ${breakdown.length ? `<div class="score-breakdown">${breakdown.slice(0, 4).map((item) => {
                    const criterion = (decision.criteria || []).find((criterion) => criterion.key === item.criterionKey);
                    return `<div><span>${escapeHtml(criterion?.label || item.criterionKey)}</span><meter min="0" max="100" value="${Math.round(Number(item.normalizedScore || 0))}"></meter><strong>${Math.round(Number(item.normalizedScore || 0))}</strong></div>`;
                }).join("")}</div>` : `<p class="muted">缺少可比数据，暂不展示评分拆解。</p>`}
                ${candidate.origin === "manual" ? `<form class="candidate-edit inline-form" data-candidate-id="${escapeHtml(candidate.candidateId)}"><label>候选说明<input name="summary" value="${escapeHtml(candidate.summary || "")}" placeholder="优点与顾虑"></label><button class="btn ghost">保存说明</button></form>` : ""}
                <details class="evidence-details"><summary>查看候选依据</summary>${window.EvidenceView.candidate(evidence)}</details>
            </article>
        `;
    }
    function renderDemoWorkbench(route) {
        const id = demoRouteId(route);
        const legacy = id ? ChoiceAgentDemo.findDecision(id) : null;
        const examples = legacy ? [legacy] : ChoiceAgentDemo.examples();
        state.demo.examples = examples;
        app.innerHTML = `<section class="section">
            <div class="card-title"><div><span class="eyebrow">演示数据 · 非实时</span><h2>用一个示例，体验对话式决策</h2></div><a class="btn ghost" href="#/">返回首页</a></div>
            <p>直接聊天，右侧同步整理条件和比较结果；看到不对的地方，随时修改。</p>
            ${id ? `<p class="muted">${legacy ? "旧记录保留在本地。将使用原目标和候选说明开启新版对话，旧评分与约束不会自动迁移。" : "未找到这条本地旧记录，你可以选择下面的示例。"}</p>` : ""}
            <div class="example-grid">${examples.map((item,index) => `<article class="section"><h3>${escapeHtml(ChoiceAgentDemo.domainLabels[item.domain] || "通用选择")}</h3><p>${escapeHtml(item.goal)}</p><button type="button" class="btn primary" data-action="start-demo-chat" data-index="${index}">${legacy ? "用此记录开启新版对话" : "开始对话体验"}</button></article>`).join("")}</div>
            <p id="demoError" class="diet-error" role="alert" hidden></p>
        </section>`;
    }
    async function startDemoChat(button) {
        const example = state.demo.examples?.[Number(button.dataset.index)];
        if (!example || state.home.creating) return;
        const restore = setLoading(button, "准备示例…");
        const errorBox = document.getElementById("demoError");
        errorBox.hidden = true;
        try {
            const domain = ["travel", "shopping"].includes(example.domain) ? example.domain : "generic";
            let message = example.goal;
            if (domain === "generic") {
                const candidates = example.candidateInput?.items?.length ? example.candidateInput.items : example.candidates || [];
                const descriptions = candidates.filter(c => c.name?.trim()).map(c => `${c.name}：${c.summary || "优点和顾虑待补充"}`);
                if (descriptions.length) message += "\n以下为演示候选：\n" + descriptions.join("；");
            }
            await conversation.startGeneral(message, domain, {context:{searchMode:"fixture",demoMode:true}});
        } catch (error) {
            errorBox.textContent = error.message || "示例加载失败，请重试。";
            errorBox.hidden = false;
        } finally { restore(); }
    }
    function renderDemoConstraintInput(decision) {
        const drafts = ChoiceAgentDemo.constraintDrafts(decision);
        const prefilledLabel = decision.constraintInput && decision.constraintInput.prefilledFrom === "domain_default"
            ? "这个场景没有真实约束输入，已放入领域示例约束；你可以改成自己的条件。"
            : "已预填演示约束，可修改、删除或清空后重填。";
        return `
            <section class="section constraint-input-panel">
                <div class="card-title">
                    <div>
                        <h3>约束准备</h3>
                        <p>正式使用时，系统会先确认硬条件和重要偏好。演示模式先给一组可编辑示例，确认后再进入候选项准备。</p>
                    </div>
                    <span class="badge">版本 ${escapeHtml(decision.revision)}</span>
                </div>
                <div class="mode-notice">${escapeHtml(prefilledLabel)}</div>
                <form id="demoConstraintForm" class="constraint-draft-list">
                    ${drafts.map((draft, index) => `
                        <div class="constraint-draft-row" data-draft-id="${escapeHtml(draft.id)}" data-source-constraint-key="${escapeHtml(draft.sourceConstraintKey || "")}">
                            <label class="field">
                                <span>约束 ${index + 1}</span>
                                <input name="constraintLabel" value="${escapeHtml(draft.label)}" placeholder="例如：预算不超过 1500 元">
                            </label>
                            <label class="field">
                                <span>类型</span>
                                <select name="constraintKind">
                                    <option value="hard" ${draft.kind !== "soft" ? "selected" : ""}>硬约束</option>
                                    <option value="soft" ${draft.kind === "soft" ? "selected" : ""}>偏好</option>
                                </select>
                            </label>
                            <label class="field">
                                <span>取值 / 说明</span>
                                <input name="constraintValue" value="${escapeHtml(draft.value)}" placeholder="例如：1500 元以内、成长优先">
                            </label>
                            <button class="btn ghost" type="button" data-action="demo-remove-constraint" data-draft-id="${escapeHtml(draft.id)}">删除</button>
                        </div>
                    `).join("")}
                </form>
                <div class="candidate-draft-actions">
                    <button class="btn ghost" type="button" data-action="demo-add-constraint">新增约束</button>
                    <button class="btn ghost" type="button" data-action="demo-reset-constraints">填入演示约束</button>
                    <button class="btn ghost" type="button" data-action="demo-clear-constraints">清空</button>
                    <button class="btn primary" type="button" data-action="demo-confirm-constraints">确认约束，继续候选项</button>
                </div>
            </section>
        `;
    }
    function renderDemoCandidateInput(decision) {
        const drafts = ChoiceAgentDemo.candidateDrafts(decision);
        const prefilledLabel = decision.candidateInput && decision.candidateInput.prefilledFrom === "prompt"
            ? "已从你的输入中识别候选项，可继续修正。"
            : "已预填演示候选项，可修改、删除或清空后重填。";
        return `
            <section class="section candidate-input-panel">
                <div class="card-title">
                    <div>
                        <h3>候选项准备</h3>
                        <p>正式使用时，这里需要先补充要比较的候选项。演示模式会提供可编辑示例，确认后再进入比较。</p>
                    </div>
                    <span class="badge">版本 ${escapeHtml(decision.revision)}</span>
                </div>
                <div class="mode-notice">${escapeHtml(prefilledLabel)}</div>
                <form id="demoCandidateForm" class="candidate-draft-list">
                    ${drafts.map((draft, index) => `
                        <div class="candidate-draft-row" data-draft-id="${escapeHtml(draft.id)}" data-source-candidate-id="${escapeHtml(draft.sourceCandidateId || "")}">
                            <label class="field">
                                <span>候选 ${index + 1}</span>
                                <input name="candidateName" value="${escapeHtml(draft.name)}" placeholder="候选名称，例如 A 公司、莫干山、方案 A">
                            </label>
                            <label class="field candidate-summary-field">
                                <span>一句话说明</span>
                                <textarea name="candidateSummary" placeholder="补充你对这个候选的关键信息。">${escapeHtml(draft.summary)}</textarea>
                            </label>
                            <button class="btn ghost" type="button" data-action="demo-remove-candidate" data-draft-id="${escapeHtml(draft.id)}">删除</button>
                        </div>
                    `).join("")}
                </form>
                <div class="candidate-draft-actions">
                    <button class="btn ghost" type="button" data-action="demo-add-candidate">新增候选</button>
                    <button class="btn ghost" type="button" data-action="demo-reset-candidates">填入演示候选项</button>
                    <button class="btn ghost" type="button" data-action="demo-clear-candidates">清空</button>
                    <button class="btn primary" type="button" data-action="demo-confirm-candidates">确认候选，开始比较</button>
                </div>
            </section>
        `;
    }
    function renderDemoNextSteps(stage) {
        const constraintStatus = stage === "constraint_input" ? "current" : "done";
        const candidateStatus = stage === "candidate_input" ? "current" : stage === "constraint_input" ? "todo" : "done";
        return `
            <div class="subtle-divider"></div>
            <div class="card-title"><div><h3>下一步</h3><p>先确认约束和候选，再进入排序和结论。</p></div></div>
            <div class="demo-list">
                <div data-status="${constraintStatus}"><strong>1. 确认约束</strong><span>硬条件和重要偏好可以先写清楚。</span></div>
                <div data-status="${candidateStatus}"><strong>2. 确认候选</strong><span>至少保留 2 个有效候选。</span></div>
                <div><strong>3. 调整权重</strong><span>根据你更看重的维度重新排序。</span></div>
                <div><strong>4. 生成结论</strong><span>用演示数据展示推荐理由和替代项。</span></div>
            </div>
        `;
    }    function renderDemoState(decision, activeRankings) {
        const constraints = (decision.constraints || []).length
            ? `<div class="demo-list">${decision.constraints.map((item) => `<div><strong>${escapeHtml(item.label)}</strong><span>${escapeHtml(item.kind)} · ${escapeHtml(item.value)}</span></div>`).join("")}</div>`
            : `<div class="empty compact">暂无硬约束，当前先比较偏好维度。</div>`;
        const questions = (decision.unansweredQuestions || []).filter((item) => !item.answered);
        const questionHtml = questions.length
            ? `<div class="chips">${questions.flatMap((question) => question.options.map((option) => `<button class="chip" data-action="demo-answer-question" data-question-id="${escapeHtml(question.id)}" data-answer="${escapeHtml(option)}">${escapeHtml(option)}</button>`)).join("")}</div><p class="muted">${escapeHtml(questions[0].question)}</p>`
            : `<p class="muted">关键条件已足够进入演示比较。</p>`;
        return `
            <div class="card-title"><div><h3>决策状态</h3><p>${escapeHtml(decision.stage === "constraint_input" ? `${ChoiceAgentDemo.constraintDrafts(decision).filter((item) => String(item.label || "").trim()).length} 个约束草稿` : decision.stage === "candidate_input" ? `${ChoiceAgentDemo.candidateDrafts(decision).filter((item) => String(item.name || "").trim()).length} 个候选草稿` : `${activeRankings.length} 个可选候选`)}</p></div></div>
            <h4>约束</h4>
            ${constraints}
            <div class="subtle-divider"></div>
            <h4>澄清问题</h4>
            ${questionHtml}
            <div class="subtle-divider"></div>
            <h4>假设</h4>
            <div class="demo-list">${(decision.assumptions || []).map((item) => `<div><span>${escapeHtml(item)}</span></div>`).join("")}</div>
            <div class="subtle-divider"></div>
            <h4>Trace</h4>
            <div class="demo-trace">${(decision.trace || []).map((item) => `<span data-status="${escapeHtml(item.status)}">${escapeHtml(item.label)}</span>`).join("")}</div>
        `;
    }
    function renderDemoWeights(decision) {
        return `
            <div class="subtle-divider"></div>
            <div class="card-title"><div><h3>偏好权重</h3><p>拖动后立即重排。</p></div></div>
            <div class="weight-list">
                ${(decision.criteria || []).map((criterion) => `
                    <label class="weight-row">
                        <span>${escapeHtml(criterion.label)}</span>
                        <strong>${escapeHtml(criterion.weight)}</strong>
                        <input type="range" min="0" max="60" value="${escapeHtml(criterion.weight)}" data-action="demo-weight" data-key="${escapeHtml(criterion.key)}">
                    </label>
                `).join("")}
            </div>
        `;
    }
    function renderDemoCandidate(item, index, decision) {
        const candidate = item.candidate;
        const attributes = Object.entries(candidate.attributes || {}).map(([key, value]) => {
            const criterion = (decision.criteria || []).find((item) => item.key === key);
            return `<span>${escapeHtml(criterion ? criterion.label : key)}：${escapeHtml(value)}</span>`;
        }).join("");
        const evidence = (candidate.evidence || []).length
            ? candidate.evidence.map((item) => `<li>${escapeHtml(item.claim)}<span>${escapeHtml(item.sourceTitle || "演示数据")}</span></li>`).join("")
            : `<li>暂无外部证据，当前只展示结构化比较。</li>`;
        return `
            <article class="demo-candidate ${candidate.eliminated ? "is-eliminated" : ""}">
                <div class="demo-candidate-head">
                    <div>
                        <span class="rank">#${index + 1}</span>
                        <h3>${escapeHtml(candidate.name)}</h3>
                        <p>${escapeHtml(candidate.summary)}</p>
                    </div>
                    <div class="score-block"><strong>${escapeHtml(item.score)}</strong><span>分</span></div>
                </div>
                <div class="attribute-grid">${attributes}</div>
                <ul class="evidence-list">${evidence}</ul>
                <button class="btn ${candidate.eliminated ? "soft" : "ghost"}" data-action="demo-toggle-candidate" data-candidate-id="${escapeHtml(candidate.id)}">
                    ${candidate.eliminated ? "恢复候选" : "排除候选"}
                </button>
            </article>
        `;
    }
    function renderDemoRecommendation(decision, recommendation) {
        if (!recommendation) {
            return `
                <div class="card-title">
                    <div>
                        <h3>推荐结论</h3>
                        <p>调整权重或排除候选后，点击生成结论查看当前选择建议。</p>
                    </div>
                </div>
                <div class="empty">尚未生成结论。</div>
            `;
        }
        const candidate = (decision.candidates || []).find((item) => item.id === recommendation.candidateId);
        const reasons = (recommendation.reasons || []).map((item) => `<li>${escapeHtml(item.text)}</li>`).join("");
        const tradeoffs = (recommendation.tradeOffs || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
        return `
            <div class="card-title">
                <div>
                    <h3>推荐结论</h3>
                    <p>${escapeHtml(candidate ? candidate.name : "当前候选")}</p>
                </div>
                <span class="badge demo-badge">演示结论</span>
            </div>
            <p class="recommendation-copy">${escapeHtml(recommendation.conclusion)}</p>
            <div class="grid two">
                <div><h4>理由</h4><ul class="evidence-list">${reasons}</ul></div>
                <div><h4>取舍</h4><ul class="evidence-list">${tradeoffs}</ul></div>
            </div>
            ${recommendation.alternative ? `<p class="muted">替代方案：${escapeHtml(recommendation.alternative.whenToChoose)}</p>` : ""}
        `;
    }
    function updateDemoWeight(key, weight) {
        if (!state.demo.decision) {
            return;
        }
        state.demo.decision = ChoiceAgentDemo.updateDecision(state.demo.decision, (decision) => {
            decision.criteria = decision.criteria.map((criterion) => criterion.key === key ? { ...criterion, weight } : criterion);
            decision.recommendation = undefined;
            decision.status = "comparing";
            decision.nextAction = "compare";
        });
        renderDemoWorkbench(currentRoute());
    }
    function toggleDemoCandidate(candidateId) {
        if (!state.demo.decision) {
            return;
        }
        state.demo.decision = ChoiceAgentDemo.updateDecision(state.demo.decision, (decision) => {
            decision.candidates = decision.candidates.map((candidate) => candidate.id === candidateId ? { ...candidate, eliminated: !candidate.eliminated } : candidate);
            decision.recommendation = undefined;
            decision.status = "comparing";
        });
        renderDemoWorkbench(currentRoute());
    }
    function completeDemoDecision() {
        if (!state.demo.decision) {
            return;
        }
        if (state.demo.decision.stage === "constraint_input" || state.demo.decision.stage === "candidate_input" || state.demo.decision.candidateState !== "complete") {
            showToast("先确认候选项，再生成结论。", "error");
            return;
        }
        state.demo.decision = ChoiceAgentDemo.updateDecision(state.demo.decision, (decision) => {
            decision.recommendation = ChoiceAgentDemo.explain(decision);
            decision.status = "decided";
            decision.nextAction = "done";
            decision.trace = (decision.trace || []).map((item) => ({ ...item, status: "done" }));
        });
        renderDemoWorkbench(currentRoute());
    }
    function answerDemoQuestion(questionId, answer) {
        if (!state.demo.decision) {
            return;
        }
        state.demo.decision = ChoiceAgentDemo.updateDecision(state.demo.decision, (decision) => {
            decision.unansweredQuestions = (decision.unansweredQuestions || []).map((question) => question.id === questionId ? { ...question, answered: true, answer } : question);
            decision.assumptions = [...(decision.assumptions || []), `你对澄清问题选择了：${answer}`];
        });
        renderDemoWorkbench(currentRoute());
    }
    function collectDemoConstraintDrafts() {
        return Array.from(document.querySelectorAll(".constraint-draft-row")).map((row) => {
            const labelInput = row.querySelector('input[name="constraintLabel"]');
            const kindInput = row.querySelector('select[name="constraintKind"]');
            const valueInput = row.querySelector('input[name="constraintValue"]');
            return {
                id: row.dataset.draftId || "",
                sourceConstraintKey: row.dataset.sourceConstraintKey || "",
                label: labelInput ? labelInput.value.trim() : "",
                kind: kindInput ? kindInput.value : "hard",
                value: valueInput ? valueInput.value.trim() : ""
            };
        });
    }
    function syncDemoConstraintDrafts() {
        if (!state.demo.decision || !document.getElementById("demoConstraintForm")) {
            return;
        }
        state.demo.decision = ChoiceAgentDemo.replaceConstraintDrafts(state.demo.decision, collectDemoConstraintDrafts(), "manual");
    }
    function addDemoConstraintDraft() {
        if (!state.demo.decision) {
            return;
        }
        syncDemoConstraintDrafts();
        state.demo.decision = ChoiceAgentDemo.addConstraintDraft(state.demo.decision);
        renderDemoWorkbench(currentRoute());
    }
    function removeDemoConstraintDraft(draftId) {
        if (!state.demo.decision) {
            return;
        }
        syncDemoConstraintDrafts();
        state.demo.decision = ChoiceAgentDemo.removeConstraintDraft(state.demo.decision, draftId);
        renderDemoWorkbench(currentRoute());
    }
    function resetDemoConstraintDrafts() {
        if (!state.demo.decision) {
            return;
        }
        state.demo.decision = ChoiceAgentDemo.resetConstraintDrafts(state.demo.decision);
        renderDemoWorkbench(currentRoute());
    }
    function clearDemoConstraintDrafts() {
        if (!state.demo.decision) {
            return;
        }
        state.demo.decision = ChoiceAgentDemo.clearConstraintDrafts(state.demo.decision);
        renderDemoWorkbench(currentRoute());
    }
    function confirmDemoConstraintDrafts() {
        if (!state.demo.decision) {
            return;
        }
        syncDemoConstraintDrafts();
        const result = ChoiceAgentDemo.confirmConstraintDrafts(state.demo.decision);
        state.demo.decision = result.decision;
        if (result.warning) {
            showToast(result.warning);
        }
        renderDemoWorkbench(currentRoute());
    }
    function editDemoConstraintDrafts() {
        if (!state.demo.decision) {
            return;
        }
        state.demo.decision = ChoiceAgentDemo.editConstraints(state.demo.decision);
        renderDemoWorkbench(currentRoute());
    }    function collectDemoCandidateDrafts() {
        return Array.from(document.querySelectorAll(".candidate-draft-row")).map((row) => {
            const nameInput = row.querySelector('input[name="candidateName"]');
            const summaryInput = row.querySelector('textarea[name="candidateSummary"]');
            return {
                id: row.dataset.draftId || "",
                sourceCandidateId: row.dataset.sourceCandidateId || "",
                name: nameInput ? nameInput.value.trim() : "",
                summary: summaryInput ? summaryInput.value.trim() : ""
            };
        });
    }
    function syncDemoCandidateDrafts() {
        if (!state.demo.decision || !document.getElementById("demoCandidateForm")) {
            return;
        }
        state.demo.decision = ChoiceAgentDemo.replaceCandidateDrafts(state.demo.decision, collectDemoCandidateDrafts(), "manual");
    }
    function addDemoCandidateDraft() {
        if (!state.demo.decision) {
            return;
        }
        syncDemoCandidateDrafts();
        state.demo.decision = ChoiceAgentDemo.addCandidateDraft(state.demo.decision);
        renderDemoWorkbench(currentRoute());
    }
    function removeDemoCandidateDraft(draftId) {
        if (!state.demo.decision) {
            return;
        }
        syncDemoCandidateDrafts();
        state.demo.decision = ChoiceAgentDemo.removeCandidateDraft(state.demo.decision, draftId);
        renderDemoWorkbench(currentRoute());
    }
    function resetDemoCandidateDrafts() {
        if (!state.demo.decision) {
            return;
        }
        state.demo.decision = ChoiceAgentDemo.resetCandidateDrafts(state.demo.decision);
        renderDemoWorkbench(currentRoute());
    }
    function clearDemoCandidateDrafts() {
        if (!state.demo.decision) {
            return;
        }
        state.demo.decision = ChoiceAgentDemo.clearCandidateDrafts(state.demo.decision);
        renderDemoWorkbench(currentRoute());
    }
    function confirmDemoCandidateDrafts() {
        if (!state.demo.decision) {
            return;
        }
        syncDemoCandidateDrafts();
        const result = ChoiceAgentDemo.confirmCandidateDrafts(state.demo.decision);
        state.demo.decision = result.decision;
        if (result.error) {
            showToast(result.error, "error");
            renderDemoWorkbench(currentRoute());
            return;
        }
        renderDemoWorkbench(currentRoute());
    }
    function editDemoCandidateDrafts() {
        if (!state.demo.decision) {
            return;
        }
        state.demo.decision = ChoiceAgentDemo.editCandidates(state.demo.decision);
        renderDemoWorkbench(currentRoute());
    }
    function renderMessage(message) {
        const mealCards = (message.meals || []).map((meal) => renderMealCard(meal, { feedback: true, sessionId: message.sessionId })).join("") + (message.choices || []).map(c => `<article class="general-choice"><strong>${escapeHtml(c.name)}</strong><p>${escapeHtml(c.summary || "")}</p></article>`).join("");
        const historyReasons = message.analysis?.sources
            ? [...(message.analysis.keyReasons || message.analysis.reasons || []), ...(message.analysis.tradeoffs || [])].slice(0, 6)
            : [];
        const historyEvidence = historyReasons.length
            ? `<details class="message-meta evidence-history"><summary>查看当轮依据</summary><ul class="evidence-linked-list">${historyReasons.map((item) => window.EvidenceView.point(item, message.analysis, null)).join("")}</ul></details>`
            : "";
        const missingSlots = message.missingSlots && message.missingSlots.length
            ? `<div class="chips">${message.missingSlots.map((slot) => `<span class="chip selected">${escapeHtml(SLOT_LABELS[slot] || slot)}</span>`).join("")}</div>`
            : "";
        const trace = message.traceId
            ? `<span>traceId：<a href="#/admin/traces" data-action="open-trace" data-trace-id="${escapeHtml(message.traceId)}">${escapeHtml(message.traceId)}</a></span>`
            : "";
        return `
            <article class="message ${message.role}">
                <div class="bubble">${escapeHtml(message.text)}</div>
                ${missingSlots}
                ${mealCards ? `<details class="diet-history"><summary>查看当时推荐</summary><div class="grid">${mealCards}</div></details>` : ""}
                ${historyEvidence}
                ${trace ? `<details class="message-meta"><summary>本轮详情</summary>${trace}</details>` : ""}
            </article>
        `;
    }
    function scrollMessagesToBottom() {
        const messages = document.getElementById("messages");
        if (messages) {
            messages.scrollTop = messages.scrollHeight;
        }
    }
    function defaultChatMessages() {
        return [
            {
                role: "assistant",
                text: "告诉我你的用餐时间、口味、场景或健康目标，我来帮你把这次选择想清楚。"
            }
        ];
    }

    function renderMealForm() {
        const meal = state.editingMeal || emptyMeal();
        const title = meal.id ? "编辑餐食" : "新增餐食";
        return `
            <div class="card-title">
                <div>
                    <h3>${title}</h3>
                    <p>从下拉框选择标签，用餐时间为必选项，其余可留空。</p>
                </div>
            </div>
            <form id="mealForm" class="form-grid">
                <input type="hidden" name="mealId" value="${escapeHtml(meal.id || "")}">
                <div class="field full">
                    <label for="mealName">餐食名称</label>
                    <input id="mealName" name="name" value="${escapeHtml(meal.name || "")}" placeholder="例如：番茄鸡蛋面" required>
                </div>
                <p class="field-hint full">标签下拉框支持多选：Windows 按住 Ctrl，Mac 按住 Command 点击可多项选择。</p>
                ${Object.entries(SLOT_LABELS).map(([key, label]) => renderSlotPicker(key, label, meal[key] || [])).join("")}
                <div class="field full">
                    <div class="button-row">
                        <button class="btn primary" type="submit">${meal.id ? "保存修改" : "创建餐食"}</button>
                        <button class="btn ghost" type="button" data-action="cancel-edit">清空</button>
                    </div>
                </div>
            </form>
        `;
    }
    function renderSlotPicker(key, label, selected) {
        const options = state.slotOptions && state.slotOptions[key] ? state.slotOptions[key] : [];
        const selectedSet = new Set(selected || []);
        const required = key === "mealTime";
        return `
            <div class="field">
                <label for="slot-${escapeHtml(key)}">${escapeHtml(label)}${required ? "（必选）" : ""}</label>
                <select
                    id="slot-${escapeHtml(key)}"
                    class="slot-select"
                    name="${escapeHtml(key)}"
                    multiple
                    size="5"
                    ${required ? "required" : ""}
                >
                    ${options.map((option) => {
                        const isSelected = selectedSet.has(option);
                        return `<option value="${escapeHtml(option)}" ${isSelected ? "selected" : ""}>${escapeHtml(option)}</option>`;
                    }).join("")}
                </select>
            </div>
        `;
    }
    function emptyMeal() {
        return {
            name: "",
            mealTime: [],
            mood: [],
            scene: [],
            healthGoal: [],
            cuisine: [],
            taste: [],
            convenience: []
        };
    }
    function renderMealList(meals, options) {
        if (!meals.length) {
            return `<div class="empty">暂无餐食。可以先新增几道常吃的菜。</div>`;
        }
        return `<div class="grid two">${meals.map((meal) => renderMealCard(meal, options || {})).join("")}</div>`;
    }
    function renderMealCard(meal, options) {
        const editable = options && options.editable;
        const feedback = options && options.feedback;
        const compact = options && options.compact;
        return `
            <article class="meal-card">
                <header>
                    <div>
                        <h3>${escapeHtml(meal.name)}</h3>
                        <p class="muted">${escapeHtml(compact ? (meal.sourceType === "PERSONAL" ? "你的餐食库" : "公共餐食库") : (meal.sourceType || ""))}</p>
                    </div>
                    ${meal.matchScore ? `<span class="score">匹配 ${Math.round(meal.matchScore * 100)}%</span>` : ""}
                </header>
                ${compact ? `<p class="diet-meal-reason">${escapeHtml(meal.reason || "根据当前条件筛选")}</p><details><summary>查看餐食标签</summary>` : ""}
                <div class="chips">${mealTags(meal).map((tag) => `<span class="chip selected">${escapeHtml(tag)}</span>`).join("")}</div>
                ${compact ? "</details>" : ""}
                ${editable ? `
                    <div class="button-row">
                        <button class="btn soft" data-action="edit-meal" data-id="${escapeHtml(meal.id)}">编辑</button>
                        <button class="btn ghost" data-action="delete-meal" data-id="${escapeHtml(meal.id)}">删除</button>
                    </div>
                ` : ""}
                ${feedback ? `
                    <div class="button-row">
                        <button class="btn soft" data-action="feedback" data-action-value="LIKE" data-item-id="${escapeHtml(meal.id)}" data-session-id="${escapeHtml(options.sessionId || "")}">喜欢</button>
                        <button class="btn ghost" data-action="feedback" data-action-value="ADOPT" data-item-id="${escapeHtml(meal.id)}" data-session-id="${escapeHtml(options.sessionId || "")}">采纳</button>
                        <button class="btn ghost" data-action="feedback" data-action-value="DISLIKE" data-item-id="${escapeHtml(meal.id)}" data-session-id="${escapeHtml(options.sessionId || "")}">不合适</button>
                    </div>
                ` : ""}
            </article>
        `;
    }
    function mealTags(meal) {
        return Object.keys(SLOT_LABELS).flatMap((key) => (meal[key] || []).map((value) => `${SLOT_LABELS[key]}：${value}`));
    }
    async function ensurePersonalMeals(force) {
        if (!force && state.personalMeals.length) {
            return;
        }
        try {
            state.personalMeals = await DietApi.listPersonalMeals();
            state.home.loaded = false;
            if (currentRoute() === "/diet/meals/personal") {
                document.getElementById("personalMealList").innerHTML = renderMealList(state.personalMeals, { editable: true });
            }
        } catch (error) {
            showToast(error.message || "个人餐食加载失败", "error");
        }
    }
    async function ensureSlotOptions() {
        if (state.slotOptions) {
            return;
        }
        try {
            state.slotOptions = await DietApi.slotOptions();
        } catch (error) {
            showToast(error.message || "槽位字典加载失败", "error");
            throw error;
        }
    }
    async function saveMeal(form) {
        const { id, payload } = mealPayloadFromForm(form);
        if (!payload.name) {
            showToast("请填写餐食名称", "error");
            return;
        }
        if (!payload.mealTime.length) {
            showToast("请至少选择一个用餐时间标签", "error");
            return;
        }
        const restore = setLoading(form.querySelector("button[type=submit]"), "保存中...");
        try {
            await guard(async () => {
                if (id) {
                    return DietApi.updatePersonalMeal(id, payload);
                }
                return DietApi.createPersonalMeal(payload);
            }, id ? "餐食已更新" : "餐食已创建");
            state.editingMeal = null;
            await ensurePersonalMeals(true);
            renderPersonalMeals();
        } finally {
            restore();
        }
    }
    function mealPayloadFromForm(form) {
        const formData = new FormData(form);
        const payload = {
            name: String(formData.get("name") || "").trim()
        };
        Object.keys(SLOT_LABELS).forEach((key) => {
            payload[key] = formData.getAll(key).filter(Boolean);
        });
        return {
            id: String(formData.get("mealId") || "").trim(),
            payload
        };
    }
    function editMeal(id) {
        const meal = state.personalMeals.find((item) => String(item.id) === String(id));
        if (!meal) {
            showToast("没有找到要编辑的餐食", "error");
            return;
        }
        state.editingMeal = JSON.parse(JSON.stringify(meal));
        renderPersonalMeals();
    }
    async function deleteMeal(id) {
        const meal = state.personalMeals.find((item) => String(item.id) === String(id));
        if (!meal || !window.confirm(`确定删除“${meal.name}”？`)) {
            return;
        }
        await guard(async () => {
            await DietApi.deletePersonalMeal(id);
            await ensurePersonalMeals(true);
            renderPersonalMeals();
        }, "餐食已删除");
    }
    function renderPublicMeals() {
        app.innerHTML = `
            <section class="section">
                <div class="card-title">
                    <div>
                        <h2>公共餐食</h2>
                        <p>系统预置餐食库，只读展示。需要快速体验时，可以在决策助手里临时使用公共数据。</p>
                    </div>
                    <a class="btn primary" href="#/diet/chat">去决策助手</a>
                </div>
                <div id="publicMealList">${renderMealList(state.publicMeals, {})}</div>
            </section>
        `;
        ensurePublicMeals();
    }
    async function ensurePublicMeals(force) {
        if (!force && state.publicMeals.length) {
            return;
        }
        try {
            state.publicMeals = await DietApi.listPublicMeals();
            state.home.loaded = false;
            if (currentRoute() === "/diet/meals/public") {
                document.getElementById("publicMealList").innerHTML = renderMealList(state.publicMeals, {});
            }
        } catch (error) {
            showToast(error.message || "公共餐食加载失败", "error");
        }
    }
    function renderTraces() {
        const selected = state.traces.selected;
        app.innerHTML = `
            <section class="split">
                <div class="section">
                    <div class="card-title">
                        <div>
                            <h2>决策过程</h2>
                            <p>按时间轴查看用户输入、意图理解、状态变化、候选过滤、Agent 输出和推荐变化。</p>
                        </div>
                    </div>
                    <form id="traceFilterForm" class="form-grid">
                        <div class="field">
                            <label>开始时间</label>
                            <input type="datetime-local" name="startAt" value="${escapeHtml(state.traces.filters.startAt)}" required>
                        </div>
                        <div class="field">
                            <label>结束时间</label>
                            <input type="datetime-local" name="endAt" value="${escapeHtml(state.traces.filters.endAt)}" required>
                        </div>
                        <div class="field">
                            <label>会话 ID（可选）</label>
                            <input name="sessionId" value="${escapeHtml(state.traces.filters.sessionId)}" placeholder="填写后按会话查询">
                        </div>
                        <div class="field">
                            <label>数量上限</label>
                            <input type="number" min="1" max="500" name="limit" value="${escapeHtml(state.traces.filters.limit)}">
                        </div>
                        <div class="field">
                            <label>标注状态</label>
                            <select name="onlyUnlabeled">
                                <option value="false" ${!state.traces.filters.onlyUnlabeled ? "selected" : ""}>全部</option>
                                <option value="true" ${state.traces.filters.onlyUnlabeled ? "selected" : ""}>仅未标注</option>
                            </select>
                        </div>
                        <div class="field">
                            <span>&nbsp;</span>
                            <button class="btn primary" type="submit">${state.traces.loading ? "查询中..." : "查询 Trace"}</button>
                        </div>
                    </form>
                    <div class="subtle-divider"></div>
                    ${renderTraceTable()}
                </div>
                <aside class="section">
                    ${selected ? renderTraceDetail(selected) : `<div class="empty">选择一条 Trace 查看决策过程和标注表单。</div>`}
                </aside>
            </section>
        `;
    }
    function renderTraceTable() {
        if (!state.traces.rows.length) {
            return `<div class="empty">暂无 Trace 数据。可以先在聊天页发起几轮对话。</div>`;
        }
        return `
            <div class="table-wrap">
                <table>
                    <thead>
                        <tr>
                            <th>Trace ID</th>
                            <th>会话</th>
                            <th>状态</th>
                            <th>事件</th>
                            <th>耗时</th>
                            <th>创建时间</th>
                            <th>标注</th>
                            <th>操作</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${state.traces.rows.map((row) => `
                            <tr>
                                <td>${escapeHtml(row.traceId)}</td>
                                <td>${escapeHtml(row.sessionId)}</td>
                                <td>${escapeHtml(row.status || "-")}</td>
                                <td>${escapeHtml(row.eventCount ?? "-")}</td>
                                <td>${row.durationMs ? `${escapeHtml(row.durationMs)} ms` : "-"}</td>
                                <td>${escapeHtml(row.createdAt || "-")}</td>
                                <td>${row.expectedIntent ? `<span class="badge">${escapeHtml(row.expectedIntent)}</span>` : "<span class=\"muted\">未标注</span>"}</td>
                                <td><button class="btn soft" data-action="select-trace" data-trace-id="${escapeHtml(row.traceId)}">查看</button></td>
                            </tr>
                        `).join("")}
                    </tbody>
                </table>
            </div>
        `;
    }
    function renderTraceDetail(trace) {
        const timelineHtml = window.TraceTimeline ? window.TraceTimeline.render(trace) : `<details open><summary>Trace JSON</summary><pre class="json-box">${escapeHtml(safeJson(trace.traceJson))}</pre></details>`;
        return `
            <div class="card-title">
                <div>
                    <h3>Trace 详情</h3>
                    <p>${escapeHtml(trace.traceId)}</p>
                </div>
            </div>
            <div class="grid">
                <div>
                    <span class="badge">${escapeHtml(trace.status || "UNKNOWN")}</span>
                    <p class="muted">Session：${escapeHtml(trace.sessionId || "-")} · Events：${escapeHtml(trace.eventCount ?? "-")} · Duration：${escapeHtml(trace.durationMs ?? "-")} ms</p>
                </div>
                ${timelineHtml}
                <form id="traceLabelForm" class="form-grid">
                    <input type="hidden" name="traceId" value="${escapeHtml(trace.traceId)}">
                    <div class="field">
                        <label>预期意图</label>
                        <select name="expectedIntent">
                            <option value="">不标注</option>
                            ${INTENTS.map((intent) => `<option value="${intent}" ${trace.expectedIntent === intent ? "selected" : ""}>${intent}</option>`).join("")}
                        </select>
                    </div>
                    <div class="field">
                        <label>澄清动作</label>
                        <select name="expectedClarifyAction">
                            <option value="">不标注</option>
                            <option value="ASK" ${trace.expectedClarifyAction === "ASK" ? "selected" : ""}>ASK</option>
                            <option value="READY" ${trace.expectedClarifyAction === "READY" ? "selected" : ""}>READY</option>
                        </select>
                    </div>
                    <div class="field full">
                        <label>预期槽位 JSON</label>
                        <textarea name="expectedSlots" placeholder='{"mealTime":["晚餐"],"taste":["清淡"]}'>${escapeHtml(safeJson(trace.expectedSlots))}</textarea>
                    </div>
                    <div class="field full">
                        <label>备注</label>
                        <textarea name="labelNote" placeholder="标注说明">${escapeHtml(trace.labelNote || "")}</textarea>
                    </div>
                    <div class="field full">
                        <button class="btn primary" type="submit">保存标注</button>
                    </div>
                </form>
            </div>
        `;
    }
    async function searchTraces(form) {
        const formData = new FormData(form);
        state.traces.filters = {
            startAt: formData.get("startAt"),
            endAt: formData.get("endAt"),
            sessionId: formData.get("sessionId").trim(),
            onlyUnlabeled: formData.get("onlyUnlabeled") === "true",
            limit: Number(formData.get("limit") || 50)
        };
        state.traces.loading = true;
        renderTraces();
        try {
            if (state.traces.filters.sessionId) {
                state.traces.rows = await DietApi.listSessionTraces(state.traces.filters.sessionId, state.traces.filters.limit);
            } else {
                state.traces.rows = await DietApi.listTraces({
                    startAt: state.traces.filters.startAt,
                    endAt: state.traces.filters.endAt,
                    onlyUnlabeled: state.traces.filters.onlyUnlabeled,
                    limit: state.traces.filters.limit
                });
            }
            state.traces.selected = state.traces.rows[0] || null;
        } catch (error) {
            showToast(error.message || "Trace 查询失败", "error");
        } finally {
            state.traces.loading = false;
            renderTraces();
        }
    }
    async function selectTrace(traceId) {
        await guard(async () => {
            state.traces.selected = await DietApi.getTrace(traceId);
            renderTraces();
        });
    }
    async function saveTraceLabel(form) {
        const formData = new FormData(form);
        const traceId = formData.get("traceId");
        const slotsText = formData.get("expectedSlots").trim();
        let expectedSlots = null;
        if (slotsText) {
            try {
                expectedSlots = JSON.parse(slotsText);
            } catch (error) {
                showToast("预期槽位必须是合法 JSON", "error");
                return;
            }
        }
        const payload = {
            expectedIntent: formData.get("expectedIntent") || null,
            expectedSlots,
            expectedClarifyAction: formData.get("expectedClarifyAction") || null,
            labelNote: formData.get("labelNote").trim()
        };
        await guard(async () => {
            await DietApi.labelTrace(traceId, payload);
            state.traces.selected = await DietApi.getTrace(traceId);
            const index = state.traces.rows.findIndex((row) => row.traceId === traceId);
            if (index >= 0) {
                state.traces.rows[index] = state.traces.selected;
            }
            renderTraces();
        }, "Trace 标注已保存");
    }
    function renderEvaluations() {
        if (evaluationDashboard) {
            evaluationDashboard.render();
            return;
        }
        app.innerHTML = `
            <section class="section">
                <div class="card-title">
                    <div>
                        <h2>评估报告</h2>
                        <p>基于已落库 Trace 生成规则评分、可选 LLM Judge 和反馈归因指标。</p>
                    </div>
                </div>
                <form id="evaluationForm" class="form-grid">
                    <div class="field">
                        <label>开始时间</label>
                        <input type="datetime-local" name="startAt" value="${escapeHtml(state.evaluation.form.startAt)}" required>
                    </div>
                    <div class="field">
                        <label>结束时间</label>
                        <input type="datetime-local" name="endAt" value="${escapeHtml(state.evaluation.form.endAt)}" required>
                    </div>
                    <div class="field">
                        <label>数量上限</label>
                        <input type="number" min="1" max="500" name="limit" value="${escapeHtml(state.evaluation.form.limit)}">
                    </div>
                    <div class="field">
                        <label>LLM Judge</label>
                        <select name="includeLlmJudge">
                            <option value="false" ${!state.evaluation.form.includeLlmJudge ? "selected" : ""}>关闭</option>
                            <option value="true" ${state.evaluation.form.includeLlmJudge ? "selected" : ""}>开启</option>
                        </select>
                    </div>
                    <div class="field full">
                        <button class="btn primary" type="submit">${state.evaluation.loading ? "评估中..." : "生成评估报告"}</button>
                    </div>
                </form>
            </section>
            <section class="section" style="margin-top: 18px;">
                ${renderEvaluationReport()}
            </section>
        `;
    }
    function renderEvaluationReport() {
        const report = state.evaluation.report;
        if (!report) {
            return `<div class="empty">暂无报告。选择时间范围后生成评估。</div>`;
        }
        return `
            <div class="grid three">
                ${statCard("Trace 总数", report.totalTraces, "本次纳入评估的请求数")}
                ${statCard("已标注", report.labeledTraces, "有人工标签的 Trace 数")}
                ${statCard("平均分", report.avgScore === null || report.avgScore === undefined ? "-" : Number(report.avgScore).toFixed(2), "综合评分")}
            </div>
            <div class="subtle-divider"></div>
            <div class="grid two">
                <div>
                    <h3>指标均值</h3>
                    ${renderMetrics(report.metricAverages)}
                </div>
                <div>
                    <h3>报告范围</h3>
                    <p class="muted">${escapeHtml(report.startAt)} 至 ${escapeHtml(report.endAt)}</p>
                </div>
            </div>
            <div class="subtle-divider"></div>
            ${renderEvaluationTable(report.traceResults || [])}
        `;
    }
    function renderMetrics(metrics) {
        const entries = Object.entries(metrics || {});
        if (!entries.length) {
            return `<div class="empty">暂无指标</div>`;
        }
        return `<div class="chips">${entries.map(([key, value]) => `<span class="chip selected">${escapeHtml(key)}：${Number(value).toFixed(2)}</span>`).join("")}</div>`;
    }
    function renderEvaluationTable(rows) {
        if (!rows.length) {
            return `<div class="empty">暂无 Trace 明细</div>`;
        }
        return `
            <div class="table-wrap">
                <table>
                    <thead>
                        <tr>
                            <th>Trace ID</th>
                            <th>会话</th>
                            <th>综合分</th>
                            <th>规则分</th>
                            <th>LLM 分</th>
                            <th>反馈分</th>
                            <th>指标 / 明细</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${rows.map((row) => `
                            <tr>
                                <td>${escapeHtml(row.traceId)}</td>
                                <td>${escapeHtml(row.sessionId)}</td>
                                <td>${formatScore(row.score)}</td>
                                <td>${formatScore(row.ruleScore)}</td>
                                <td>${formatScore(row.llmJudgeScore)}</td>
                                <td>${formatScore(row.userFeedbackScore)}</td>
                                <td>
                                    <details>
                                        <summary>查看 JSON</summary>
                                        <pre class="json-box">${escapeHtml(JSON.stringify({ metrics: row.metrics, detail: row.detail }, null, 2))}</pre>
                                    </details>
                                </td>
                            </tr>
                        `).join("")}
                    </tbody>
                </table>
            </div>
        `;
    }
    function formatScore(value) {
        return value === null || value === undefined ? "-" : Number(value).toFixed(2);
    }
    async function runEvaluation(form) {
        const formData = new FormData(form);
        state.evaluation.form = {
            startAt: formData.get("startAt"),
            endAt: formData.get("endAt"),
            limit: Number(formData.get("limit") || 50),
            includeLlmJudge: formData.get("includeLlmJudge") === "true"
        };
        state.evaluation.loading = true;
        renderEvaluations();
        try {
            state.evaluation.report = await DietApi.evaluate(state.evaluation.form);
        } catch (error) {
            showToast(error.message || "评估失败", "error");
        } finally {
            state.evaluation.loading = false;
            renderEvaluations();
        }
    }
    function saveModelSettings(form) {
        const formData = new FormData(form);
        try {
            state.settings.model = DietApi.saveModelSettings({
                enabled: formData.get("enabled") === "on",
                apiKey: formData.get("apiKey"),
                baseUrl: formData.get("baseUrl"),
                mainModel: formData.get("mainModel"),
                lightModel: formData.get("lightModel"),
                searchEnabled: formData.get("searchEnabled") === "on",
                searchApiKey: formData.get("searchApiKey"),
                searchBaseUrl: formData.get("searchBaseUrl"),
                searchModel: formData.get("searchModel")
            });
            state.home.searchCapabilities = null;
            const active = DietApi.hasConfiguredModel() || DietApi.hasConfiguredSearch();
            showToast(active ? "真实 API 设置已保存" : "设置已保存，当前为演示模式");
            renderSettings();
        } catch (error) {
            showToast("真实 API 设置保存失败", "error");
        }
    }
    function clearModelSettings() {
        try {
            state.settings.model = DietApi.clearModelSettings();
            state.home.searchCapabilities = null;
            showToast("真实 API 设置已清除，当前为演示模式");
            renderSettings();
        } catch (error) {
            showToast("真实 API 设置清除失败", "error");
        }
    }
    async function saveFeedback(button) {
        await guard(async () => {
            await DietApi.saveFeedback({
                sessionId: button.dataset.sessionId || state.chat.sessionId,
                itemId: Number(button.dataset.itemId),
                action: button.dataset.actionValue,
                rating: button.dataset.actionValue === "DISLIKE" ? 2 : 5,
                reason: ""
            });
        }, "反馈已记录");
    }
    function handleClick(event) {
        if (evaluationDashboard?.handleClick(event)) {
            return;
        }
        const dietTarget = event.target.closest("[data-diet-action]");
        if (dietTarget) { handleDietAction(dietTarget).catch(error => showToast(error.message, "error")); return; }
        const target = event.target.closest("[data-action]");
        if (!target) {
            return;
        }
        const action = target.dataset.action;
        if (action === "start-demo-chat") {
            startDemoChat(target);
        } else if (action === "toggle-theme-menu") {
            toggleThemeMenu();
        } else if (action === "toggle-developer-menu") {
            toggleDeveloperMenu();
        } else if (action === "set-theme") {
            setTheme(target.dataset.themeValue);
        } else if (action === "general-example") {
            state.home.generalPrompt = target.dataset.example || "";
            state.home.notice = "";
            renderGeneralHome();
            const input = document.querySelector("#generalDecisionForm textarea[name=prompt]");
            if (input) {
                input.dataset.demoDomain = target.dataset.demoDomain || "";
                input.dataset.demoPrompt = state.home.generalPrompt;
                input.focus();
            }
        } else if (action === "set-source") {
            state.chat.sourceMode = target.dataset.source;
            resetChat();
        } else if (action === "new-session") {
            resetChat();
        } else if (action === "quick-message") {
            const input = document.querySelector("#chatForm textarea[name=message]");
            if (input) {
                input.value = target.dataset.message;
                state.chat.draft = input.value;
                input.focus();
            }
        } else if (action === "feedback") {
            saveFeedback(target);
        } else if (action === "new-meal") {
            state.editingMeal = emptyMeal();
            renderPersonalMeals();
        } else if (action === "edit-meal") {
            editMeal(target.dataset.id);
        } else if (action === "delete-meal") {
            deleteMeal(target.dataset.id);
        } else if (action === "cancel-edit") {
            state.editingMeal = null;
            renderPersonalMeals();
        } else if (action === "select-trace") {
            selectTrace(target.dataset.traceId);
        } else if (action === "open-trace") {
            state.traces.filters.sessionId = "";
            navigate("/admin/traces");
            selectTrace(target.dataset.traceId);
        } else if (action === "demo-toggle-candidate") {
            toggleDemoCandidate(target.dataset.candidateId);
        } else if (action === "demo-complete") {
            completeDemoDecision();
        } else if (action === "demo-new") {
            const decision = ChoiceAgentDemo.createDecision("周末从上海出发，找一个两天一夜、轻松、人相对少的目的地", "travel");
            navigate(`/demo/decision/${encodeURIComponent(decision.id)}`);
        } else if (action === "demo-answer-question") {
            answerDemoQuestion(target.dataset.questionId, target.dataset.answer);
        } else if (action === "demo-add-constraint") {
            addDemoConstraintDraft();
        } else if (action === "demo-remove-constraint") {
            removeDemoConstraintDraft(target.dataset.draftId);
        } else if (action === "demo-reset-constraints") {
            resetDemoConstraintDrafts();
        } else if (action === "demo-clear-constraints") {
            clearDemoConstraintDrafts();
        } else if (action === "demo-confirm-constraints") {
            confirmDemoConstraintDrafts();
        } else if (action === "demo-edit-constraints") {
            editDemoConstraintDrafts();
        } else if (action === "demo-add-candidate") {
            addDemoCandidateDraft();
        } else if (action === "demo-remove-candidate") {
            removeDemoCandidateDraft(target.dataset.draftId);
        } else if (action === "demo-reset-candidates") {
            resetDemoCandidateDrafts();
        } else if (action === "demo-clear-candidates") {
            clearDemoCandidateDrafts();
        } else if (action === "demo-confirm-candidates") {
            confirmDemoCandidateDrafts();
        } else if (action === "demo-edit-candidates") {
            editDemoCandidateDrafts();
        } else if (action === "clear-model-settings") {
            clearModelSettings();
        } else if (action === "clear-outcome") {
            clearDecisionOutcome(target);
        } else if (action === "clear-outcome-review") {
            clearDecisionOutcomeReview(target);
        }
    }
    async function submitGeneralDecision(form) {
        const formData = new FormData(form);
        const prompt = String(formData.get("prompt") || "").trim();
        state.home.generalPrompt = prompt;
        if (!prompt) {
            state.home.notice = "先写下一个正在纠结的选择，再开始。";
            renderGeneralHome();
            return;
        }
        const input = form.querySelector("textarea[name=prompt]");
        const explicitDomain = input && input.dataset.demoPrompt === prompt ? input.dataset.demoDomain : "";
        const realtime = formData.get("realTimeSearch") === "on" && Boolean(state.home.searchCapabilities?.webSearchConfigured);
        const restore = setLoading(form.querySelector('button[type="submit"]'), "创建决策中...");
        state.home.progress = [];
        try {
            await conversation.startGeneral(prompt, ["diet","travel","shopping","generic"].includes(explicitDomain) ? explicitDomain : null, {searchMode: realtime ? "web" : "fixture", onProgress: (event) => {
                state.home.progress = [...state.home.progress, event].slice(-6);
                if (currentRoute() === "/") renderGeneralHome();
            }});
            state.home.notice = "";
            state.home.progress = [];
        } catch (error) {
            state.home.notice = error.message || "创建决策失败，请重试。";
            showToast(state.home.notice, "error");
        } finally {
            restore();
        }
    }
    function handleSubmit(event) {
        const form = event.target;
        if (evaluationDashboard?.handleSubmit(event)) {
            return;
        }
        if (form.id === "generalDecisionForm") {
            event.preventDefault();
            submitGeneralDecision(form);
        } else if (form.id === "chatForm") {
            event.preventDefault();
            submitChat(form);
        } else if (form.id === "mealForm") {
            event.preventDefault();
            if (!form.checkValidity()) {
                form.reportValidity();
                return;
            }
            saveMeal(form);
        } else if (form.id === "traceFilterForm") {
            event.preventDefault();
            searchTraces(form);
        } else if (form.id === "traceLabelForm") {
            event.preventDefault();
            saveTraceLabel(form);
        } else if (form.id === "evaluationForm") {
            event.preventDefault();
            runEvaluation(form);
        } else if (form.id === "modelSettingsForm") {
            event.preventDefault();
            saveModelSettings(form);
        } else if (form.id === "decisionOutcomeForm") {
            event.preventDefault();
            saveDecisionOutcome(form);
        } else if (form.id === "decisionOutcomeReviewForm") {
            event.preventDefault();
            saveDecisionOutcomeReview(form);
        } else if (form.id === "profileForm") {
            event.preventDefault();
            saveProfile(form);
        }
    }
    function closeThemeMenuOnOutsideClick(event) {
        if (!event.target.closest("#themeMenu")) {
            closeThemeMenu();
        }
        if (!event.target.closest("#developerMenu")) {
            closeDeveloperMenu();
        }
    }
    function handleChange(event) {
        const target = event.target.closest("[data-action]");
        if (!target) {
            return;
        }
        if (target.dataset.action === "demo-weight") {
            updateDemoWeight(target.dataset.key, Number(target.value));
        } else if (target.dataset.action === "real-search-toggle") {
            state.home.realtimeSearch = target.checked;
        } else if (target.dataset.action === "toggle-developer-mode") {
            setDeveloperMode(target.checked);
        } else if (evaluationDashboard?.handleChange(event)) {
            return;
        }
    }
    function initTheme() {
        applyTheme(state.theme);
        applyDeveloperMode();
    }
    function initUserField() {
        userIdInput.value = DietApi.setUserId(DietApi.getUserId());
        userIdInput.addEventListener("change", () => {
            DietApi.setUserId(userIdInput.value);
            state.home.loaded = false;
            state.personalMeals = [];
            state.publicMeals = [];
            state.history = { items: [], detail: null, loading: false, error: "" };
            state.profile = { data: null, loading: false, error: "" };
            state.traces.rows = [];
            state.traces.selected = null;
            Object.assign(state.evaluation, { dashboard: null, selectedRun: null, selectedCaseId: null, loading: false });
            state.chat.generation += 1;
            Object.assign(state.chat, {sessionId: null, decision: null, messages: defaultChatMessages(), initialized: false, sending: false, retry: null, error: "", draft: "", editFields: null, panelOpen: false, pendingPrompt: "", autoSending: false});
            showToast("用户 ID 已切换");
            render();
        });
    }
    window.addEventListener("hashchange", render);
    document.addEventListener("click", closeThemeMenuOnOutsideClick);
    document.addEventListener("click", handleClick);
    app.addEventListener("input", event => {
        if (event.target.id === "dietMessage") state.chat.draft = event.target.value;
        const key = event.target.dataset.generalField;
        if (key && state.chat.editFields) state.chat.editFields[key] = event.target.value === "" ? null : event.target.type === "number" ? Number(event.target.value) : event.target.value;
    });
    app.addEventListener("change", event => {
        const general = event.target.dataset.generalField;
        if (general && event.target.tagName === "SELECT" && state.chat.editFields) state.chat.editFields[general] = event.target.value || null;
        const key = event.target.dataset.dietField;
        if (key && state.chat.editFields) {
            const values = new Set(state.chat.editFields[key] || []);
            if (event.target.checked) values.add(event.target.value); else values.delete(event.target.value);
            state.chat.editFields[key] = [...values];
        }
    });
    document.addEventListener("keydown", event => {
        if (!state.chat.panelOpen || !document.getElementById("dietPanel")) return;
        if (event.key === "Escape") { event.preventDefault(); closeDietPanel(); }
        if (event.key === "Tab" && window.matchMedia("(max-width: 980px)").matches) {
            const panel = document.getElementById("dietPanel");
            const focusable = [...panel.querySelectorAll("button:not([disabled]), a, input:not([disabled]), select:not([disabled]), summary")].filter(el => el.getClientRects().length);
            const first = focusable[0], last = focusable[focusable.length - 1];
            if (event.shiftKey && (document.activeElement === first || document.activeElement === panel)) { event.preventDefault(); last?.focus(); }
            else if (!event.shiftKey && (document.activeElement === last || document.activeElement === panel)) { event.preventDefault(); first?.focus(); }
        }
    });
    app.addEventListener("change", handleChange);
    app.addEventListener("submit", handleSubmit);
    const conversation = window.createConversation({state, app, currentRoute, navigate, showToast, ensureSlotOptions, SLOT_LABELS, defaultChatMessages, renderMessage, renderMealCard, escapeHtml, genericRouteId, renderGeneralDetails});
    const evaluationDashboard = window.createEvaluationDashboard ? window.createEvaluationDashboard({state, app, navigate, showToast, escapeHtml, safeJson, statCard, formatScore}) : null;
    const {renderChat, closeDietPanel, sendDietCommand, handleDietAction, submitChat, resetChat, prepareChatFromHome} = conversation;
    initTheme();
    initUserField();
    if (!location.hash) {
        navigate("/");
    } else {
        render();
    }
})();
