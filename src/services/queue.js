import { logger } from "../utils/logger.js";

export class JobQueue {
  constructor({ concurrency = 1 } = {}) {
    this.concurrency = Math.max(1, concurrency);
    this.active = 0;
    this.items = [];
  }

  async enqueue(task, meta = {}) {
    this.items.push({ task, meta });
    this.drain();
  }

  drain() {
    while (this.active < this.concurrency && this.items.length > 0) {
      const item = this.items.shift();
      this.active += 1;
      Promise.resolve()
        .then(item.task)
        .catch((error) => logger.error("queue_task_uncaught_error", { jobId: item.meta.jobId, error: error instanceof Error ? error.message : String(error) }))
        .finally(() => {
          this.active -= 1;
          this.drain();
        });
    }
  }

  stats() {
    return { queued: this.items.length, active: this.active, concurrency: this.concurrency };
  }
}
