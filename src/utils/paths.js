import path from "node:path";
import fs from "node:fs/promises";
import { AppError } from "./errors.js";

export async function ensureDir(dir) {
  await fs.mkdir(dir, { recursive: true });
}

export function assertInside(parentDir, candidatePath) {
  const parent = path.resolve(parentDir);
  const candidate = path.resolve(candidatePath);
  const prefix = parent.endsWith(path.sep) ? parent : `${parent}${path.sep}`;
  if (candidate !== parent && !candidate.startsWith(prefix)) {
    throw new AppError(400, "INVALID_PATH", "Resolved file path is outside the job directory.");
  }
  return candidate;
}

export function safeBaseName(originalName) {
  const parsed = path.parse(originalName || "video.mp4");
  const extension = parsed.ext.toLowerCase();
  return `${parsed.name.replace(/[^a-zA-Z0-9_-]+/g, "_").slice(0, 80) || "video"}${extension}`;
}
