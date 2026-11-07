# Minimal, lightweight container for RepoBrain governance engine
FROM python:3.12-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY repobrain/ ./repobrain/

RUN pip install --no-cache-dir pyyaml && \
    pip install --no-cache-dir -e .

WORKDIR /repo

ENTRYPOINT ["repobrain"]
CMD ["review", "--base", "origin/main"]
