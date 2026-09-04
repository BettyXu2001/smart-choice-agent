# Web Deployment Research

## Demand and Scope

The project needs the minimum files required to deploy the existing application as a web service.

Scope:

- Add deployment configuration files.
- Document supported deployment paths.
- Avoid changing product code or runtime behavior.

Out of scope:

- Refactoring the application.
- Changing API routes.
- Splitting frontend and backend hosting.
- Adding external managed services.

## Current Understanding

The application is expected to run as a Python ASGI service using FastAPI/Uvicorn, with the app entrypoint:

```bash
choice_agent.main:app
```

The runtime needs `src` on `PYTHONPATH`.

The known local command shape is:

```bash
PYTHONPATH=src python -m uvicorn choice_agent.main:app --host 0.0.0.0 --port 8000
```

For hosted platforms, the port must come from the platform environment, usually `$PORT`.

## Core Files and Responsibilities

- `Dockerfile`: Container image definition for generic Docker-compatible hosts.
- `.dockerignore`: Prevents local caches, virtual environments, build output, and Git metadata from entering the Docker build context.
- `render.yaml`: Render Blueprint configuration for one web service.
- `docs/deploy.md`: Human-readable deployment instructions.

## Key Runtime Flow

1. Host checks out or receives the repository.
2. Python dependencies are installed from `requirements.txt` when present.
3. If `requirements.txt` is absent and `pyproject.toml` is present, the project is installed from `pyproject.toml`.
4. The server starts Uvicorn with `choice_agent.main:app`.
5. The public web service receives traffic on the host-provided port.

## Reusable Capability

Existing ASGI app startup can be reused directly. No new application entrypoint is required.

## Risks and Constraints

- If neither `requirements.txt` nor `pyproject.toml` exists, deployment should fail clearly during build.
- If static assets depend on backend API routes, the frontend and backend should be deployed together.
- Platform-specific environment variables must be configured outside the repository if the app requires them.
- The command helper initially returned `helper_unknown_error`; deployment files are therefore conservative and generic.

## Decisions Deferred to Plan

- Whether to include both Docker and Render support.
- Whether to add documentation in addition to machine-readable deployment files.
- Whether to modify application code for health checks or production settings.