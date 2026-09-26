FROM node:22-bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHON_EXECUTABLE=/opt/venv/bin/python

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates \
       ffmpeg \
       python3 \
       python3-pip \
       python3-venv \
       libglib2.0-0 \
       libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

COPY package.json ./
RUN npm install --omit=dev

COPY . .

RUN mkdir -p /app/storage/jobs

ENV PORT=8080 \
    PYTHON_ENGINE_ENABLED=true \
    PYTHON_ENGINE_PATH=./ai_studio_code.py \
    UPSCALE_LOW_MEMORY_MODE=true \
    TEMP_DIR=./storage/jobs \
    MAX_CONCURRENT_JOBS=1

EXPOSE 8080

CMD ["npm", "start"]
