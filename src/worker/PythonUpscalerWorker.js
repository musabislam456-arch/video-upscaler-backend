import { spawn } from "node:child_process";
import fs from "node:fs/promises";
import path from "node:path";
import { env } from "../config/env.js";
import { AppError } from "../utils/errors.js";
import { WorkerContract } from "./WorkerContract.js";

function appendArgScale(args, scale) {
  if (scale === "2x") {
    args.push("--scale", "2");
  } else if (scale === "4x") {
    args.push("--scale", "4");
  } else if (scale === "1080p") {
    args.push("--height", "1080");
  } else if (scale === "1440p") {
    args.push("--height", "1440");
  } else if (scale === "4K") {
    args.push("--height", "2160");
  } else {
    throw new AppError(400, "INVALID_SCALE", "Unsupported scale option.");
  }
}

function parseEngineProgress(text) {
  const match = text.match(/Progress:\s*([0-9]+(?:\.[0-9]+)?)%.*?Speed:\s*([^\s|]+)/);
  if (!match) return null;
  const progress = Number(match[1]);
  const speed = match[2];
  return {
    progress: Number.isFinite(progress) ? progress : null,
    status: `Encoding · ${speed}`,
  };
}

/**
 * Adapter for the supplied ai_studio_code.py.
 *
 * Current CLI:
 *   python ai_studio_code.py -i <input> -o <output> [--scale 2|4 | --height 1080|1440|2160] --quality <quality>
 *
 * The engine writes human-readable progress updates using carriage returns.
 * We parse those updates without requiring any changes to the engine's CLI.
 */
export class PythonUpscalerWorker extends WorkerContract {
  async run({ job, inputPath, outputPath, updateProgress, signal }) {
    if (!env.pythonEngineEnabled) {
      throw new AppError(503, "ENGINE_DISABLED", "Python upscaling engine is disabled.");
    }

    await fs.access(env.pythonEnginePath);
    await fs.mkdir(path.dirname(outputPath), { recursive: true });

    const args = [
      env.pythonEnginePath,
      "-i", inputPath,
      "-o", outputPath,
      "--quality", job.quality,
    ];
    appendArgScale(args, job.scale);

    updateProgress({ progress: 3, status: "Starting CPU upscaling engine" });

    const child = spawn(env.pythonExecutable, args, {
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true,
      signal,
    });

    let stderr = "";
    let outputBuffer = "";

    await new Promise((resolve, reject) => {
      const timeout = env.pythonEngineTimeoutMs > 0
        ? setTimeout(() => {
            child.kill("SIGTERM");
            reject(new AppError(504, "ENGINE_TIMEOUT", "Python upscaling worker timed out."));
          }, env.pythonEngineTimeoutMs)
        : null;

      const consume = (chunk) => {
        outputBuffer += chunk.toString("utf8");
        const parts = outputBuffer.split(/[\r\n]+/);
        outputBuffer = parts.pop() || "";

        for (const part of parts) {
          const parsed = parseEngineProgress(part);
          if (!parsed || parsed.progress == null) continue;
          const mapped = 5 + (Math.min(100, Math.max(0, parsed.progress)) * 0.95);
          updateProgress({
            progress: Math.min(100, mapped),
            status: parsed.status,
          });
        }
      };

      child.stdout.on("data", consume);
      child.stderr.on("data", (chunk) => {
        stderr = (stderr + chunk.toString("utf8")).slice(-8000);
      });

      child.once("error", (error) => {
        if (timeout) clearTimeout(timeout);
        reject(new AppError(500, "ENGINE_START_FAILED", "Unable to start the Python upscaling process.", error.message));
      });

      child.once("close", (code) => {
        if (timeout) clearTimeout(timeout);
        if (outputBuffer) consume("\n");
        if (code === 0) resolve();
        else if (code === null && signal.aborted) reject(new AppError(499, "ENGINE_ABORTED", "Python upscaling process was aborted."));
        else reject(new AppError(500, "ENGINE_PROCESS_FAILED", `Python engine exited with code ${code}.`, stderr.trim().slice(-4000)));
      });
    });

    if (!(await fileIsReady(outputPath))) {
      throw new AppError(500, "ENGINE_OUTPUT_MISSING", "Python engine finished without producing a non-empty output file.");
    }

    updateProgress({ progress: 99.5, status: "Validating output" });
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
