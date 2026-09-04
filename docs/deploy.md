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
python -m pip install -r requirements.txt
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

## Notes

- Deploy the backend and frontend together unless the application is explicitly split later.
- Configure secrets and environment-specific values on the hosting platform instead of committing them.
- If the project uses `pyproject.toml` instead of `requirements.txt`, the Dockerfile and Render config already fall back to installing the project package directly.