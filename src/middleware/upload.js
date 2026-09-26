import multer from "multer";
import os from "node:os";
import path from "node:path";
import { env } from "../config/env.js";
import { AppError } from "../utils/errors.js";
import { VIDEO_EXTENSIONS } from "../config/constants.js";

const tempUploadDir = path.join(os.tmpdir(), "video-upscaler-uploads");

export const upload = multer({
  dest: tempUploadDir,
  limits: {
    fileSize: env.maxUploadSizeMb * 1024 * 1024,
    files: 1,
  },
  fileFilter: (_req, file, cb) => {
    const extension = path.extname(file.originalname || "").toLowerCase();
    if (!VIDEO_EXTENSIONS[extension]) {
      cb(new AppError(415, "UNSUPPORTED_VIDEO_FORMAT", "Unsupported video format."));
      return;
    }
    cb(null, true);
  },
});
