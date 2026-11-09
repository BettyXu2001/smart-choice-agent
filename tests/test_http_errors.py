import pytest
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode


@pytest.mark.parametrize("body,raw", [
    ({"title": "x", "originalQuestion": "x", "expectedBehavior": "x", "caseData": {
        "assertions": [{"metricId": "x", "operator": "manual", "required": True}]}}, None),
    ({"title": []}, None),
    ({}, None),
    (None, b"{invalid json"),
])
def test_invalid_requests_return_serializable_422_json(web, body, raw):
    web.call("GET", "/api/v1/identity")
    status, response, _ = web.call("POST", "/api/v1/evaluations/cases", body, raw=raw)
    assert status == 422
    assert response["message"] == "请求参数不合法" and response["errors"]
    assert all("ctx" not in item and "input" not in item for item in response["errors"])


def range_request(web, endpoint, start, end):
    params = {"startAt": start, "endAt": end}
    if endpoint == "traces":
        return web.call("GET", "/api/v1/diet/debug/traces?" + urlencode(params))
    return web.call("POST", "/api/v1/diet/evaluations", params)


@pytest.mark.parametrize("endpoint", ["traces", "evaluations"])
@pytest.mark.parametrize("start,end", [
    ("2026-01-01T00:00:00Z", "2026-01-02T00:00:00"),
    ("2026-01-01T00:00:00", "2026-01-02T00:00:00+08:00"),
    ("2026-01-02T00:00:00", "2026-01-01T00:00:00"),
    ("2026-01-01T00:00:00", "2026-01-01T00:00:00"),
    ("2026-01-01T08:00:00+08:00", "2026-01-01T00:00:00Z"),
    ("2026-01-01T00:00:00Z", "2026-01-01T01:00:00+08:00"),
])
def test_invalid_time_ranges_return_business_400(web, endpoint, start, end):
    web.call("GET", "/api/v1/identity")
    status, response, _ = range_request(web, endpoint, start, end)
    assert status == 400 and response["message"]


@pytest.mark.parametrize("endpoint", ["traces", "evaluations"])
@pytest.mark.parametrize("mode", ["naive", "utc", "different_offsets"])
def test_time_ranges_query_trace_and_feedback_by_instant(web, endpoint, mode):
    from choice_agent.db_models import FeedbackRecord, TraceRecord

    owner = web.call("GET", "/api/v1/identity")[1]["userId"]
    instant = datetime(2026, 1, 5, 12, tzinfo=timezone.utc)
    local = instant.astimezone().replace(tzinfo=None)
    with web.app.state.database.session_factory() as db:
        for name, delta in (("before", -2), ("inside", 0), ("after", 2)):
            db.add(TraceRecord(
                trace_id=name, session_id="range-session", user_id=owner, status="SUCCESS",
                event_count=0, trace_json={}, created_at=local + timedelta(hours=delta),
            ))
        db.add(FeedbackRecord(user_id=owner, session_id="range-session", action="LIKE", rating=5, created_at=local))
        db.add(FeedbackRecord(user_id=owner, session_id="range-session", action="DISLIKE", rating=0,
                              created_at=local + timedelta(hours=2)))
        db.commit()
    start, end = instant - timedelta(hours=1), instant + timedelta(hours=1)
    if mode == "naive":
        start, end = (value.astimezone().replace(tzinfo=None) for value in (start, end))
    elif mode == "different_offsets":
        start = start.astimezone(timezone(timedelta(hours=8)))
        end = end.astimezone(timezone(timedelta(hours=-5)))
    start_text, end_text = start.isoformat(), end.isoformat()
    if mode == "utc":
        start_text, end_text = start_text.replace("+00:00", "Z"), end_text.replace("+00:00", "Z")
    status, result, _ = range_request(web, endpoint, start_text, end_text)
    assert status == 200
    if endpoint == "traces":
        assert [row["traceId"] for row in result] == ["inside"]
    else:
        assert result["totalTraces"] == 1
        assert result["traceResults"][0]["traceId"] == "inside"
        assert result["traceResults"][0]["userFeedbackScore"] == 1
        assert datetime.fromisoformat(result["startAt"]) == start
        assert datetime.fromisoformat(result["endAt"]) == end
