(function () {
    "use strict";

    const API_BASE = "/api/v1/diet";
    const DECISION_API_BASE = "/api/v1/decisions";
    const USER_ID_KEY = "diet.userId";
    const MODEL_SETTINGS_KEY = "choiceAgentModelSettings";
    const DEFAULT_MODEL_SETTINGS = {
        enabled: false,
        apiKey: "",
        baseUrl: "https://api.openai.com/v1",
        mainModel: "gpt-5",
        lightModel: "gpt-5-mini"
    };

    function getUserId() {
        return localStorage.getItem(USER_ID_KEY) || "1";
    }

    function setUserId(userId) {
        const normalized = String(userId || "1").trim() || "1";
        localStorage.setItem(USER_ID_KEY, normalized);
        return normalized;
    }

    function normalizeModelSettings(settings) {
        const source = settings && typeof settings === "object" ? settings : {};
        return {
            enabled: source.enabled === true,
            apiKey: String(source.apiKey || "").trim(),
            baseUrl: String(source.baseUrl || DEFAULT_MODEL_SETTINGS.baseUrl).trim() || DEFAULT_MODEL_SETTINGS.baseUrl,
            mainModel: String(source.mainModel || DEFAULT_MODEL_SETTINGS.mainModel).trim() || DEFAULT_MODEL_SETTINGS.mainModel,
            lightModel: String(source.lightModel || DEFAULT_MODEL_SETTINGS.lightModel).trim() || DEFAULT_MODEL_SETTINGS.lightModel
        };
    }

    function getModelSettings() {
        try {
            const raw = localStorage.getItem(MODEL_SETTINGS_KEY);
            if (!raw) {
                return { ...DEFAULT_MODEL_SETTINGS };
            }
            return normalizeModelSettings(JSON.parse(raw));
        } catch (error) {
            return { ...DEFAULT_MODEL_SETTINGS };
        }
    }

    function saveModelSettings(settings) {
        const normalized = normalizeModelSettings(settings);
        localStorage.setItem(MODEL_SETTINGS_KEY, JSON.stringify(normalized));
        return normalized;
    }

    function clearModelSettings() {
        localStorage.removeItem(MODEL_SETTINGS_KEY);
        return { ...DEFAULT_MODEL_SETTINGS };
    }

    function hasConfiguredModel() {
        const settings = getModelSettings();
        return settings.enabled && Boolean(settings.apiKey);
    }

    function attachModelHeaders(headers) {
        const settings = getModelSettings();
        if (!settings.enabled || !settings.apiKey) {
            return;
        }
        headers.set("X-Choice-Agent-Model-Enabled", "true");
        headers.set("X-Choice-Agent-Model-Api-Key", settings.apiKey);
        headers.set("X-Choice-Agent-Model-Base-Url", settings.baseUrl);
        headers.set("X-Choice-Agent-Main-Model", settings.mainModel);
        headers.set("X-Choice-Agent-Light-Model", settings.lightModel);
    }

    async function request(baseUrl, path, options) {
        const config = options || {};
        const headers = new Headers(config.headers || {});
        headers.set("X-User-Id", getUserId());
        attachModelHeaders(headers);

        if (config.body !== undefined && !(config.body instanceof FormData)) {
            headers.set("Content-Type", "application/json");
        }

        const response = await fetch(`${baseUrl}${path}`, {
            ...config,
            headers,
            body: config.body === undefined || config.body instanceof FormData
                ? config.body
                : JSON.stringify(config.body)
        });

        if (!response.ok) {
            const detail = await readError(response);
            const error = new Error(detail || `请求失败：${response.status}`);
            error.status = response.status;
            error.detail = detail;
            throw error;
        }

        if (response.status === 204) {
            return null;
        }

        const text = await response.text();
        if (!text) {
            return null;
        }

        try {
            return JSON.parse(text);
        } catch (error) {
            return text;
        }
    }

    async function dietRequest(path, options) {
        return request(API_BASE, path, options);
    }

    async function decisionRequest(path, options) {
        return request(DECISION_API_BASE, path, options);
    }
    function normalizeStreamError(event) {
        const detail = event?.error?.message || event?.message || "请求失败，请重试。";
        const error = new Error(detail);
        error.code = event?.error?.code || "stream_error";
        return error;
    }

    async function streamRequest(baseUrl, path, body, options) {
        const config = options || {};
        const headers = new Headers(config.headers || {});
        headers.set("X-User-Id", getUserId());
        headers.set("Content-Type", "application/json");
        attachModelHeaders(headers);
        const response = await fetch(`${baseUrl}${path}`, {
            method: "POST",
            headers,
            body: JSON.stringify(body),
            signal: config.signal
        });
        if (!response.ok) {
            const detail = await readError(response);
            const error = new Error(detail || `请求失败：${response.status}`);
            error.status = response.status;
            error.detail = detail;
            throw error;
        }
        if (!response.body) {
            throw new Error("当前浏览器不支持流式响应");
        }
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let finalResponse = null;
        const handleLine = (line) => {
            const text = line.trim();
            if (!text) return;
            let event;
            try {
                event = JSON.parse(text);
            } catch (error) {
                throw new Error("流式响应格式不合法");
            }
            if (config.onEvent) config.onEvent(event);
            if (event.type === "error") throw normalizeStreamError(event);
            if (event.type === "final") finalResponse = event.response;
        };
        while (true) {
            const {value, done} = await reader.read();
            buffer += decoder.decode(value || new Uint8Array(), {stream: !done});
            const lines = buffer.split("\n");
            buffer = lines.pop() || "";
            for (const line of lines) handleLine(line);
            if (done) break;
        }
        if (buffer.trim()) handleLine(buffer);
        if (!finalResponse) {
            throw new Error("请求未完成，请重试。");
        }
        return finalResponse;
    }

    function decisionStream(path, payload, options) {
        return streamRequest(DECISION_API_BASE, path, payload, options);
    }

    async function readError(response) {
        const text = await response.text();
        if (!text) {
            return "";
        }

        try {
            const payload = JSON.parse(text);
            return typeof payload.detail === "string" ? payload.detail : payload.message || payload.error || text;
        } catch (error) {
            return text;
        }
    }

    function toQuery(params) {
        const search = new URLSearchParams();
        Object.entries(params || {}).forEach(([key, value]) => {
            if (value !== undefined && value !== null && value !== "") {
                search.set(key, value);
            }
        });
        const query = search.toString();
        return query ? `?${query}` : "";
    }

    window.DietApi = {
        getUserId,
        setUserId,
        getModelSettings,
        saveModelSettings,
        clearModelSettings,
        hasConfiguredModel,
        state: (sessionId) => dietRequest(`/sessions/${encodeURIComponent(sessionId)}/state`),
        command: (sessionId, payload) => dietRequest(`/sessions/${encodeURIComponent(sessionId)}/commands`, { method: "POST", body: payload }),
        createSession: () => dietRequest("/sessions", { method: "POST" }),
        chat: (payload) => dietRequest("/chat", { method: "POST", body: payload }),
        listPersonalMeals: () => dietRequest("/meals/personal"),
        createPersonalMeal: (payload) => dietRequest("/meals/personal", { method: "POST", body: payload }),
        updatePersonalMeal: (mealId, payload) => dietRequest(`/meals/personal/${encodeURIComponent(mealId)}`, { method: "PUT", body: payload }),
        deletePersonalMeal: (mealId) => dietRequest(`/meals/personal/${encodeURIComponent(mealId)}`, { method: "DELETE" }),
        listPublicMeals: () => dietRequest("/meals/public"),
        slotOptions: () => dietRequest("/slot-options"),
        saveFeedback: (payload) => dietRequest("/feedback", { method: "POST", body: payload }),
        listTraces: (params) => dietRequest(`/debug/traces${toQuery(params)}`),
        getTrace: (traceId) => dietRequest(`/debug/traces/${encodeURIComponent(traceId)}`),
        listSessionTraces: (sessionId, limit) => dietRequest(`/debug/sessions/${encodeURIComponent(sessionId)}/traces${toQuery({ limit })}`),
        labelTrace: (traceId, payload) => dietRequest(`/debug/traces/${encodeURIComponent(traceId)}/label`, { method: "PUT", body: payload }),
        evaluate: (payload) => dietRequest("/evaluations", { method: "POST", body: payload })
    };

    window.DecisionApi = {
        resolve: (payload) => request("/api/v1/decision-domains", "/resolve", {method:"POST",body:payload}),
        searchCapabilities: () => request("/api/v1/search", "/capabilities"),
        create: (payload) => decisionRequest("", { method: "POST", body: payload }),
        createStream: (payload, options) => decisionStream("/stream", payload, options),
        message: (decisionId, payload) => decisionRequest(`/${encodeURIComponent(decisionId)}/messages`, { method: "POST", body: payload }),
        messageStream: (decisionId, payload, options) => decisionStream(`/${encodeURIComponent(decisionId)}/messages/stream`, payload, options),
        command: (decisionId, payload) => decisionRequest(`/${encodeURIComponent(decisionId)}/commands`, { method: "POST", body: payload }),
        commandStream: (decisionId, payload, options) => decisionStream(`/${encodeURIComponent(decisionId)}/commands/stream`, payload, options),
        get: (decisionId) => decisionRequest(`/${encodeURIComponent(decisionId)}`)
    };
})();
