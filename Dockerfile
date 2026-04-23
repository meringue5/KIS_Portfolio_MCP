FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    KIS_DATA_DIR=var

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .

RUN uv sync --frozen --no-dev

RUN mkdir -p var/tokens var/local var/backup

EXPOSE 8000

CMD ["uv", "run", "kis-portfolio-mcp"]
