(function () {
    "use strict";

    const TRACE_HASH = "#/admin/traces";
    const ONE_DAY_MS = 24 * 60 * 60 * 1000;
    let suppressNextAutoLoad = false;
    let scheduledLoad = 0;

    function isTraceRoute() {
        return (window.location.hash || "").split("?")[0] === TRACE_HASH;
    }

    function toLocalInputValue(date) {
        const pad = (value) => String(value).padStart(2, "0");
        return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
    }

    function submitCurrentTraceForm() {
        if (!isTraceRoute()) return;
        const form = document.getElementById("traceFilterForm");
        if (!form) return;

        const end = new Date();
        const start = new Date(end.getTime() - ONE_DAY_MS);
        const startInput = form.elements.namedItem("startAt");
        const endInput = form.elements.namedItem("endAt");
        if (startInput) startInput.value = toLocalInputValue(start);
        if (endInput) endInput.value = toLocalInputValue(end);

        form.requestSubmit();
    }

    function scheduleTraceAutoLoad() {
        const token = ++scheduledLoad;
        window.setTimeout(() => {
            if (token !== scheduledLoad || !isTraceRoute()) return;
            submitCurrentTraceForm();
        }, 0);
    }

    function handleTraceRoute() {
        if (!isTraceRoute()) return;
        if (suppressNextAutoLoad) {
            suppressNextAutoLoad = false;
            return;
        }
        scheduleTraceAutoLoad();
    }

    document.addEventListener("click", (event) => {
        const directTraceLink = event.target.closest('[data-action="open-trace"]');
        if (directTraceLink && !isTraceRoute()) {
            // app.js already loads this exact traceId. Avoid an automatic list query
            // racing with selectTrace() and replacing the requested detail.
            suppressNextAutoLoad = true;
        }
    }, true);

    window.addEventListener("hashchange", handleTraceRoute);

    // app.js renders synchronously during initial page load. If the browser is
    // refreshed on #/admin/traces, trigger the same recent-24h query afterwards.
    if (isTraceRoute()) {
        scheduleTraceAutoLoad();
    }
})();
