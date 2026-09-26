import path from "node:path";
import process from "node:process";

function positiveInt(value, fallback, label) {
  const parsed = Number.parseInt(value ?? "", 10);
  if (!Number.isInteger(parsed) || parsed <= 0) {
    if (value == null || value === "") return fallback;
    throw new Error(`${label} must be a positive integer.`);
  }
  return parsed;
}

function nonNegativeInt(value, fallback, label) {
  const parsed = Number.parseInt(value ?? "", 10);
  if (!Number.isInteger(parsed) || parsed < 0) {
    if (value == null || value === "") return fallback;
    throw new Error(`${label} must be a non-negative integer.`);
  }
  return parsed;
}

function normalizeOrigin(value) {
  return String(value || "").trim().replace(/\/$/, "");
}

const origins = (process.env.FRONTEND_ORIGINS || "http://localhost:3000")
  .split(",")
  .map(normalizeOrigin)
  .filter(Boolean);

const originPatterns = (process.env.FRONTEND_ORIGIN_PATTERNS || "")
  .split(",")
  .map(normalizeOrigin)
  .filter(Boolean);

const tempDir = process.env.TEMP_DIR || "./storage/jobs";
const pythonEnginePath = process.env.PYTHON_ENGINE_PATH || "./ai_studio_code.py";

export const env = {
  nodeEnv: process.env.NODE_ENV || "development",
  port: positiveInt(process.env.PORT, 8080, "PORT"),
  frontendOrigins: origins,
  maxUploadSizeMb: positiveInt(process.env.MAX_UPLOAD_SIZE_MB, 500, "MAX_UPLOAD_SIZE_MB"),
  maxConcurrentJobs: positiveInt(process.env.MAX_CONCURRENT_JOBS, 1, "MAX_CONCURRENT_JOBS"),
  jobTtlHours: positiveInt(process.env.JOB_TTL_HOURS, 24, "JOB_TTL_HOURS"),
  cleanupIntervalMs: positiveInt(process.env.CLEANUP_INTERVAL_MINUTES, 30, "CLEANUP_INTERVAL_MINUTES") * 60_000,
  tempDir: path.resolve(process.cwd(), tempDir),
  pythonEngineEnabled: String(process.env.PYTHON_ENGINE_ENABLED ?? "true").toLowerCase() === "true",
  pythonExecutable: process.env.PYTHON_EXECUTABLE || "python",
  pythonEnginePath: path.resolve(process.cwd(), pythonEnginePath),
  pythonEngineTimeoutMs: nonNegativeInt(process.env.PYTHON_ENGINE_TIMEOUT_MS, 86_400_000, "PYTHON_ENGINE_TIMEOUT_MS"),
};

if (env.nodeEnv === "production" && env.frontendOrigins.includes("*")) {
  throw new Error("FRONTEND_ORIGINS=* is not allowed in production.");
}
