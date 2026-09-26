import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import { env } from "../config/env.js";
import { AppError } from "../utils/errors.js";
import { logger } from "../utils/logger.js";

export class JobService {
  constructor({ store, storage, queue, worker }) {
    this.store = store;
    this.storage = storage;
    this.queue = queue;
    this.worker = worker;
  }

  async createJob({ file, scale, quality }) {
    const jobId = crypto.randomUUID();
    const jobDir = await this.storage.createJobDirectory(jobId);
    const inputPath = this.storage.getInputPath(jobDir, file.originalname);
    const outputPath = this.storage.getOutputPath(jobDir, file.originalname);

    try {
      await fs.rename(file.path, inputPath);
    } catch (error) {
      await this.storage.removeJobDirectory(jobDir);
      throw new AppError(500, "UPLOAD_SAVE_FAILED", "Unable to store the uploaded video.", error instanceof Error ? error.message : undefined);
    }

    const now = new Date().toISOString();
    const job = this.store.create({
      jobId,
      state: "queued",
      progress: 0,
      status: "Queued for processing",
      scale,
      quality,
      originalFileName: file.originalname,
      inputPath,
      outputPath,
      jobDir,
      outputFileName: null,
      createdAt: now,
      startedAt: null,
      completedAt: null,
      updatedAt: now,
      error: null,
    });

    await this.queue.enqueue(() => this.processJob(jobId), { jobId });
    logger.info("job_created", { jobId, scale, quality, originalFileName: file.originalname });
    return this.toResponse(job);
  }

  async processJob(jobId) {
    const job = this.store.get(jobId);
    if (!job) return;

    const startedAt = new Date().toISOString();
    this.store.update(jobId, { state: "processing", progress: 0, status: "Processing", startedAt, error: null });
    logger.info("job_processing_started", { jobId });

    try {
      const controller = new AbortController();
      const timer = env.pythonEngineTimeoutMs > 0 ? setTimeout(() => controller.abort(), env.pythonEngineTimeoutMs + 1000) : null;
      try {
        await this.worker.run({
          job,
          inputPath: job.inputPath,
          outputPath: job.outputPath,
          signal: controller.signal,
          updateProgress: ({ progress, status }) => {
            const normalized = Number.isFinite(Number(progress)) ? Math.min(100, Math.max(0, Number(progress))) : job.progress;
            this.store.update(jobId, { progress: normalized, status: status || "Processing" });
          },
        });
      } finally {
        if (timer) clearTimeout(timer);
      }

      const outputReady = await this.storage.outputExists(job.outputPath);
      if (!outputReady) throw new AppError(500, "OUTPUT_NOT_READY", "Worker completed but output file is missing or empty.");

      this.store.update(jobId, {
        state: "completed",
        progress: 100,
        status: "Completed",
        outputFileName: path.basename(job.outputPath),
        completedAt: new Date().toISOString(),
      });
      logger.info("job_completed", { jobId });
    } catch (error) {
      const publicError = error instanceof AppError
        ? { code: error.code, message: error.message }
        : { code: "WORKER_ERROR", message: "The processing worker failed." };
      this.store.update(jobId, {
        state: "failed",
        status: "Failed",
        error: publicError,
        completedAt: new Date().toISOString(),
      });
      logger.error("job_failed", { jobId, error: publicError, detail: error instanceof Error ? error.message : String(error) });
    }
  }

  getJob(jobId) {
    const job = this.store.get(jobId);
    if (!job) throw new AppError(404, "JOB_NOT_FOUND", "Job not found.");
    return this.toResponse(job);
  }

  getProgress(jobId) {
    const job = this.store.get(jobId);
    if (!job) throw new AppError(404, "JOB_NOT_FOUND", "Job not found.");
    return {
      jobId: job.jobId,
      state: job.state,
      progress: job.progress,
      status: job.status,
      updatedAt: job.updatedAt,
      error: job.error,
    };
  }

  getDownload(jobId) {
    const job = this.store.get(jobId);
    if (!job) throw new AppError(404, "JOB_NOT_FOUND", "Job not found.");
    if (job.state !== "completed") throw new AppError(409, "OUTPUT_NOT_READY", "The job has not completed successfully.");
    if (!job.outputPath) throw new AppError(404, "OUTPUT_MISSING", "Output file is not available.");
    return { path: job.outputPath, fileName: job.outputFileName || "upscaled-video.mp4" };
  }

  toResponse(job) {
    return {
      jobId: job.jobId,
      state: job.state,
      progress: job.progress,
      status: job.status,
      scale: job.scale,
      quality: job.quality,
      originalFileName: job.originalFileName,
      outputFileName: job.outputFileName,
      createdAt: job.createdAt,
      startedAt: job.startedAt,
      completedAt: job.completedAt,
      error: job.error,
      links: {
        status: `/api/v1/jobs/${job.jobId}`,
        progress: `/api/v1/jobs/${job.jobId}/progress`,
        download: job.state === "completed" ? `/api/v1/jobs/${job.jobId}/download` : null,
      },
    };
  }
}
