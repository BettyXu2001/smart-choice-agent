"""Operator-authorized runtime endpoints and non-redirecting provider transport."""
from urllib.parse import urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, build_opener


def normalize_base_url(value: str) -> str:
    if not value or any(ord(ch) <= 32 or ord(ch) == 127 for ch in value) or "\\" in value:
        raise ValueError("Provider Base URL 不合法")
    parsed = urlsplit(value)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or "?" in value or "#" in value or "%" in parsed.netloc
            or "%" in parsed.path or any(part in {".", ".."} for part in parsed.path.split("/"))):
        raise ValueError("Provider Base URL 不合法")
    host = parsed.hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    port = parsed.port
    if port is not None and port != (443 if parsed.scheme == "https" else 80):
        host += f":{port}"
    return urlunsplit((parsed.scheme, host, parsed.path.rstrip("/"), "", ""))


def authorize_base_url(value: str, server_url: str, additional: tuple[str, ...], *, search: bool = False) -> str:
    normalized = normalize_base_url(value)
    defaults = {"https://api.openai.com/v1"}
    if not search:
        defaults.add("https://api.deepseek.com")
    allowed = defaults | {normalize_base_url(server_url)} | {normalize_base_url(url) for url in additional}
    if normalized not in allowed:
        raise ValueError("该 Provider 地址未获授权，请联系部署者配置可信地址")
    return normalized


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def open_provider_request(request, *, timeout: float):
    return build_opener(_NoRedirect()).open(request, timeout=timeout)
