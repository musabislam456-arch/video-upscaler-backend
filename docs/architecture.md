# Architecture

```
Next.js/Vercel
     |
     | HTTPS REST
     v
Node.js + Express/Railway
     |
     +--> JobService
     |       |
     |       +--> InMemoryJobStore
     |       +--> LocalJobStorage
     |       +--> JobQueue (concurrency limited)
     |
     +--> PythonUpscalerWorker
             |
             +--> ai_studio_code.py
                    |
                    +--> FFmpeg
                    +--> OpenCV
                    +--> NumPy
```

## Engine boundary

The Node API does not contain the upscaling algorithm. `PythonUpscalerWorker` is the adapter and can be replaced later without changing the frontend API.

## Scale mapping

Fixed-height targets preserve source aspect ratio because the Python engine computes the other dimension automatically:

- 1080p → height 1080
- 1440p → height 1440
- 4K → height 2160

## Progress

The Python engine emits carriage-return progress lines during FFmpeg encoding. The adapter converts these to job progress and status messages. The HTTP client polls `/progress` until the job reaches `completed` or `failed`.

## Deployment

Railway uses the root-level Dockerfile automatically. The Docker image installs the required Python runtime, OpenCV, NumPy and FFmpeg.

## Storage evolution

Local files are the current implementation boundary. Railway Volumes can make local files persistent for a single service instance; an S3-compatible/Railway storage bucket is better for larger media. The job metadata store should eventually move from memory to Postgres/Supabase for restart and multi-instance durability.

## Concurrency

`MAX_CONCURRENT_JOBS=1` is deliberate for a zero-budget CPU deployment. Multiple workers/instances should be introduced only after durable job metadata and a shared queue/storage layer are added.
