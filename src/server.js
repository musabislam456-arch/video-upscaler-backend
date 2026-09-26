import { createApp } from "./app.js";
import { env } from "./config/env.js";
import { logger } from "./utils/logger.js";
import { InMemoryJobStore } from "./store/jobStore.js";
import { LocalJobStorage } from "./store/storage.js";
import { JobQueue } from "./services/queue.js";
import { JobService } from "./services/jobService.js";
import { CleanupService } from "./services/cleanupService.js";
import { PythonUpscalerWorker } from "./worker/PythonUpscalerWorker.js";

const store = new InMemoryJobStore();
const storage = new LocalJobStorage(env.tempDir);
await storage.init();

const queue = new JobQueue({ concurrency: env.maxConcurrentJobs });
const worker = new PythonUpscalerWorker();
const jobService = new JobService({ store, storage, queue, worker });
const cleanup = new CleanupService({ store, storage });
cleanup.start();

const app = createApp({ jobService, queue });
const server = app.listen(env.port, () => {
  logger.info("server_started", { port: env.port, nodeEnv: env.nodeEnv, tempDir: env.tempDir, pythonEngineEnabled: env.pythonEngineEnabled });
});

function shutdown(signal) {
  logger.info("shutdown_requested", { signal });
  cleanup.stop();
  server.close(() => process.exit(0));
}

process.on("SIGINT", () => shutdown("SIGINT"));
process.on("SIGTERM", () => shutdown("SIGTERM"));
