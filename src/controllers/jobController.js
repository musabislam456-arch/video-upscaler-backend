import fs from "node:fs";
import { AppError } from "../utils/errors.js";
import { validateQuality, validateScale, validateUploadedFile, validateVideoSignature } from "../utils/validation.js";

export function createJobController(jobService) {
  return {
    create: async (req, res) => {
      try {
        const extension = validateUploadedFile(req.file);
        await validateVideoSignature(req.file.path, extension);
        const scale = validateScale(req.body.scale);
        const quality = validateQuality(req.body.quality);
        const response = await jobService.createJob({ file: req.file, scale, quality });
        res.status(202).json(response);
      } catch (error) {
        if (req.file?.path) {
          try { await fs.promises.unlink(req.file.path); } catch { /* best effort cleanup */ }
        }
        throw error;
      }
    },
    get: (req, res) => res.json(jobService.getJob(req.params.jobId)),
    progress: (req, res) => res.json(jobService.getProgress(req.params.jobId)),
    download: (req, res, next) => {
      const { path, fileName } = jobService.getDownload(req.params.jobId);
      res.download(path, fileName, (error) => {
        if (error && !res.headersSent) {
          next(new AppError(500, "DOWNLOAD_FAILED", "Unable to stream the output file."));
        }
      });
    },
  };
}
