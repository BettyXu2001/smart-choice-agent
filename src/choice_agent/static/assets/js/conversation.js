window.createConversation = function(deps) {
    const {state, app, currentRoute, navigate, showToast, ensureSlotOptions, SLOT_LABELS, defaultChatMessages, renderMessage, renderMealCard, escapeHtml, genericRouteId, renderGeneralDetails} = deps;
    function dietStorageKey() { return `choiceAgent.dietSession.${DietApi.getUserId()}`; }
    function rememberDietSession(sessionId) {
        try {
            if (sessionId) localStorage.setItem(dietStorageKey(), sessionId);
            else localStorage.removeItem(dietStorageKey());
        } catch (error) { showToast("浏览器未能保存会话入口，刷新恢复可能不可用", "error"); }
    }
    function syncDietState(decision) {
        if (isGeneral()) state.generic.decision = decision;
        state.chat.decision = decision;
        if (!decision) { state.chat.messages = defaultChatMessages(); return; }
        state.chat.sessionId = decision.sessionId;
        state.chat.sourceMode = decision.context?.sourceMode || state.chat.sourceMode;
        const turns = decision.domainState?.[isGeneral() ? "conversationTurns" : "dietTurns"] || [];
        let assistantIndex = 0;
        const assistantTurns = turns.slice();
        // New turns form a suffix; legacy messages are restored as text without invented cards.
        const assistantCount = (decision.messages || []).filter(m => m.role === "assistant").length;
        state.chat.messages = (decision.messages || []).map(m => {
            let turn = null;
            if (m.role === "assistant") {
                turn = assistantTurns[assistantIndex - (assistantCount - assistantTurns.length)];
                assistantIndex += 1;
            }
            return { role: m.role, text: m.content, meals: isGeneral() ? [] : turn?.displayBlocks || [], choices: isGeneral() ? turn?.displayBlocks || [] : [],
                traceId: turn?.traceId, sessionId: decision.sessionId };
        });
    }
    async function initializeDiet() {
        const generation = state.chat.generation;
        state.chat.initialized = true;
        state.chat.sending = true;
        renderChat();
        try {
            if (isGeneral()) {
                const decision = await DecisionApi.get(genericRouteId(currentRoute()));
                if (generation !== state.chat.generation) return;
                if (decision.domain === "diet") { state.chat.mode = "diet"; rememberDietSession(decision.sessionId); state.chat.initialized = false; navigate("/diet/chat"); return; }
                syncDietState(decision); return;
            }
            await ensureSlotOptions();
            if (generation !== state.chat.generation) return;
            let sessionId;
            try { sessionId = localStorage.getItem(dietStorageKey()); }
            catch (error) { showToast("无法读取浏览器会话入口", "error"); }
            if (sessionId) {
                const loaded = await DietApi.state(sessionId);
                if (generation !== state.chat.generation) return;
                state.chat.sessionId = loaded.sessionId;
                state.chat.sourceMode = loaded.sourceMode;
                syncDietState(loaded.decisionState);
            }
        } catch (error) {
            if (generation !== state.chat.generation) return;
            if (error.status === 404) rememberDietSession(null);
            state.chat.error = `恢复失败：${error.message}。可点击重新加载。`;
        } finally {
            if (generation === state.chat.generation) { state.chat.sending = false; renderChat(); }
        }
    }
    function dietFieldValues() {
        const d = state.chat.decision;
        if (isGeneral()) return Object.fromEntries(Object.entries(d?.domainState?.conversationFields || {}).map(([k,v]) => [k,v.value]));
        const fields = { ...(d?.domainState?.slots || {}) };
        fields.exclusions = (d?.constraints || []).filter(c => c.key === "diet_exclusion").flatMap(c => c.values);
        return fields;
    }
    function renderDietPanel() {
        if (isGeneral()) return renderGeneralPanel();
        const d = state.chat.decision;
        const labels = { ...SLOT_LABELS, exclusions: "忌口与排除" };
        const fields = dietFieldValues();
        const meta = d?.domainState?.dietFieldState || {};
        const busy = state.chat.sending || state.chat.retry ? "disabled" : "";
        const unresolved = Object.keys(labels).filter(k => (fields[k] || []).length && !meta[k]?.confirmed);
        const fieldRows = Object.entries(labels).map(([key, label]) => {
            const current = fields[key] || [];
            if (state.chat.editFields) {
                const options = key === "exclusions" ? [...new Set(Object.values(state.slotOptions || {}).flat())] : (state.slotOptions?.[key] || []);
                const all = [...new Set([...options, ...current])];
                return `<details class="diet-field-editor" ${["mealTime", "taste", "healthGoal"].includes(key) || current.length ? "open" : ""}>
                    <summary>${escapeHtml(label)}</summary><div class="chips">${all.map(value => `<label class="diet-option"><input type="checkbox" data-diet-field="${key}" value="${escapeHtml(value)}" ${(state.chat.editFields[key] || []).includes(value) ? "checked" : ""} ${busy}>${escapeHtml(value)}</label>`).join("") || '<span class="muted">暂无支持选项</span>'}</div>
                    <button type="button" class="btn ghost" data-diet-action="clear" data-field="${key}" ${busy}>清空</button></details>`;
            }
            if (!current.length && !["mealTime", "taste", "healthGoal"].includes(key)) return "";
            return `<div class="diet-field-row"><span>${escapeHtml(label)}</span><div><strong>${escapeHtml(current.join("、") || (meta[key]?.cleared ? "不限" : "尚未设置"))}</strong>${current.length ? `<small>${meta[key]?.confirmed ? "你已表达" : "待你确认"}</small>` : ""}</div></div>`;
        }).join("");
        const blocks = d?.domainState?.displayBlocks || [];
        const valid = d && d.status !== "clarifying" && !(d.riskFlags || []).length;
        const composition = valid ? d.composition?.items : null;
        let results = '<p class="muted">聊聊这顿想吃什么，推荐会出现在这里。</p>';
        if (d?.riskFlags?.length) results = '<p class="muted">这轮涉及健康风险，请先查看对话中的提示。</p>';
        else if (d?.status === "clarifying") results = '<p class="muted">补充关键信息后，我会更新推荐。</p>';
        else if (composition) results = composition.map(item => {
            const meal = blocks.find(b => String(b.id) === item.candidateId);
            return `<div class="diet-plan-slot"><h4>${escapeHtml(item.slot)}</h4>${meal ? renderMealCard(meal, {feedback: true, compact: true, sessionId: d.sessionId}) : `<p>${escapeHtml(item.label)}</p>`}</div>`;
        }).join("");
        else if (valid) results = blocks.length ? blocks.map((meal, i) => `<div><span class="diet-result-label">${i ? "也可以选" : "这次优先推荐"}</span>${renderMealCard(meal, {feedback: true, compact: true, sessionId: d.sessionId})}</div>`).join("") : '<p class="muted">暂无匹配餐食，可调整偏好或切换餐食库。不会自动放宽排除条件。</p>';
        const dialog = state.chat.panelOpen && window.matchMedia("(max-width: 980px)").matches;
        return `<aside ${dialog ? 'role="dialog" aria-modal="true"' : ""} id="dietPanel" class="diet-panel ${state.chat.panelOpen ? "is-open" : ""}" aria-label="当前决策" tabindex="-1">
            <div class="card-title"><div><span class="eyebrow">一起把选择想清楚</span><h3>当前决策</h3></div><button class="btn ghost diet-panel-close" data-diet-action="close" aria-label="关闭当前决策">关闭</button></div>
            <p class="diet-goal">${escapeHtml(d?.composition ? "安排这一天的三餐" : fields.mealTime?.length ? `${fields.mealTime.join("、")}吃什么` : d?.userGoal || "从这顿饭开始")}</p>
            <button class="btn ghost" data-diet-action="focus">在对话中修改需求</button>
            <section class="diet-panel-section"><div class="card-title"><h4>这顿的条件</h4>${!state.chat.editFields ? `<button class="btn soft" data-diet-action="edit" ${busy} ${!d || !state.slotOptions ? "disabled" : ""}>编辑条件</button>` : ""}</div>
                ${fieldRows}
                ${state.chat.editFields ? `<div class="button-row"><button class="btn primary" data-diet-action="save" ${busy}>保存并更新</button><button class="btn ghost" data-diet-action="cancel" ${busy}>取消</button></div>` : ""}
                ${unresolved.length && !state.chat.editFields ? `<div class="diet-pending"><strong>待确认理解</strong><p>${unresolved.map(k => escapeHtml(labels[k])).join("、")}来自模型理解或历史记录。</p><button class="btn soft" data-diet-action="confirm" ${busy}>确认这些条件</button></div>` : ""}
                ${(d?.domainState?.unverifiedRestrictions || []).length ? `<p class="diet-pending">你提到：${escapeHtml(d.domainState.unverifiedRestrictions.join("、"))}。当前餐食数据尚不能验证这些限制，请核对食材。</p>` : ""}
                <details><summary>忌口支持范围</summary><p class="muted">当前仅能排除餐食库中已有的标签，尚不能保证任意食材忌口已被过滤。</p></details>
            </section>
            ${d?.status === "clarifying" ? `<section class="diet-panel-section"><h4>还需补充</h4><p>${escapeHtml((d.clarifyingQuestions || []).join(" "))}</p><button class="btn soft" data-diet-action="focus">补充一下</button></section>` : ""}
            <section class="diet-panel-section" aria-busy="${state.chat.sending}"><div class="card-title"><h4>当前推荐</h4><span role="status">${state.chat.sending ? "更新中…" : ""}</span></div>${results}</section>
            <details class="diet-panel-section"><summary>餐食来源 · ${state.chat.sourceMode === "PERSONAL" ? "个人餐食库" : "公共餐食库"}</summary><div class="button-row"><button class="btn soft" data-diet-action="source" data-source="PERSONAL" ${busy}>个人餐食</button><button class="btn soft" data-diet-action="source" data-source="PUBLIC" ${busy}>公共餐食</button><a href="#/diet/meals/personal">管理餐食</a></div></details>
        </aside>`;
    }
    function renderChat() {
        if (!activeRoute()) return;
        if (!state.chat.initialized) { initializeDiet(); return; }
        const previousMessages = document.getElementById("messages");
        const scrollTop = previousMessages?.scrollTop || 0;
        const atBottom = !previousMessages || previousMessages.scrollHeight - previousMessages.scrollTop - previousMessages.clientHeight < 80;
        const detailsOpen = document.querySelector(".general-details")?.open;
        const panelScroll = document.getElementById("dietPanel")?.scrollTop || 0;
        const focused = document.activeElement;
        const focusId = focused?.id;
        const selection = focused?.selectionStart;
        app.innerHTML = `<section class="chat-layout diet-conversation">
            <div class="section chat-window"><div class="card-title"><div><span class="eyebrow">${isGeneral() ? "从想法，走到适合你的选择" : "每一顿，都更合心意"}</span><h2>${isGeneral() ? "一起把选择想清楚" : "今天想怎么吃？"}</h2></div><div class="inline-actions"><button id="dietPanelToggle" class="btn soft diet-panel-toggle" data-diet-action="open" aria-expanded="${state.chat.panelOpen}">当前决策</button><button class="btn ghost" data-action="new-session">新会话</button></div></div>
            <div id="messages" class="messages">${state.chat.messages.map(renderMessage).join("")}${state.chat.sending ? '<p class="muted" role="status">正在整理你的选择…</p>' : ""}</div>
            <div class="diet-composer-wrap">${state.chat.error ? `<div class="diet-error" role="alert">${escapeHtml(state.chat.error)}<button class="btn ghost" data-diet-action="${state.chat.retry ? "retry" : "reload"}" ${state.chat.sending ? "disabled" : ""}>${state.chat.retry ? "重试这次操作" : "重新加载"}</button></div>` : ""}
            <div class="chips diet-quick">${(isGeneral() ? ["更看重成本", "帮我比较一下", "刷新候选"] : ["晚餐想吃清淡一点", "帮我规划三餐", "换一批"]).map(text => `<button class="chip" data-action="quick-message" data-message="${text}">${text}</button>`).join("")}</div>
            <form id="chatForm" class="composer"><textarea id="dietMessage" name="message" aria-label="${isGeneral() ? "决策需求" : "饮食需求"}" placeholder="告诉我你的想法，也可以随时纠正我的理解…" required>${escapeHtml(state.chat.draft)}</textarea><button class="btn primary" ${state.chat.sending || state.chat.retry || (state.chat.error && !state.chat.sessionId) ? "disabled" : ""}>${state.chat.sending ? "整理中…" : "发送"}</button></form></div></div>
            ${state.chat.panelOpen ? '<button class="diet-panel-backdrop" data-diet-action="close" aria-label="关闭当前决策"></button>' : ""}${renderDietPanel()}</section>`;
        const messageBox = document.getElementById("messages");
        messageBox.scrollTop = atBottom ? messageBox.scrollHeight : scrollTop;
        document.getElementById("dietPanel").scrollTop = panelScroll;
        if (focusId) {
            const restored = document.getElementById(focusId);
            restored?.focus({preventScroll: true});
            if (typeof selection === "number" && restored?.setSelectionRange) restored.setSelectionRange(selection, selection);
        }
        if (state.chat.panelOpen && window.matchMedia("(max-width: 980px)").matches
                && !document.getElementById("dietPanel").contains(document.activeElement)) {
            document.getElementById("dietPanel").focus({preventScroll: true});
        }
        if (isGeneral()) { renderGeneralDetails(state.chat.decision); const details = document.querySelector(".general-details"); if (details) details.open = !!detailsOpen; }
        triggerPendingPrompt();
    }
    function closeDietPanel() {
        state.chat.panelOpen = false;
        renderChat();
        document.getElementById("dietPanelToggle")?.focus();
    }
    async function runDietOperation(operation) {
        if (state.chat.sending) return;
        const generation = state.chat.generation;
        state.chat.sending = true;
        state.chat.error = "";
        state.chat.retry = operation;
        renderChat();
        try {
            if (!isGeneral() && !state.chat.sessionId) {
                const created = await DietApi.createSession();
                if (generation !== state.chat.generation) return;
                state.chat.sessionId = created.sessionId;
                rememberDietSession(created.sessionId);
            }
            const response = isGeneral()
                ? operation.kind === "chat" ? await DecisionApi.message(state.chat.decision.decisionId, operation.body) : await DecisionApi.command(state.chat.decision.decisionId, operation.body)
                : operation.kind === "chat" ? await DietApi.chat({...operation.body, sessionId: state.chat.sessionId}) : await DietApi.command(state.chat.sessionId, operation.body);
            if (generation !== state.chat.generation) return;
            // Read current state also on idempotent replay, which may return an older receipt.
            const loaded = await loadCurrent();
            if (generation !== state.chat.generation) return;
            syncDietState(loaded.decisionState || response.decisionState);
            if (operation.kind === "chat" && state.chat.draft.trim() === operation.body.message) state.chat.draft = "";
            if (operation.kind === "command") state.chat.editFields = null;
            state.chat.retry = null;
            const suggestion = state.chat.decision?.domainState?.suggestedDomain;
            if (suggestion?.explicit) await startGeneral(suggestion.message, suggestion.domain);
        } catch (error) {
            if (generation !== state.chat.generation) return;
            state.chat.error = error.message || "请求失败，请重试。";
            if (error.status === 409) {
                try {
                    const loaded = await loadCurrent();
                    if (generation !== state.chat.generation) return;
                    syncDietState(loaded.decisionState);
                    state.chat.error = "条件已被另一处更新。已加载最新状态，你的草稿仍保留，请检查后重新提交。";
                    state.chat.retry = null;
                } catch (reloadError) { state.chat.error += `；读取最新状态失败：${reloadError.message}`; }
            } else if (error.status && error.status < 500) state.chat.retry = null;
        } finally {
            if (generation === state.chat.generation) { state.chat.sending = false; renderChat(); }
        }
    }
    function sendDietCommand(type, payload) {
        if (!state.chat.decision || state.chat.sending || state.chat.retry) return;
        state.chat.error = "";
        return runDietOperation({kind: "command", body: {commandId: crypto.randomUUID(), expectedRevision: state.chat.decision.revision, type, payload}});
    }
    async function handleDietAction(target) {
        const action = target.dataset.dietAction;
        if (action === "open") { state.chat.panelOpen = true; renderChat(); document.getElementById("dietPanel")?.focus(); }
        else if (action === "close") closeDietPanel();
        else if (action === "focus") { closeDietPanel(); document.getElementById("dietMessage")?.focus(); }
        else if (action === "reload") { state.chat.error = ""; state.chat.initialized = false; renderChat(); }
        else if (action === "retry") await runDietOperation(state.chat.retry);
        else if (!state.chat.sending && !state.chat.retry) {
            if (action === "edit") { state.chat.editFields = structuredClone(dietFieldValues()); renderChat(); }
            else if (action === "cancel") { state.chat.editFields = null; renderChat(); }
            else if (action === "clear") { state.chat.editFields[target.dataset.field] = isGeneral() ? null : []; renderChat(); }
            else if (action === "save") {
                const saved = dietFieldValues();
                const fields = Object.fromEntries(Object.entries(state.chat.editFields).filter(([k,v]) => JSON.stringify(v) !== JSON.stringify(saved[k] ?? (isGeneral() ? null : []))));
                if (!Object.keys(fields).length) { state.chat.editFields = null; renderChat(); return; }
                await sendDietCommand("update_fields", {fields});
            } else if (action === "confirm") {
                const meta = state.chat.decision.domainState?.[isGeneral() ? "conversationFields" : "dietFieldState"] || {};
                const fields = Object.entries(dietFieldValues()).filter(([k,v]) => (isGeneral() ? v != null : v.length) && !meta[k]?.confirmed).map(([k]) => k);
                await sendDietCommand("confirm_fields", {fields});
            } else if (action === "switch") {
                const suggestion = state.chat.decision.domainState.suggestedDomain;
                await startGeneral(suggestion.message, suggestion.domain);
            } else if (action === "source") {
                if (state.chat.decision) await sendDietCommand("set_source", {sourceMode: target.dataset.source});
                else { state.chat.sourceMode = target.dataset.source; renderChat(); }
            }
        }
    }
    async function sendChatMessage(message) {
        const text = String(message || "").trim();
        if (!text || state.chat.sending || state.chat.retry) return;
        state.chat.draft = text;
        await runDietOperation({kind: "chat", body: {requestId: crypto.randomUUID(), message: text,
            sourceMode: state.chat.sourceMode, expectedRevision: state.chat.decision?.revision || 0, context: {}}});
    }
    async function submitChat(form) {
        await sendChatMessage(form.elements.message.value);
    }
    function resetChat() {
        const general = isGeneral();
        state.chat.generation += 1;
        Object.assign(state.chat, {sessionId: null, decision: null, draft: "", editFields: null,
            pendingPrompt: "", autoSending: false, sending: false, retry: null, error: "",
            panelOpen: false, initialized: true, messages: defaultChatMessages()});
        if (general) { navigate("/"); return; }
        rememberDietSession(null);
        renderChat();
    }
    function prepareChatFromHome(prompt) {
        state.chat.mode = "diet";
        state.chat.routeId = null;
        resetChat();
        state.chat.sourceMode = "PERSONAL";
        state.chat.pendingPrompt = prompt;
        if (!state.slotOptions) ensureSlotOptions().then(() => renderChat()).catch(error => {
            state.chat.error = error.message; renderChat();
        });
    }
    function triggerPendingPrompt() {
        if (!state.chat.pendingPrompt || state.chat.autoSending || state.chat.sending || !activeRoute()) {
            return;
        }
        const prompt = state.chat.pendingPrompt;
        state.chat.pendingPrompt = "";
        state.chat.autoSending = true;
        window.setTimeout(async () => {
            try {
                await sendChatMessage(prompt);
            } finally {
                state.chat.autoSending = false;
            }
        }, 0);
    }
    async function renderPersonalMeals() {
        if (!state.slotOptions) {
            app.innerHTML = `<section class="section"><div class="empty">标签字典加载中...</div></section>`;
            await ensureSlotOptions();
            if (currentRoute() !== "/diet/meals/personal") {
                return;
            }
        }
        await ensurePersonalMeals();
        if (currentRoute() !== "/diet/meals/personal") {
            return;
        }
        app.innerHTML = `
            <section class="split">
                <div class="section">
                    <div class="card-title">
                        <div>
                            <h2>个人餐食</h2>
                            <p>维护常吃餐食，决策时会优先参考这些数据。</p>
                        </div>
                        <button class="btn primary" data-action="new-meal">新增餐食</button>
                    </div>
                    <div id="personalMealList">${renderMealList(state.personalMeals, { editable: true })}</div>
                </div>
                <aside class="section">
                    ${renderMealForm()}
                </aside>
            </section>
        `;
    }
    function isGeneral() { return state.chat.mode === "general"; }
    function activeRoute() { return isGeneral() ? currentRoute() === `/decisions/${state.chat.routeId}` : currentRoute() === "/diet/chat"; }
    function loadCurrent() { return isGeneral() ? DecisionApi.get(state.chat.decision.decisionId).then(decisionState => ({decisionState})) : DietApi.state(state.chat.sessionId); }
    function enter(mode, id = null) {
        if (state.chat.mode !== mode || state.chat.routeId !== id) {
            state.chat.generation += 1;
            Object.assign(state.chat, {mode, routeId:id, initialized:false, sessionId:null, decision:null, messages:[], draft:"", editFields:null, retry:null, sending:false, error:"", panelOpen:false});
        }
        renderChat();
    }
    async function startGeneral(message, domain, options = {}) {
        if (state.home.creating) return;
        const generation = state.chat.generation;
        const originRoute = currentRoute();
        const user = DietApi.getUserId();
        state.home.creating = true;
        try {
            const resolution = await DecisionApi.resolve({message, domain:domain || null});
            if (generation !== state.chat.generation || user !== DietApi.getUserId() || originRoute !== currentRoute()) return;
            if (resolution.domain === "diet") { prepareChatFromHome(message); navigate("/diet/chat"); return; }
            const key = JSON.stringify({message,domain:resolution.domain,user,context:options.context || {}});
            const request = state.home.createRetry?.key === key ? state.home.createRetry : {key,body:{message,domain:domain || null,context:options.context || {},requestId:options.requestId || crypto.randomUUID()}};
            state.home.createRetry = request;
            const response = await DecisionApi.create(request.body);
            if (generation !== state.chat.generation || user !== DietApi.getUserId() || originRoute !== currentRoute()) return;
            state.home.createRetry = null;
            state.chat.generation += 1;
            Object.assign(state.chat,{mode:"general",routeId:response.decisionState.decisionId,initialized:true,sending:false,retry:null,error:"",editFields:null,draft:"",panelOpen:false});
            syncDietState(response.decisionState);
            navigate(`/decisions/${response.decisionState.decisionId}`);
            renderChat();
        } finally { state.home.creating = false; }
    }
    function renderGeneralPanel() {
        const d = state.chat.decision;
        const busy = state.chat.sending || state.chat.retry ? "disabled" : "";
        const all = d?.domainState?.conversationFields || {};
        const labels = {travel:"旅行",shopping:"购物",generic:"通用"};
        const displayValue = v => ({laptop:"电脑 / 笔记本",phone:"手机",headphones:"耳机",appliance:"家电"}[v] || v);
        const goal = d?.domain === "shopping" ? `选择适合你的${displayValue(all.category?.value) || "商品"}` : d?.domain === "travel" ? `${all.departure?.value || "待定地点"}出发${all.days?.value ? ` · ${all.days.value} 天旅行` : "的旅行"}` : all.target?.value || d?.userGoal;
        const rows = Object.entries(all).filter(([key,field]) => !["background","weeklyHours"].includes(key) || field.value != null || /学习|课程|编程/.test(d?.userGoal || "")).map(([key, field]) => {
            const value = state.chat.editFields ? state.chat.editFields[key] : field.value;
            const input = key === "category" ? `<select id="general-${key}" data-general-field="${key}" ${busy}><option value="">尚未设置</option>${Object.entries({laptop:"电脑 / 笔记本",phone:"手机",headphones:"耳机",appliance:"家电"}).map(([v,l]) => `<option value="${v}" ${value === v ? "selected" : ""}>${l}</option>`).join("")}</select>` : `<input id="general-${key}" data-general-field="${key}" type="${field.type === "number" ? "number" : "text"}" ${field.type === "number" ? 'min="0.01" step="any"' : ''} value="${escapeHtml(value ?? "")}" ${busy}>`;
            return `<div class="diet-field-row"><label for="general-${key}">${escapeHtml(field.label)}${field.unit ? `（${escapeHtml(field.unit)}）` : ""}</label><div>${state.chat.editFields ? input : `<strong>${escapeHtml(displayValue(value) ?? (field.cleared ? "不限 / 已清空" : "尚未设置"))}</strong>`}<small>${field.value != null ? (field.confirmed ? "你已表达" : "待你确认") : ""}</small><small>${escapeHtml(field.impact)}</small></div></div>`;
        }).join("");
        const pending = Object.values(all).some(f => f.value != null && !f.confirmed);
        const suggestion = d?.domainState?.suggestedDomain;
        const source = d?.domainState?.source;
        const assistance = d?.domainState?.assistance || {};
        const analysis = assistance.analysis;
        const blocks = d?.status === "clarifying" ? [] : d?.domainState?.displayBlocks || [];
        const dialog = state.chat.panelOpen && window.matchMedia("(max-width: 980px)").matches;
        return `<aside id="dietPanel" class="diet-panel ${state.chat.panelOpen ? "is-open" : ""}" tabindex="-1" aria-label="当前决策" ${dialog ? 'role="dialog" aria-modal="true"' : ''}>
            <div class="card-title"><div><span class="eyebrow">${labels[d?.domain] || "通用"}决策${d?.context?.demoMode ? " · 演示数据" : ""}</span><h3>当前决策</h3></div><button class="btn ghost diet-panel-close" data-diet-action="close">关闭</button></div>
            <p class="diet-goal">${escapeHtml(goal || "一起想清楚这次选择")}</p>
            ${d?.context?.demoMode ? '<p class="muted">正在体验演示数据，候选说明与属性不代表真实情况。<a href="#/demo">换个示例</a></p>' : ""}
            ${suggestion ? `<section class="diet-pending"><p>这次想切换到${labels[suggestion.domain] || "饮食"}场景吗？会新建会话，保留当前选择。</p><button class="btn soft" data-diet-action="switch" ${busy}>新建${labels[suggestion.domain] || "饮食"}决策</button></section>` : ""}
            ${analysis ? `<section class="diet-panel-section"><span class="eyebrow">${analysis.mode === "model" ? "模型辅助" : analysis.mode === "rules_fallback" ? "规则辅助 · 模型暂不可用" : "规则辅助"}</span><h4>${analysis.hypothetical ? "假设分析 · 未修改当前选择" : "当前取舍"}</h4><p>${escapeHtml(analysis.summary)}</p>${analysis.changes?.length ? `<details open><summary>这轮更新了什么</summary>${analysis.changes.map(t=>`<p>${escapeHtml(t)}</p>`).join("")}</details>` : ""}${[["reasons","依据"],["tradeoffs","需要接受的代价"]].map(([key,label])=>analysis[key]?.length ? `<details open><summary>${label}</summary>${analysis[key].map(r=>`<p>${escapeHtml(r.text)}<small>${escapeHtml(analysis.sources?.[r.sourceId]?.source === "demo" || d.context?.demoMode ? "依据演示数据" : "依据已有候选信息")}</small></p>`).join("")}</details>` : "").join("")}${analysis.question ? `<p><strong>还需想清楚：</strong>${escapeHtml(analysis.question)}</p>` : ""}</section>` : ""}
            ${assistance.warning ? `<p class="diet-error">${escapeHtml(assistance.warning)}</p>` : ""}
            <section class="diet-panel-section"><div class="card-title"><h4>我理解的条件</h4>${!state.chat.editFields ? `<button class="btn soft" data-diet-action="edit" ${busy} ${!d ? "disabled" : ""}>编辑条件</button>` : ""}</div>${rows}
            ${state.chat.editFields ? `<div class="button-row"><button class="btn primary" data-diet-action="save" ${busy}>保存并更新</button><button class="btn ghost" data-diet-action="cancel" ${busy}>取消</button></div>` : pending ? `<button class="btn soft" data-diet-action="confirm" ${busy}>确认这些条件</button>` : ""}</section>
            ${d?.status === "clarifying" ? `<section class="diet-panel-section"><h4>还需补充</h4><p>${escapeHtml((d.clarifyingQuestions || []).join(" "))}</p><button class="btn soft" data-diet-action="focus">补充一下</button></section>` : ""}
            <section class="diet-panel-section" aria-busy="${state.chat.sending}"><h4>当前比较 ${state.chat.sending ? "· 更新中…" : ""}</h4><p>${escapeHtml(d?.recommendation?.summary || "随着对话补充，我会更新这里的比较。")}</p>${blocks.map(b => `<article class="general-choice"><strong>${escapeHtml(b.name)}</strong><p>${escapeHtml(b.summary || "")}</p>${(b.facts || []).map(f=>`<p class="muted">你补充：${escapeHtml(f.text)}</p>`).join("")}</article>`).join("")}</section>
            <p class="muted">${escapeHtml(source?.label || "等待补充信息")}${source?.mode === "fixture" ? " · 离线模拟数据，未核验实际价格、出发路线和行程费用" : source?.mode === "manual" ? " · 由你提供，未经外部核实" : ""}</p>
            ${d?.domainState?.interpretationWarning ? `<p class="diet-error">${escapeHtml(d.domainState.interpretationWarning)}</p>` : ""}
            <details class="diet-panel-section general-details"><summary>详细比较与候选编辑</summary><div id="generalDetails"></div></details>
        </aside>`;
    }

    return {enter, renderChat, closeDietPanel, sendDietCommand, handleDietAction, submitChat, resetChat, prepareChatFromHome, startGeneral};
};
