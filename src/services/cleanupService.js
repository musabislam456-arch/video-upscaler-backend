import fs from "node:fs/promises";
import { env } from "../config/env.js";
import { logger } from "../utils/logger.js";

export class CleanupService {
  constructor({ store, storage }) {
    this.store = store;
    this.storage = storage;
    this.timer = null;
  }

  start() {
    this.timer = setInterval(() => this.run().catch((error) => logger.error("cleanup_failed", { error: String(error) })), env.cleanupIntervalMs);
    this.timer.unref?.();
  }

  stop() {
    if (this.timer) clearInterval(this.timer);
  }

  async run() {
    const cutoff = Date.now() - env.jobTtlHours * 60 * 60 * 1000;
    for (const job of this.store.list()) {
      if (!["completed", "failed"].includes(job.state)) continue;
      if (Date.parse(job.completedAt || job.updatedAt || job.createdAt) > cutoff) continue;
      await this.storage.removeJobDirectory(job.jobDir);
      this.store.delete(job.jobId);
      logger.info("job_cleaned", { jobId: job.jobId });
    }

    let entries = [];
    try { entries = await fs.readdir(this.storage.rootDir, { withFileTypes: true }); } catch { return; }
    for (const entry of entries) {
      if (!entry.isDirectory() || this.store.get(entry.name)) continue;
      const fullPath = `${this.storage.rootDir}/${entry.name}`;
      let stat;
      try { stat = await fs.stat(fullPath); } catch { continue; }
      if (stat.mtimeMs < cutoff) {
        await this.storage.removeJobDirectory(fullPath);
        logger.info("orphan_job_directory_cleaned", { name: entry.name });
      }
    }
  }
}
