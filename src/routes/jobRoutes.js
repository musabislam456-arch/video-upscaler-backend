import { Router } from "express";
import { upload } from "../middleware/upload.js";

export function buildJobRoutes(controller) {
  const router = Router();
  router.post("/", upload.single("video"), controller.create);
  router.get("/:jobId", controller.get);
  router.get("/:jobId/progress", controller.progress);
  router.get("/:jobId/download", controller.download);
  return router;
}
