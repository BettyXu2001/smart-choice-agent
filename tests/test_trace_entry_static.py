from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "choice_agent" / "static"


def test_trace_page_auto_loads_recent_window_without_racing_direct_trace_open():
    entry = (STATIC / "assets" / "js" / "trace-entry.js").read_text(encoding="utf-8")
    index = (STATIC / "index.html").read_text(encoding="utf-8")

    assert 'const TRACE_HASH = "#/admin/traces"' in entry
    assert "const ONE_DAY_MS = 24 * 60 * 60 * 1000" in entry
    assert "form.requestSubmit()" in entry
    assert 'form.elements.namedItem("startAt")' in entry
    assert 'form.elements.namedItem("endAt")' in entry
    assert 'event.target.closest(\'[data-action="open-trace"]\')' in entry
    assert "suppressNextAutoLoad = true" in entry
    assert 'window.addEventListener("hashchange", handleTraceRoute)' in entry
    assert index.index("assets/js/app.js") < index.index("assets/js/trace-entry.js")
