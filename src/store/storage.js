import fs from "node:fs/promises";
import path from "node:path";
import { env } from "../config/env.js";
import { assertInside, ensureDir, safeBaseName } from "../utils/paths.js";

export class LocalJobStorage {
  constructor(rootDir = env.tempDir) {
    this.rootDir = rootDir;
  }

  async init() {
    await ensureDir(this.rootDir);
  }

  async createJobDirectory(jobId) {
    const jobDir = assertInside(this.rootDir, path.join(this.rootDir, jobId));
    await fs.mkdir(jobDir, { recursive: false });
    return jobDir;
  }

  getInputPath(jobDir, originalName) {
    const extension = path.extname(originalName).toLowerCase();
    return assertInside(jobDir, path.join(jobDir, `input${extension}`));
  }

  getOutputPath(jobDir, originalName) {
    const baseName = path.parse(safeBaseName(originalName)).name;
    return assertInside(jobDir, path.join(jobDir, `${baseName}-upscaled.mp4`));
  }

  async removeJobDirectory(jobDir) {
    await fs.rm(jobDir, { recursive: true, force: true });
  }

  async outputExists(outputPath) {
    try {
      const stat = await fs.stat(outputPath);
      return stat.isFile() && stat.size > 0;
    } catch {
      return false;
    }
  }
}
