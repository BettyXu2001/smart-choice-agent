# Web Deployment Plan

## Goal

Add the minimum deployment files needed to publish the existing Python ASGI application as a web service.

## Success Criteria

- The project has a Dockerfile suitable for generic web deployment.
- The Docker build context excludes unnecessary local files.
- Render can deploy the service from repository configuration.
- Deployment steps are documented for Render, Docker, and a VPS.
- No product code is changed.

## Design

The deployment configuration treats the app as one Python web service and starts it with Uvicorn:

```bash
python -m uvicorn choice_agent.main:app --host 0.0.0.0 --port ${PORT:-8000}
```

The image and hosted build commands support both common Python dependency layouts:

- Prefer `requirements.txt` when present.
- Fall back to `pyproject.toml` when present.
- Fail clearly if neither dependency definition exists.

## Affected Files

- `Dockerfile`
  - Add a Python 3.12 slim runtime.
  - Copy project files into `/app`.
  - Install dependencies.
  - Set `PYTHONPATH=/app/src`.
  - Start Uvicorn on `$PORT`.

- `.dockerignore`
  - Exclude Git metadata, virtual environments, caches, logs, test output, and local environment files.

- `render.yaml`
  - Add a Render web service blueprint.
  - Configure build and start commands.
  - Use the platform `PORT`.

- `docs/deploy.md`
  - Document Render deployment.
  - Document Docker deployment.
  - Document VPS/Nginx deployment outline.

## Compatibility

This change does not alter public APIs, schemas, application code, or runtime behavior outside deployment environments.

## Risks

- Deployment can still fail if required environment variables are missing on the host.
- If the project uses a nonstandard dependency manager, the dependency install command may need adjustment.
- Runtime verification is limited if Docker or the production host is unavailable locally.

## Verification

1. Inspect final diff for unexpected changes.
2. Check deployment file syntax manually.
3. Run `git diff --check`.
4. If Docker is available, optionally run `docker build -t choice-agent-v2 .`.

## Todo

- [x] Add Dockerfile.
- [x] Add .dockerignore.
- [x] Add Render blueprint.
- [x] Add deployment documentation.
- [x] Check final diff and validation status.