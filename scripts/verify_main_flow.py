from __future__ import annotations

import json
from datetime import datetime, timedelta
from urllib import request


BASE = "http://127.0.0.1:8000"


def call(method: str, path: str, body: dict | None = None):
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8") if body else None
    req = request.Request(
        BASE + path,
        data=payload,
        method=method,
        headers={"Content-Type": "application/json", "X-User-Id": "7001"},
    )
    with request.urlopen(req, timeout=10) as response:
        raw = response.read()
        return json.loads(raw.decode("utf-8")) if raw else None


def main() -> None:
    health = call("GET", "/health")
    session = call("POST", "/api/v1/diet/sessions")
    chat = call(
        "POST",
        "/api/v1/diet/chat",
        {
            "sessionId": session["sessionId"],
            "message": "晚餐想吃清淡一点",
            "sourceMode": "PUBLIC",
        },
    )
    trace = call("GET", f"/api/v1/diet/debug/traces/{chat['traceId']}")
    personal = call(
        "POST",
        "/api/v1/diet/meals/personal",
        {"name": "验证餐", "mealTime": ["晚餐"], "taste": ["清淡"]},
    )
    call(
        "PUT",
        f"/api/v1/diet/meals/personal/{personal['id']}",
        {"name": "验证餐更新", "mealTime": ["午餐"], "taste": ["咸鲜"]},
    )
    call(
        "POST",
        "/api/v1/diet/feedback",
        {
            "sessionId": chat["sessionId"],
            "itemId": chat["displayBlocks"][0]["id"],
            "action": "LIKE",
            "rating": 5,
        },
    )
    call(
        "PUT",
        f"/api/v1/diet/debug/traces/{chat['traceId']}/label",
        {
            "expectedIntent": "MEAL_RECOMMENDATION",
            "expectedClarifyAction": "READY",
            "labelNote": "main flow verification",
        },
    )
    now = datetime.now()
    report = call(
        "POST",
        "/api/v1/diet/evaluations",
        {
            "startAt": (now - timedelta(hours=1)).isoformat(),
            "endAt": (now + timedelta(hours=1)).isoformat(),
            "includeLlmJudge": False,
            "limit": 50,
        },
    )
    call("DELETE", f"/api/v1/diet/meals/personal/{personal['id']}")
    assert health["status"] == "ok"
    assert chat["responseType"] == "ANSWER"
    assert len(chat["displayBlocks"]) > 0
    assert len(chat["decisionState"]["agentRuns"]) >= 7
    assert trace["status"] == "SUCCESS"
    assert report["totalTraces"] >= 1
    print("Main flow verified.")


if __name__ == "__main__":
    main()
