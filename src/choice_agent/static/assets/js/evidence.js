window.EvidenceView = (function() {
    function esc(value) {
        return window.escapeHtml ? window.escapeHtml(value) : String(value ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
    }

    function status(item) {
        const sourceKind = item?.sourceKind || "unknown";
        const statementKind = item?.statementKind || "unknown";
        const citation = item?.citationStatus || "unknown";
        const claim = item?.claimStatus || "unverified";
        const sourceLabel = {
            user: "用户输入",
            web: "搜索结果",
            system: "系统推断",
            fixture: "演示数据",
            database: "数据库记录",
            unknown: "来源不明",
        }[sourceKind] || "来源不明";
        const statementLabel = {
            reported_fact: "事实陈述",
            subjective_judgment: "主观判断",
            preference: "用户偏好",
            inference: "系统推断",
            unknown: "性质未确认",
        }[statementKind] || "性质未确认";
        let note = item?.verificationNote;
        if (!note) {
            if (sourceKind === "web") note = citation === "matched" ? "来源链接已校验，内容未独立核实" : "搜索来源待核实";
            else if (sourceKind === "user") note = "用户输入，未外部核实";
            else if (sourceKind === "fixture") note = "演示数据，不代表真实情况";
            else if (sourceKind === "database") note = "项目数据库记录";
            else if (sourceKind === "system") note = "系统推断，需查看其支撑依据";
            else note = "来源不明，待核实";
        }
        if (claim === "verified") note = "事实已核验：" + note;
        return {sourceLabel, statementLabel, note};
    }

    function safeLink(item) {
        const url = item?.sourceUrl || "";
        if (!/^https?:\/\//i.test(url)) return esc(item?.sourceTitle || "来源未记录");
        return `<a href="${esc(url)}" target="_blank" rel="noreferrer">${esc(item?.sourceTitle || url)}</a>`;
    }

    function timeLabel(item) {
        const parts = [];
        if (item?.retrievedAt) parts.push(`检索时间：${esc(new Date(item.retrievedAt).toLocaleString())}`);
        if (item?.publishedAt) parts.push(`发布时间：${esc(new Date(item.publishedAt).toLocaleString())}`);
        if (!parts.length) parts.push("时间未知");
        if (item?.freshness) parts.push(esc(item.freshness));
        return parts.join(" · ");
    }

    function sourceMap(analysis) {
        return analysis?.sources || {};
    }

    function evidenceById(analysis, decision) {
        const map = {};
        for (const source of Object.values(sourceMap(analysis))) {
            const item = source?.evidence;
            if (item?.evidenceId) map[item.evidenceId] = item;
        }
        for (const item of decision?.evidence || []) {
            if (item?.evidenceId) map[item.evidenceId] = item;
        }
        return map;
    }

    function list(ids, analysis, decision) {
        const map = evidenceById(analysis, decision);
        const items = (ids || []).map((id) => map[id] || sourceMap(analysis)[id]?.evidence).filter(Boolean);
        if (!items.length) return `<p class="muted evidence-empty">历史依据未保存或当前缺少可解析依据。</p>`;
        return `<div class="evidence-stack">${items.map((item) => {
            const labels = status(item);
            return `<article class="evidence-card">
                <div class="evidence-meta"><span>${esc(labels.sourceLabel)}</span><span>${esc(labels.statementLabel)}</span></div>
                <p>${esc(item.claim || item.sourceQuote || `${item.key || "依据"}：${item.value ?? ""}`)}</p>
                <small>${safeLink(item)}</small>
                <small>${esc(labels.note)}</small>
                <small>${timeLabel(item)}</small>
            </article>`;
        }).join("")}</div>`;
    }

    function point(item, analysis, decision) {
        const ids = item?.evidenceIds || (item?.sourceId ? [item.sourceId] : []);
        return `<li><span>${esc(item?.text || item || "")}</span><details class="evidence-details"><summary>查看 ${ids.length || 0} 条依据</summary>${list(ids, analysis, decision)}</details></li>`;
    }

    function candidate(items) {
        if (!items?.length) return `<p class="muted evidence-empty">暂缺可靠依据。</p>`;
        return list(items.map((item) => item.evidenceId).filter(Boolean), {sources: Object.fromEntries(items.filter((item) => item.evidenceId).map((item) => [item.evidenceId, {evidence: item}]))}, {evidence: items});
    }

    return {point, list, candidate};
})();
