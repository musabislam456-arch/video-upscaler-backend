export const SCALE_OPTIONS = Object.freeze(["2x", "4x", "1080p", "1440p", "4K"]);
export const QUALITY_OPTIONS = Object.freeze(["fast", "balanced", "quality", "max"]);
export const JOB_STATES = Object.freeze(["queued", "processing", "completed", "failed"]);

export const VIDEO_EXTENSIONS = Object.freeze({
  ".mp4": "video/mp4",
  ".mov": "video/quicktime",
  ".mkv": "video/x-matroska",
  ".webm": "video/webm",
  ".avi": "video/x-msvideo",
});
