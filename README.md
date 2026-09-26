# Video Upscaler — Backend

Node.js + Express REST API for a zero-AI, CPU-only video upscaling service. The supplied `ai_studio_code.py` is included and invoked through an isolated worker adapter.

## Processing

Next.js/Vercel
→ Node.js + Express/Railway
→ bounded in-process queue
→ Python worker adapter
→ ai_studio_code.py
→ FFmpeg + OpenCV + NumPy
→ output video
→ download API

No AI/ML, GPU, or neural-network dependency is used.

## Local development

Requirements:
- Node.js 22+
- Python 3.11+
- FFmpeg + ffprobe in PATH

Windows setup:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
ffmpeg -version
ffprobe -version
npm install
npm run dev
```

API: `http://localhost:8080`

Use `.env.example` as the starting point. On Windows the Python executable is normally `python`; Railway's Docker image uses `/opt/venv/bin/python`.

## Railway deployment

Railway detects a root-level `Dockerfile` automatically. This image installs Node, Python, NumPy, OpenCV and FFmpeg.

Recommended variables:

```text
NODE_ENV=production
FRONTEND_ORIGINS=https://YOUR-VERCEL-DOMAIN.vercel.app
MAX_UPLOAD_SIZE_MB=500
MAX_CONCURRENT_JOBS=1
JOB_TTL_HOURS=24
CLEANUP_INTERVAL_MINUTES=30
TEMP_DIR=./storage/jobs
PYTHON_ENGINE_ENABLED=true
PYTHON_EXECUTABLE=/opt/venv/bin/python
PYTHON_ENGINE_PATH=./ai_studio_code.py
PYTHON_ENGINE_TIMEOUT_MS=86400000
```

Connect the GitHub repo to the Railway service. Each push to the tracked branch can trigger a new deployment.

## API

- `GET /health`
- `POST /api/v1/jobs`
- `GET /api/v1/jobs/:jobId`
- `GET /api/v1/jobs/:jobId/progress`
- `GET /api/v1/jobs/:jobId/download`

Upload field: `video`

Scale values:
- `2x`
- `4x`
- `1080p`
- `1440p`
- `4K`

Quality values:
- `fast`
- `balanced`
- `quality`
- `max`

## Python engine mapping

The Node adapter maps frontend choices to the actual CLI supported by the Python engine:

- 2x → `--scale 2`
- 4x → `--scale 4`
- 1080p → `--height 1080`
- 1440p → `--height 1440`
- 4K → `--height 2160`

The worker also parses the engine's carriage-return progress output and maps it into the existing job progress endpoint.

## Storage / zero-budget limitation

The current job metadata store is in memory and active job files use local storage. On Railway, local filesystem data is ephemeral unless a persistent volume or object storage is used. The Railway free plan currently exposes 0.5 GB volume storage, so large source/output videos can exceed the free storage budget.

For the first zero-budget test, use small sample videos and keep `MAX_CONCURRENT_JOBS=1`. For larger production files, move media to object storage and job metadata to durable storage.

## No fake processing

A job is marked completed only if the Python process exits successfully and the expected output file exists and passes post-validation. There is no mock output path.
