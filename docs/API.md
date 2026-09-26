# API Contract

Base URL locally: http://localhost:8080

All JSON errors use an error object with code and message.

## GET /health
Returns service and queue health.

## POST /api/v1/jobs
multipart/form-data upload.

Fields:
- video: one supported video file
- scale: 2x | 4x | 1080p | 1440p | 4K
- quality: fast | balanced | quality | max

Returns HTTP 202 with a unique jobId and initial queued state.

## GET /api/v1/jobs/:jobId
Returns the full current job representation.

## GET /api/v1/jobs/:jobId/progress
Returns a lightweight polling-friendly progress object. The frontend polls this endpoint every 1.5 seconds. A future SSE/WebSocket layer can publish the same progress fields without changing job semantics.

## GET /api/v1/jobs/:jobId/download
Returns the completed output as an attachment. It returns 409 until the job is completed.

## Job states
queued -> processing -> completed
                    -> failed

completed means the worker returned successfully and the expected output file exists and is non-empty.

## Worker integration contract
The adapter currently expects:
python ai_studio_code.py --input <input> --output <output> --scale <scale> --quality <quality> --job-id <jobId>

Optional progress can be emitted as JSONL on stdout using type=progress or type=status with progress 0..100.

Exit code 0 plus a non-empty output path is required for completion.
