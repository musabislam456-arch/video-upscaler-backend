# API Contract

Base URL locally: `http://localhost:8080`

## POST /api/v1/jobs

`multipart/form-data`

- `video`: one video file
- `scale`: `2x | 4x | 1080p | 1440p | 4K`
- `quality`: `fast | balanced | quality | max`

Returns HTTP 202 and a `jobId`.

## GET /api/v1/jobs/:jobId

Returns the current job object.

## GET /api/v1/jobs/:jobId/progress

Polling-friendly response:

```json
{
  "jobId": "uuid",
  "state": "processing",
  "progress": 42.5,
  "status": "Encoding · 0.8x",
  "updatedAt": "2026-09-26T00:00:00.000Z",
  "error": null
}
```

## GET /api/v1/jobs/:jobId/download

Streams the completed output as a download. Returns 409 until the job completes.

## Job lifecycle

```
queued -> processing -> completed
                    -> failed
```

## Worker mapping

```
2x      -> ai_studio_code.py --scale 2
4x      -> ai_studio_code.py --scale 4
1080p   -> ai_studio_code.py --height 1080
1440p   -> ai_studio_code.py --height 1440
4K      -> ai_studio_code.py --height 2160
```

The worker does not pass arbitrary filesystem paths from the browser to Python. Input/output paths are created server-side inside a unique job directory.
