const test = require("node:test");
const assert = require("node:assert/strict");
const vm = require("node:vm");
const fs = require("node:fs");
const source = fs.readFileSync("src/choice_agent/static/assets/js/api.js", "utf8");
function setup(fetch) {
    const events = [];
    const storage = new Map([["diet.userId", "1"]]);
    const window = {dispatchEvent: event => events.push(event.type)};
    const context = {window, fetch, navigator: {locks: {request: (_name, load) => load()}},
        localStorage: {getItem: key => storage.get(key) || null, setItem: (key, value) => storage.set(key, value), removeItem: key => storage.delete(key)},
        Headers, FormData, TextDecoder, Uint8Array, URLSearchParams, Event};
    vm.runInNewContext(source, context);
    return {window, events};
}
function json(value, status = 200) { return new Response(JSON.stringify(value), {status}); }
test("concurrent ordinary/stream requests initialize identity once and ignore old IDs", async () => {
    const calls = [];
    const {window} = setup(async (url, options) => {
        calls.push({url, options});
        if (url === "/api/v1/identity") return json({userId: 314});
        if (url.endsWith("/stream")) return new Response(JSON.stringify({type: "final", response: {ok: true}}) + "\n");
        return json({notes: null});
    });
    await Promise.all([window.ProfileApi.get(), window.DecisionApi.createStream({message: "test"})]);
    assert.equal(calls.filter(c => c.url === "/api/v1/identity").length, 1);
    assert.equal(window.DietApi.getUserId(), "314");
    assert.equal(window.DietApi.setUserId, undefined);
    for (const call of calls) {
        assert.equal(call.options.credentials, "same-origin");
        if (call.options.headers) assert.equal(call.options.headers.has("X-User-Id"), false);
    }
});
test("identity failure can retry, but a 401 invalidates state and never replays writes", async () => {
    let bootstraps = 0, writes = 0;
    const {window, events} = setup(async (url) => {
        if (url === "/api/v1/identity") return ++bootstraps === 1 ? json({message: "temporary"}, 503) : json({userId: 42});
        writes++;
        return json({message: "expired"}, 401);
    });
    await assert.rejects(window.DietApi.ensureIdentity(), /temporary/);
    await window.DietApi.ensureIdentity();
    await assert.rejects(window.ProfileApi.save({notes: "private"}), /expired/);
    assert.equal(window.DietApi.getUserId(), null);
    await assert.rejects(window.ProfileApi.save({notes: "private"}), /会话已失效/);
    assert.equal(writes, 1);
    assert.equal(bootstraps, 2);
    assert.deepEqual(events, ["choice-agent-identity-expired"]);
});
