from __future__ import annotations

import json
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from choice_agent.agents.base import AgentContext
from choice_agent.providers.candidates import CandidateSearchResult
from choice_agent.schemas import Candidate, Evidence, SearchRun, SourceDocument


Transport = Callable[[Request, float], dict[str, Any]]


class SearchProviderError(RuntimeError):
    """Search configuration, transport, or structured-response failure."""


class OpenAIWebSearchProvider:
    name = "openai_web_search"

    def __init__(self, api_key: str, base_url: str, model: str,
                 timeout_seconds: float = 20.0, max_queries: int = 2,
                 transport: Transport | None = None):
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_queries = max(1, max_queries)
        self.transport = transport or self._send

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def search(self, context: AgentContext) -> CandidateSearchResult:
        if not self.enabled:
            raise SearchProviderError("Web Search 未配置 API Key")
        body = {
            "model": self.model,
            "tools": [{"type": "web_search"}],
            "include": ["web_search_call.action.sources"],
            "tool_choice": "required",
            "max_tool_calls": self.max_queries,
            "input": (
                "Research real options for this decision. Return strict JSON with a candidates array. "
                "Each candidate needs id, name, summary, attributes, and evidence. Each evidence item "
                "needs key, value, claim, sourceTitle, and sourceUrl. Use only URLs returned by web search.\n"
                f"Domain: {context.decision.domain}\nGoal: {context.decision.user_goal}\n"
                f"Confirmed/current fields (override original goal): {json.dumps(context.decision.domain_state.get('conversationFields', {}), ensure_ascii=False)}\n"
                f"Current message: {context.message}\nCriteria: "
                f"{json.dumps([item.model_dump(by_alias=True) for item in context.decision.criteria], ensure_ascii=False)}\n"
                f"Constraints: {json.dumps([item.model_dump(by_alias=True) for item in context.decision.constraints], ensure_ascii=False)}"
            ),
        }
        request = Request(
            f"{self.base_url}/responses",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        last_error: Exception | None = None
        for _ in range(2):
            try:
                payload = self.transport(request, self.timeout_seconds)
                return self._parse(payload, context)
            except (HTTPError, URLError, TimeoutError, ValueError, KeyError, TypeError) as error:
                last_error = error
        raise SearchProviderError(f"Web Search 失败：{last_error}") from last_error

    def _send(self, request: Request, timeout: float) -> dict[str, Any]:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def _parse(self, payload: dict[str, Any], context: AgentContext) -> CandidateSearchResult:
        text = str(payload.get("output_text") or "")
        fragments: list[str] = []
        citations: dict[str, str] = {}
        for output in payload.get("output", []):
            if output.get("type") == "web_search_call":
                for source in output.get("action", {}).get("sources", []):
                    if source.get("type") == "url" and source.get("url"):
                        citations[source["url"]] = str(source.get("title") or source["url"])
            for content in output.get("content", []):
                if content.get("type") == "output_text":
                    fragments.append(str(content.get("text", "")))
                for annotation in content.get("annotations", []):
                    url = annotation.get("url")
                    if annotation.get("type") == "url_citation" and url:
                        citations[str(url)] = str(annotation.get("title") or url)
        text = text or "".join(fragments)
        parsed = json.loads(self._clean_json(text))
        sources = [
            SourceDocument(source_id=f"web:{index}", title=title, url=url,
                           publisher=title, kind="web")
            for index, (url, title) in enumerate(citations.items(), start=1)
        ]
        candidates: list[Candidate] = []
        evidence: list[Evidence] = []
        for raw in parsed.get("candidates", []):
            candidate_id = str(raw.get("id") or uuid4().hex)
            items = [
                Evidence(
                    key=str(item["key"]), value=item.get("value"), candidate_id=candidate_id,
                    criterion_key=str(item.get("criterionKey") or item["key"]),
                    claim=str(item.get("claim") or ""),
                    source_title=str(item.get("sourceTitle") or "Web Search"),
                    source_url=str(item.get("sourceUrl") or "") or None,
                    publisher=str(item.get("publisher") or "") or None,
                    confidence=float(item.get("confidence", 0.7)),
                    published_at=item.get("publishedAt"),
                    freshness="需核实当前价格" if str(item["key"]) in {"price", "budget"} else item.get("freshness"),
                )
                for item in raw.get("evidence", [])
            ]
            evidence.extend(items)
            candidates.append(Candidate(
                candidate_id=candidate_id, name=str(raw["name"]),
                summary=str(raw.get("summary", "")),
                attributes=dict(raw.get("attributes", {})), evidence=items, origin="web",
            ))
        if not candidates:
            raise ValueError("Web Search 未返回结构化候选")
        run = SearchRun(
            run_id=str(payload.get("id") or uuid4().hex), provider=self.name, mode="web",
            query=context.message, source_ids=[source.source_id for source in sources],
        )
        return CandidateSearchResult(candidates, sources, evidence, run)

    def _clean_json(self, value: str) -> str:
        text = value.strip()
        fence = chr(96) * 3
        if text.startswith(fence):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            text = text.rsplit(fence, 1)[0]
        return text.strip()