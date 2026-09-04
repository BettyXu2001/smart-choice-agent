FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src
ENV PORT=8000

WORKDIR /app

COPY . .

RUN python -m pip install --no-cache-dir --upgrade pip \
    && if [ -f requirements.txt ]; then \
        python -m pip install --no-cache-dir -r requirements.txt; \
    elif [ -f pyproject.toml ]; then \
        python -m pip install --no-cache-dir .; \
    else \
        echo "No requirements.txt or pyproject.toml found" >&2; \
        exit 1; \
    fi

EXPOSE 8000

CMD ["sh", "-c", "python -m uvicorn choice_agent.main:app --host 0.0.0.0 --port ${PORT:-8000}"]