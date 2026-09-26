# Engine Integration Checklist

When ai_studio_code.py is supplied:

1. Inspect the script before changing any backend code.
2. Determine its actual input/output arguments and how it reports progress.
3. Update only src/worker/PythonUpscalerWorker.js if possible.
4. Keep output path under the generated job directory.
5. Never accept a user-provided filesystem path as a worker command argument.
6. Keep the worker process spawned without a shell.
7. Make sure the engine exits non-zero on failure.
8. Make sure a completed run produces a non-empty output file.
9. Verify 2x, 4x, 1080p, 1440p, and 4K mapping.
10. Verify fast, balanced, quality, and max mapping.
11. Test progress updates from 0 to 100.
12. Test cancellation/timeout behavior.
13. Test cleanup of failed jobs.
