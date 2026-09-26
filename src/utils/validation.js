import path from "node:path";
import fs from "node:fs/promises";
import { QUALITY_OPTIONS, SCALE_OPTIONS, VIDEO_EXTENSIONS } from "../config/constants.js";
import { AppError } from "./errors.js";

export function validateScale(value) {
  if (!SCALE_OPTIONS.includes(value)) {
    throw new AppError(400, "INVALID_SCALE", `Scale must be one of: ${SCALE_OPTIONS.join(", ")}.`);
  }
  return value;
}

export function validateQuality(value) {
  if (!QUALITY_OPTIONS.includes(value)) {
    throw new AppError(400, "INVALID_QUALITY", `Quality must be one of: ${QUALITY_OPTIONS.join(", ")}.`);
  }
  return value;
}

export function validateUploadedFile(file) {
  if (!file) throw new AppError(400, "VIDEO_REQUIRED", "A video file is required in the 'video' form field.");
  const extension = path.extname(file.originalname || "").toLowerCase();
  const expectedMime = VIDEO_EXTENSIONS[extension];
  if (!expectedMime) {
    throw new AppError(415, "UNSUPPORTED_VIDEO_FORMAT", "Unsupported video extension.");
  }

  const allowedMime = new Set(Object.values(VIDEO_EXTENSIONS));
  if (file.mimetype && !allowedMime.has(file.mimetype)) {
    throw new AppError(415, "UNSUPPORTED_VIDEO_MIME", "Unsupported uploaded video MIME type.");
  }

  return extension;
}

export async function validateVideoSignature(filePath, extension) {
  const handle = await fs.open(filePath, "r");
  try {
    const buffer = Buffer.alloc(16);
    const { bytesRead } = await handle.read(buffer, 0, buffer.length, 0);
    if (bytesRead < 8) {
      throw new AppError(415, "INVALID_VIDEO_FILE", "Uploaded file is too small to be a valid video.");
    }

    const ascii4 = buffer.subarray(0, 4).toString("ascii");
    const boxType = buffer.subarray(4, 8).toString("ascii");
    const isIsoBaseMedia = boxType === "ftyp" || boxType === "wide" || boxType === "mdat";
    const isRiffAvi = ascii4 === "RIFF" && buffer.subarray(8, 12).toString("ascii") === "AVI ";
    const isEbml = buffer.subarray(0, 4).equals(Buffer.from([0x1A, 0x45, 0xDF, 0xA3]));

    if (extension === ".avi" && !isRiffAvi) {
      throw new AppError(415, "INVALID_VIDEO_SIGNATURE", "The uploaded AVI file signature does not match its extension.");
    }
    if ([".mp4", ".mov"].includes(extension) && !isIsoBaseMedia) {
      throw new AppError(415, "INVALID_VIDEO_SIGNATURE", "The uploaded MP4/MOV file signature does not match its extension.");
    }
    if ([".mkv", ".webm"].includes(extension) && !isEbml) {
      throw new AppError(415, "INVALID_VIDEO_SIGNATURE", "The uploaded MKV/WebM file signature does not match its extension.");
    }
  } finally {
    await handle.close();
  }
}
