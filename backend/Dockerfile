FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends libcairo2 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]" || pip install --no-cache-dir ".[dev]"
COPY . .
