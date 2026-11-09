# Deploy

This project is deployed as a Python ASGI web service. The service starts the existing app entrypoint:

```bash
choice_agent.main:app
```

The runtime must include `src` on `PYTHONPATH`.

## Render

The repository includes `render.yaml`, so Render can create the service from a Blueprint.

1. Push the repository to GitHub or another Git provider supported by Render.
2. In Render, choose **New > Blueprint**.
3. Select this repository.
4. Add any required application environment variables in the Render dashboard.
5. Deploy.

Render uses:

```bash
PYTHONPATH=src python -m uvicorn choice_agent.main:app --host 0.0.0.0 --port $PORT
```

## Docker

Build the image:

```bash
docker build -t choice-agent-v2 .
```

Run the container:

```bash
docker run --rm -p 8000:8000 choice-agent-v2
```

Then open:

```text
http://localhost:8000
```

To pass environment variables:

```bash
docker run --rm -p 8000:8000 --env-file .env choice-agent-v2
```

## VPS

Install Python, clone the repository, and run the app behind a reverse proxy such as Nginx.

```bash
cd /path/to/choice-agent-v2
python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install .
PYTHONPATH=src python -m uvicorn choice_agent.main:app --host 127.0.0.1 --port 8000
```

Example Nginx proxy:

```nginx
server {
    server_name example.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Use Certbot or the host platform's certificate tooling to enable HTTPS.


## Realtime Candidate Search

The deployed public UI can expose realtime candidate search for shopping and travel. Configure these environment variables on the hosting platform:

```env
CHOICE_AGENT_SEARCH_PROVIDER=openai
CHOICE_AGENT_SEARCH_API_KEY=sk-...
CHOICE_AGENT_SEARCH_BASE_URL=https://api.openai.com/v1
CHOICE_AGENT_SEARCH_MODEL=gpt-5-mini
CHOICE_AGENT_SEARCH_TIMEOUT_SECONDS=20
CHOICE_AGENT_SEARCH_MAX_QUERIES=2
```

Without `CHOICE_AGENT_SEARCH_API_KEY`, the realtime-search toggle is disabled and demo/fixture behavior remains available.

## Notes

- Deploy the backend and frontend together unless the application is explicitly split later.
- Configure secrets and environment-specific values on the hosting platform instead of committing them.
- If the project uses `pyproject.toml` instead of `requirements.txt`, the Dockerfile and Render config already fall back to installing the project package directly.

## Anonymous identity and persistent data

Set `CHOICE_AGENT_SESSION_SECRET` to a saved random secret of at least 32 bytes. Generate it once using `python -c "import secrets; print(secrets.token_hex(32))"`. Reuse it after restarts and across instances. Startup fails if it is missing or too short. The Render Blueprint generates this secret. The app does not automatically read `.env`; export variables on VPS, or use Docker `--env-file`. Never publish the saved secret.

Keep `CHOICE_AGENT_COOKIE_SECURE=true` for public HTTPS. Only local HTTP testing should use `false`. Configure the HTTPS reverse proxy to forward the correct host and scheme, and configure Uvicorn to trust forwarded headers only from that proxy. API clients must first GET `/api/v1/identity` and retain its Cookie; `X-User-Id` is ignored. Clearing/expiring the Cookie, using another device, or rotating the key loses anonymous access to previous data. Existing demonstration data is retained but not assigned to new visitors.

Runtime SQLite databases are excluded from Docker images. Persist the database using a volume and an explicit path, for example:

```bash
docker run --rm -p 8000:8000 --env-file .env -v choice-agent-data:/data -e CHOICE_AGENT_DATABASE_URL=sqlite:////data/choice_agent.db choice-agent-v2
```

Use a persistent disk/path on the hosting platform as well. Multiple instances require a shared database and secret; a local SQLite file is suitable for a single instance. Anonymous isolation does not limit model/search spending.

## Provider endpoint authorization

Browser-supplied model/search addresses must match an operator-authorized Base URL, including its path. Model defaults are `https://api.deepseek.com` and `https://api.openai.com/v1`; the search default is `https://api.openai.com/v1`. Each corresponding server-configured Base URL is trusted as well. Additional addresses use JSON string arrays:

```env
CHOICE_AGENT_MODEL_BASE_URL_ALLOWLIST=["https://model-gateway.example/v1"]
CHOICE_AGENT_SEARCH_BASE_URL_ALLOWLIST=["https://search-gateway.example/v1"]
```

Export these values using your shell's quoting rules or supply them through deployment environment settings. The app does not automatically read `.env`. Additional entries require HTTPS and exact paths; wildcards, URL credentials, queries, fragments and ambiguous/encoded paths are rejected. Trailing slashes, host case and default ports are normalized. Rejected runtime targets return HTTP 400 before a provider request is sent.

Provider HTTP requests never follow redirects. Configure the final endpoint, including for existing server-side providers. An operator may explicitly configure an HTTP/local model through the original `CHOICE_AGENT_MODEL_BASE_URL` or `CHOICE_AGENT_SEARCH_BASE_URL`; this grants access to that endpoint and should be done only for trusted services. The operator controls trusted destinations and their DNS/network configuration. The allowlist does not protect against compromised trusted endpoints or malicious deployment configuration. Browser API keys remain request-local on the server.

## Time range format

Trace queries and diet evaluations accept `startAt` and `endAt` either both without a timezone (existing server-local time semantics) or both with explicit timezone offsets. Explicit offsets, including `Z`, are converted to server-local time to match existing database timestamps. Mixed formats, equal times and reversed ranges return HTTP 400. This does not migrate old timestamps or change browser/server timezone settings.
