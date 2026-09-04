(function () {
    "use strict";
    const app = document.getElementById("app");
    const toast = document.getElementById("toast");
    const userIdInput = document.getElementById("userIdInput");
    const THEME_STORAGE_KEY = "choiceAgentTheme";
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
        settings: { model: DietApi.getModelSettings() },
        home: { loaded: false, personalCount: 0, publicCount: 0, generalPrompt: "", notice: "" },
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
            form: defaultRangeForm()
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
    function applyTheme(theme) {
        const nextTheme = isKnownTheme(theme) ? theme : "mint";
        document.body.dataset.theme = nextTheme;
        document.querySelectorAll('[data-action="set-theme"]').forEach((button) => {
            const active = button.dataset.themeValue === nextTheme;
            button.setAttribute("aria-checked", active ? "true" : "false");
        });
    }
    function closeThemeMenu() {
        const menu = document.querySelector(".theme-menu-list");
        const button = document.getElementById("themeMenuButton");
        if (menu) {
            menu.classList.add("hidden");
        }
        if (button) {
            button.setAttribute("aria-expanded", "false");
        }
    }
    function toggleThemeMenu() {
        const menu = document.querySelector(".theme-menu-list");
        const button = document.getElementById("themeMenuButton");
        if (!menu || !button) {
            return;
        }
        const willOpen = menu.classList.contains("hidden");
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
            navRoute = "/data";
        } else if (route === "/diet/chat" || route.startsWith("/demo") || route.startsWith("/decisions/")) {
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
        } else if (route === "/admin/traces") {
            renderTraces();
        } else if (route === "/admin/evaluations") {
            renderEvaluations();
        } else if (route === "/settings") {
            renderSettings();
        } else {
            navigate("/");
        }
        app.focus({ preventScroll: true });
    }
    function renderGeneralHome() {
        const modelConfigured = DietApi.hasConfiguredModel();
        const modeTitle = modelConfigured ? "模型配置已启用" : "演示模式";
        const modeDescription = modelConfigured
            ? "对话会使用已配置的模型辅助理解；你可以随时查看和修正当前条件。"
            : "当前使用规则理解和离线示例。直接说出你的选择，我会整理条件和候选；示例价格和行程尚未核实。";
        const examples = [
            { text: "周末想出去走走，但不知道去哪里", domain: "travel" },
            { text: "A 公司和 B 公司两个 Offer 各有优缺点，应该怎么选", domain: "career" },
            { text: "想系统学 AI Agent，但不知道先选哪条学习路径", domain: "learning" },
            { text: "想换一台适合通勤的轻便电脑", domain: "shopping" },
            { text: "今晚不知道吃什么，想要清淡一点", domain: "diet" }
        ];
        app.innerHTML = `
            <section class="hero general-home">
                <div class="hero-panel decision-entry">
                    <span class="badge">Choice Agent</span>
                    <h1>把选择题想清楚</h1>
                    <p>说出你正在纠结的选择。系统会先理解目标和约束，再追问关键条件、比较取舍，并把能直接处理的场景带入对应决策能力。</p>
                    <div class="mode-banner" data-mode="${modelConfigured ? "model" : "demo"}">
                        <span>${escapeHtml(modeTitle)}</span>
                        <p>${escapeHtml(modeDescription)}</p>
                        <a class="btn ghost" href="#/settings">配置 API</a>
                    </div>
                    <form id="generalDecisionForm" class="decision-entry-form">
                        <label class="field full">
                            <span>你最近在纠结什么？</span>
                            <textarea name="prompt" placeholder="比如：今晚不知道吃什么，想要清淡一点。">${escapeHtml(state.home.generalPrompt)}</textarea>
                        </label>
                        <div class="button-row">
                            <button class="btn primary" type="submit">开始决策</button>
                        </div>
                    </form>
                    ${state.home.notice ? `<div class="mode-notice">${escapeHtml(state.home.notice)}</div>` : ""}
                    <div class="example-grid" aria-label="决策示例">
                        ${examples.map((example) => `<button class="example-button" type="button" data-action="general-example" data-example="${escapeHtml(example.text)}" data-demo-domain="${escapeHtml(example.domain)}">${escapeHtml(example.text)}</button>`).join("")}
                    </div>
                </div>
                <aside class="grid stats workflow-stats">
                    ${statCard("描述选择", "一句话开始", "把目标、候选和纠结点先放到同一个入口")}
                    ${statCard("澄清条件", "补关键约束", "信息不足时先追问，不急着给结论")}
                    ${statCard("比较取舍", "解释建议", "展示推荐理由、替代项和下一步")}
                    ${statCard("通用决策", "旅行 / 购物 / 自定义", "服务端决策工作台")}
                </aside>
            </section>
            <section class="grid three decision-flow" style="margin-top: 18px;">
                ${featureCard("描述选择", "输入正在纠结的问题，不需要先判断该进入哪个能力。", "#/")}
                ${featureCard("澄清条件", "系统围绕目标、约束、偏好和场景补齐关键上下文。", "#/")}
                ${featureCard("比较取舍", "对候选进行排序、解释理由，并保留可追踪的决策过程。", "#/")}
                ${featureCard("通用 Demo", "用演示数据体验同一套对话与可编辑结果侧栏。", "#/demo")}
            </section>
            <section class="developer-links" aria-label="开发者入口">
                <span class="muted">开发者入口</span>
                <a class="btn ghost" href="#/admin/traces">Trace</a>
                <a class="btn ghost" href="#/admin/evaluations">评估</a>
            </section>
        `;
    }
    function renderSettings() {
        const settings = DietApi.getModelSettings();
        state.settings.model = settings;
        const configured = settings.enabled && Boolean(settings.apiKey);
        app.innerHTML = `
            <section class="settings-layout">
                <div class="section settings-panel">
                    <div class="card-title">
                        <div>
                            <h2>设置</h2>
                            <p>浏览器模型配置</p>
                        </div>
                        <span class="settings-status" data-mode="${configured ? "model" : "demo"}">${configured ? "模型模式" : "演示模式"}</span>
                    </div>
                    <form id="modelSettingsForm" class="settings-form">
                        <label class="toggle-row">
                            <input type="checkbox" name="enabled" ${settings.enabled ? "checked" : ""}>
                            <span>启用浏览器模型配置</span>
                        </label>
                        <label class="field full secret-field">
                            <span>API Key</span>
                            <input type="password" name="apiKey" value="${escapeHtml(settings.apiKey)}" autocomplete="off" placeholder="sk-...">
                        </label>
                        <label class="field full">
                            <span>Base URL</span>
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
                        <p class="field-hint">API Key 只保存在当前浏览器的 localStorage 中，请不要在共享设备上保存个人密钥。前端设置会随饮食聊天和评估请求通过请求头发送给本地后端，不会写入请求 body。</p>
                        <div class="button-row">
                            <button class="btn primary" type="submit">保存设置</button>
                            <button class="btn ghost" type="button" data-action="clear-model-settings">清除设置</button>
                        </div>
                    </form>
                </div>
                <aside class="grid settings-side">
                    ${statCard("当前模式", configured ? "模型模式" : "演示模式", configured ? "饮食助手会尝试调用你配置的模型。" : "本地规则与离线数据")}
                    ${statCard("通用决策", "服务端工作台", "旅行、购物与自定义候选")}
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
                    <p>这是 Choice Agent V2 当前已增强的决策场景。你可以维护个人餐食库，也可以从公共餐食库开始；助手会根据时间、心情、场景、健康目标、口味和便利程度给出推荐，并在信息不足时主动追问。</p>
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

    function renderGenericDecision(route) { conversation.enter("general", genericRouteId(route)); }

    function renderGeneralDetails(decision) {
        const container = document.getElementById("generalDetails");
        if (!container || !decision) return;
        const labels = { diet: "饮食决策", travel: "旅行决策", shopping: "购物决策", generic: "通用决策" };
        const domainLabel = labels[decision.domain] || decision.domain;
        const activeCandidates = decision.candidates || [];
        const excludedIds = new Set(decision.excludedCandidates || []);
        const pool = decision.domainState?.candidatePool || [];
        const excludedCandidates = pool.filter((item) => excludedIds.has(item.candidateId) && !activeCandidates.some((active) => active.candidateId === item.candidateId));
        const candidates = [...activeCandidates, ...excludedCandidates];
        const recommendation = decision.recommendation || {};
        const source = decision.domainState?.source || {};
        container.innerHTML = `
            <section class="demo-workbench unified-workbench">
                <header class="demo-header">
                    <div>
                        <span class="badge demo-badge">${escapeHtml(domainLabel)}</span>
                        <h2>${escapeHtml(decision.userGoal || "待补充目标")}</h2>
                        <p>${escapeHtml(decision.intentKey || decision.status || "")} · Revision ${escapeHtml(decision.revision)}</p>
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
                        <div class="card-title"><div><h3>候选比较</h3><p>${activeCandidates.length} 个可用</p></div></div>
                        <div class="demo-candidates">${candidates.map((candidate) => renderGenericCandidate(candidate, decision)).join("") || `<div class="empty">暂无候选</div>`}</div>
                        ${decision.domain !== "diet" ? `<form id="genericCandidateForm" class="inline-form">
                            <input name="name" required placeholder="候选名称">
                            <input name="summary" placeholder="简短说明">
                            ${(decision.criteria || []).map((item) => `<label class="field"><span>${escapeHtml(item.label)}</span><input type="number" step="any" name="attribute:${escapeHtml(item.key)}" placeholder="${escapeHtml(item.unit || item.label)}"></label>`).join("")}
                            <button class="btn ghost" type="submit">添加候选</button>
                        </form>` : ""}
                        <div class="demo-recommendation">
                            <span class="badge demo-badge">推荐结论</span>
                            <h4>${escapeHtml(recommendation.primaryCandidateId || "待定")}</h4>
                            <p>${escapeHtml(recommendation.summary || "暂无结论")}</p>
                            <div class="demo-list">
                                ${(recommendation.reasons || []).map((item) => `<div><span>${escapeHtml(item.text)}</span></div>`).join("")}
                                ${(recommendation.tradeoffs || []).map((item) => `<div><span>${escapeHtml(item)}</span></div>`).join("")}
                            </div>
                        </div>
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

    function renderGenericCandidate(candidate, decision) {
        const attrs = Object.entries(candidate.attributes || {});
        const excluded = (decision.excludedCandidates || []).includes(candidate.candidateId);
        const breakdown = candidate.scoreBreakdown || [];
        const evidence = candidate.evidence || [];
        return `
            <article class="demo-candidate${excluded ? " is-eliminated" : ""}">
                <div class="demo-candidate-head">
                    <div><h3>${escapeHtml(candidate.name)}</h3><p>${escapeHtml(candidate.summary || "")}</p></div>
                    <div class="score-block"><span class="score">${decision.domainState?.qualitative || !breakdown.some(p => p.rawValue != null) ? "待比较" : Math.round(Number(candidate.score || 0) * 100) + "%"}</span><button class="btn ghost" type="button" data-candidate-action="${excluded ? "restore_candidate" : "exclude_candidate"}" data-candidate-id="${escapeHtml(candidate.candidateId)}">${excluded ? "恢复" : "排除"}</button></div>
                </div>
                <div class="attribute-grid">${attrs.map(([key, value]) => `<span><strong>${escapeHtml(key)}</strong>${escapeHtml(Array.isArray(value) ? value.join("、") : value)}</span>`).join("")}</div>
                ${breakdown.length ? `<div class="demo-list">${breakdown.map((item) => `<div><strong>${escapeHtml(item.criterionKey)}</strong><span>${Math.round(Number(item.normalizedScore || 0))}</span></div>`).join("")}</div>` : ""}
                ${candidate.origin === "manual" ? `<form class="candidate-edit inline-form" data-candidate-id="${escapeHtml(candidate.candidateId)}"><label>候选说明<input name="summary" value="${escapeHtml(candidate.summary || "")}" placeholder="优点与顾虑"></label><button class="btn ghost">保存说明</button></form>` : ""}
                ${evidence.length ? `<div class="demo-list">${evidence.map((item) => `<div><strong>${escapeHtml(item.verificationStatus || "unverified")}</strong><span>${/^https?:\/\//i.test(item.sourceUrl || "") && item.verificationStatus === "verified" ? `<a href="${escapeHtml(item.sourceUrl)}" target="_blank" rel="noreferrer">${escapeHtml(item.sourceTitle)}</a>` : escapeHtml(item.sourceTitle)}${item.freshness ? ` · ${escapeHtml(item.freshness)}` : ""}</span></div>`).join("")}</div>` : ""}
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
                            <h2>Trace 调试</h2>
                            <p>按时间范围或会话查询请求链路，查看意图修正、槽位和推荐事件。</p>
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
                    ${selected ? renderTraceDetail(selected) : `<div class="empty">选择一条 Trace 查看详情和标注表单。</div>`}
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
                <details open>
                    <summary>Trace JSON</summary>
                    <pre class="json-box">${escapeHtml(safeJson(trace.traceJson))}</pre>
                </details>
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
                lightModel: formData.get("lightModel")
            });
            showToast(DietApi.hasConfiguredModel() ? "模型设置已保存" : "设置已保存，当前为演示模式");
            renderSettings();
        } catch (error) {
            showToast("模型设置保存失败", "error");
        }
    }
    function clearModelSettings() {
        try {
            state.settings.model = DietApi.clearModelSettings();
            showToast("模型设置已清除，当前为演示模式");
            renderSettings();
        } catch (error) {
            showToast("模型设置清除失败", "error");
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
        const dietTarget = event.target.closest("[data-diet-action]");
        if (dietTarget) { handleDietAction(dietTarget).catch(error => showToast(error.message, "error")); return; }
        const target = event.target.closest("[data-action]");
        if (!target) {
            return;
        }
        const action = target.dataset.action;
        if (action === "start-demo-chat") {
            startDemoChat(target);
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
        }
    }
    async function submitGeneralDecision(form) {
        const prompt = String(new FormData(form).get("prompt") || "").trim();
        state.home.generalPrompt = prompt;
        if (!prompt) {
            state.home.notice = "先写下一个正在纠结的选择，再开始。";
            renderGeneralHome();
            return;
        }
        const input = form.querySelector("textarea[name=prompt]");
        const explicitDomain = input && input.dataset.demoPrompt === prompt ? input.dataset.demoDomain : "";
        const restore = setLoading(form.querySelector('button[type="submit"]'), "创建决策中...");
        try {
            await conversation.startGeneral(prompt, ["diet","travel","shopping","generic"].includes(explicitDomain) ? explicitDomain : null);
            state.home.notice = "";
        } catch (error) {
            state.home.notice = error.message || "创建决策失败，请重试。";
            showToast(state.home.notice, "error");
        } finally {
            restore();
        }
    }
    function handleSubmit(event) {
        const form = event.target;
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
        }
    }
    function closeThemeMenuOnOutsideClick(event) {
        if (!event.target.closest(".theme-menu")) {
            closeThemeMenu();
        }
    }
    function handleChange(event) {
        const target = event.target.closest("[data-action]");
        if (!target) {
            return;
        }
        if (target.dataset.action === "demo-weight") {
            updateDemoWeight(target.dataset.key, Number(target.value));
        }
    }
    function initTheme() {
        applyTheme(state.theme);
    }
    function initUserField() {
        userIdInput.value = DietApi.setUserId(DietApi.getUserId());
        userIdInput.addEventListener("change", () => {
            DietApi.setUserId(userIdInput.value);
            state.home.loaded = false;
            state.personalMeals = [];
            state.publicMeals = [];
            state.traces.rows = [];
            state.traces.selected = null;
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
    const {renderChat, closeDietPanel, sendDietCommand, handleDietAction, submitChat, resetChat, prepareChatFromHome} = conversation;
    initTheme();
    initUserField();
    if (!location.hash) {
        navigate("/");
    } else {
        render();
    }
})();
