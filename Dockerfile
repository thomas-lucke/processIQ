FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 libpangoft2-1.0-0 libgdk-pixbuf-xlib-2.0-0 \
    libffi-dev shared-mime-info \
    libgl1 libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

RUN pip install uv

COPY pyproject.toml uv.lock README.md ./

RUN uv sync --no-dev

COPY src/ src/
COPY api/ api/

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
