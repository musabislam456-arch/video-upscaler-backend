# Architecture

Browser / Next.js on Vercel -> Node.js + Express on Railway -> JobService -> Queue -> WorkerContract/Python adapter -> future ai_studio_code.py -> FFmpeg/OpenCV.

## Boundaries

### JobService
Owns job lifecycle and API response shape. It does not know the internal upscaling algorithm.

### JobQueue
Currently an in-process concurrency-limited queue. Keep it small for a zero-budget Railway deployment. A future Redis/BullMQ or database-backed queue can replace the implementation behind the enqueue concept.

### WorkerContract
The stable Python integration seam. A worker receives input/output paths, job settings, a cancellation signal, and a progress callback.

### LocalJobStorage
Per-job directories prevent name collisions and make path validation straightforward. The storage interface can later be replaced by Supabase Storage or S3-compatible object storage.

### JobStore
Currently in memory. For jobs that must survive backend restarts, replace it with a database repository implementing the same create/get/update/list/delete semantics. Supabase/Postgres is the intended future integration point.

## Security notes

- Original filenames are not used as filesystem paths.
- Every job gets a cryptographically random UUID directory.
- Resolved paths are checked to remain inside the job directory.
- Multer enforces the backend upload size limit.
- Upload extensions and MIME types are validated.
- HTTP security headers are enabled with Helmet.
- CORS requires explicit production origins.
- API requests are rate limited.
- Python processes are spawned without a shell.
- Cleanup removes completed/failed data after the configured TTL.
