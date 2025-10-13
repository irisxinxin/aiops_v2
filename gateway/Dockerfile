FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl wget git build-essential \
  && rm -rf /var/lib/apt/lists/*

# Install ttyd from GitHub releases
RUN wget -O /usr/local/bin/ttyd https://github.com/tsl0922/ttyd/releases/download/1.7.7/ttyd.x86_64 \
  && chmod +x /usr/local/bin/ttyd

WORKDIR /app

# 复制整个项目到 /app
COPY . /app/

RUN pip install --no-cache-dir fastapi uvicorn[standard] websockets stransi

EXPOSE 8081

CMD ["bash", "-lc", "bash gateway/start.sh"]


