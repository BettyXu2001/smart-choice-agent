(function () {
    "use strict";

    const API_BASE = "/api/v1/diet";
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

    async function request(path, options) {
        const config = options || {};
        const headers = new Headers(config.headers || {});
        headers.set("X-User-Id", getUserId());
        attachModelHeaders(headers);

        if (config.body !== undefined && !(config.body instanceof FormData)) {
            headers.set("Content-Type", "application/json");
        }

        const response = await fetch(`${API_BASE}${path}`, {
            ...config,
            headers,
            body: config.body === undefined || config.body instanceof FormData
                ? config.body
                : JSON.stringify(config.body)
        });

        if (!response.ok) {
            const detail = await readError(response);
            throw new Error(detail || `请求失败：${response.status}`);
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

    async function readError(response) {
        const text = await response.text();
        if (!text) {
            return "";
        }

        try {
            const payload = JSON.parse(text);
            return payload.message || payload.error || text;
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
        createSession: () => request("/sessions", { method: "POST" }),
        chat: (payload) => request("/chat", { method: "POST", body: payload }),
        listPersonalMeals: () => request("/meals/personal"),
        createPersonalMeal: (payload) => request("/meals/personal", { method: "POST", body: payload }),
        updatePersonalMeal: (mealId, payload) => request(`/meals/personal/${encodeURIComponent(mealId)}`, { method: "PUT", body: payload }),
        deletePersonalMeal: (mealId) => request(`/meals/personal/${encodeURIComponent(mealId)}`, { method: "DELETE" }),
        listPublicMeals: () => request("/meals/public"),
        slotOptions: () => request("/slot-options"),
        saveFeedback: (payload) => request("/feedback", { method: "POST", body: payload }),
        listTraces: (params) => request(`/debug/traces${toQuery(params)}`),
        getTrace: (traceId) => request(`/debug/traces/${encodeURIComponent(traceId)}`),
        listSessionTraces: (sessionId, limit) => request(`/debug/sessions/${encodeURIComponent(sessionId)}/traces${toQuery({ limit })}`),
        labelTrace: (traceId, payload) => request(`/debug/traces/${encodeURIComponent(traceId)}/label`, { method: "PUT", body: payload }),
        evaluate: (payload) => request("/evaluations", { method: "POST", body: payload })
    };
})();
