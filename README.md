# Video Upscaler — Backend

Node.js + Express REST API designed for Railway. It owns uploads, job lifecycle, progress, local output delivery, cleanup, and the future Python-engine seam.

## Important
The actual ai_studio_code.py engine is intentionally NOT included or invented. Until the real engine is supplied, submitted jobs end in failed state with ENGINE_NOT_CONFIGURED. There are no mock outputs or fake successful jobs.

## Local
Install Node.js 22+, copy .env.example to .env, keep PYTHON_ENGINE_ENABLED=false, then run:

npm install
npm run dev

API: http://localhost:8080
Health: http://localhost:8080/health

## Railway
Use npm start as the start command. Recommended variables: NODE_ENV=production, FRONTEND_ORIGINS=https://YOUR-VERCEL-DOMAIN.vercel.app, MAX_UPLOAD_SIZE_MB=500, MAX_CONCURRENT_JOBS=1, JOB_TTL_HOURS=24, CLEANUP_INTERVAL_MINUTES=30, TEMP_DIR=./storage/jobs, PYTHON_ENGINE_ENABLED=false.

## Frontend connection
Set NEXT_PUBLIC_API_BASE_URL in Vercel to your Railway backend URL and allow that exact origin in FRONTEND_ORIGINS.

## API
GET /health
POST /api/v1/jobs
GET /api/v1/jobs/:jobId
GET /api/v1/jobs/:jobId/progress
GET /api/v1/jobs/:jobId/download

Supported: .mp4 .mov .mkv .webm .avi

## Future Python engine
The adapter is src/worker/PythonUpscalerWorker.js. When the real script is supplied, inspect its actual interface and adjust the adapter only where possible. No Python-specific logic is needed in the frontend or REST layer.

Expected current adapter command:
python ai_studio_code.py --input <input> --output <output> --scale <scale> --quality <quality> --job-id <jobId>

## Architecture
Current realtime transport is HTTP polling. Job state is queued | processing | completed | failed with progress 0..100. A future SSE/WebSocket layer can publish the same model.

## Storage
LocalJobStorage is the current implementation. Replace it later with Supabase Storage/S3-compatible storage while keeping the storage boundary. Replace InMemoryJobStore with Supabase/Postgres for durable multi-instance job metadata.

## Operational limitation
The job store is in memory and Railway local disk is ephemeral. That is intentional for the first zero-budget scaffold; durable storage should be added before multi-instance production use.
