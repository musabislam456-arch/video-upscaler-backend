import { spawn } from "node:child_process";
import fs from "node:fs/promises";
import path from "node:path";
import { env } from "../config/env.js";
import { AppError } from "../utils/errors.js";
import { WorkerContract } from "./WorkerContract.js";

/**
 * Adapter for the future ai_studio_code.py.
 *
 * The Python engine is NOT included in this repository.
 * When enabled, the adapter invokes:
 *   python <script> --input <path> --output <path> --scale <scale> --quality <quality> --job-id <id>
 *
 * The script may emit newline-delimited JSON progress events:
 *   {"type":"progress","progress":42,"status":"..."}
 *   {"type":"status","progress":42,"status":"..."}
 *   {"type":"error","code":"ENGINE_ERROR","message":"..."}
 *
 * The exact adapter can be adjusted later when the real script's interface is supplied.
 */
export class PythonUpscalerWorker extends WorkerContract {
  async run({ job, inputPath, outputPath, updateProgress, signal }) {
    if (!env.pythonEngineEnabled || !env.pythonEnginePath) {
      throw new AppError(503, "ENGINE_NOT_CONFIGURED", "Python upscaling engine is not configured yet. Add the supplied ai_studio_code.py and enable PYTHON_ENGINE_ENABLED.");
    }

    await fs.access(env.pythonEnginePath);
    await fs.mkdir(path.dirname(outputPath), { recursive: true });

    const args = [
      env.pythonEnginePath,
      "--input", inputPath,
      "--output", outputPath,
      "--scale", job.scale,
      "--quality", job.quality,
      "--job-id", job.jobId,
    ];

    const child = spawn(env.pythonExecutable, args, {
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true,
      signal,
    });

    let stderr = "";
    let stdoutBuffer = "";
    let settled = false;

    child.stdout.on("data", (chunk) => {
      stdoutBuffer += chunk.toString("utf8");
      const lines = stdoutBuffer.split(/\r?\n/);
      stdoutBuffer = lines.pop() || "";
      for (const line of lines) {
        if (!line.trim()) continue;
        try {
          const event = JSON.parse(line);
          if (event.type === "progress" || event.type === "status") {
            updateProgress({ progress: Number(event.progress), status: String(event.status || "Processing") });
          }
          if (event.type === "error") {
            stderr += `${event.code || "ENGINE_ERROR"}: ${event.message || "Engine error"}\n`;
          }
        } catch {
          // Human-readable engine output is ignored; structured JSON is the progress channel.
        }
      }
    });

    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString("utf8").slice(-4000);
    });

    await new Promise((resolve, reject) => {
      const timeout = env.pythonEngineTimeoutMs > 0 ? setTimeout(() => {
        child.kill("SIGTERM");
        reject(new AppError(504, "ENGINE_TIMEOUT", "Python upscaling worker timed out."));
      }, env.pythonEngineTimeoutMs) : null;

      child.once("error", (error) => {
        if (timeout) clearTimeout(timeout);
        reject(error);
      });
      child.once("close", (code) => {
        if (timeout) clearTimeout(timeout);
        if (code === 0) resolve();
        else reject(new AppError(500, "ENGINE_PROCESS_FAILED", `Python engine exited with code ${code}.`, stderr.trim().slice(-4000)));
      });
    });

    if (!(await fileIsReady(outputPath))) {
      throw new AppError(500, "ENGINE_OUTPUT_MISSING", "Python engine finished without producing the expected output file.");
    }

    if (!settled) settled = true;
    return { outputPath };
  }
}

async function fileIsReady(filePath) {
  try {
    const stat = await fs.stat(filePath);
    return stat.isFile() && stat.size > 0;
  } catch {
    return false;
  }
}
