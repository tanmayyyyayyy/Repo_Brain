# Minimal, lightweight container for RepoBrain governance engine + demo console
FROM python:3.12-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    REPOBRAIN_HOST=0.0.0.0 \
    PORT=8765

WORKDIR /app
COPY pyproject.toml README.md ./
COPY repobrain/ ./repobrain/
COPY demo_assets/ ./demo_assets/
COPY .github/ ./.github/

RUN pip install --no-cache-dir pyyaml pytest coverage && \
    pip install --no-cache-dir -e .

EXPOSE 8765

ENTRYPOINT ["repobrain"]
# Default to the public demo console. Override with e.g.
#   docker run --rm -v "$(pwd)":/repo -w /repo repobrain review --base origin/main
CMD ["serve", "--demo", "--no-browser", "--host", "0.0.0.0", "--open"]
