FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_VERSION=1.8.3

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl wget git build-essential \
    ttyd \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 复制网关与 aiops（以工程根为构建上下文）
COPY gateway/ /app/gateway/
COPY . /app/aiops/

RUN pip install --no-cache-dir fastapi uvicorn[standard] websockets

EXPOSE 8081

CMD ["bash", "-lc", "bash gateway/start.sh"]


