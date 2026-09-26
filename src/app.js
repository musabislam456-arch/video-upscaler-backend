import cors from "cors";
import express from "express";
import helmet from "helmet";
import rateLimit from "express-rate-limit";
import morgan from "morgan";
import { env } from "./config/env.js";
import { buildJobRoutes } from "./routes/jobRoutes.js";
import { createJobController } from "./controllers/jobController.js";
import { notFoundHandler, errorHandler } from "./middleware/errorHandler.js";
import { requestId } from "./middleware/requestId.js";
import { logger } from "./utils/logger.js";
import { AppError } from "./utils/errors.js";

export function createApp({ jobService, queue }) {
  const app = express();

  app.disable("x-powered-by");
  app.set("trust proxy", 1);
  app.use(requestId);
  app.use(helmet({ crossOriginResourcePolicy: { policy: "cross-origin" } }));
  app.use(cors({
    origin(origin, callback) {
      const normalizedOrigin = String(origin || "").replace(/\/$/, "");
      const exactAllowed = !normalizedOrigin || env.frontendOrigins.includes(normalizedOrigin);
      const patternAllowed = normalizedOrigin && env.frontendOriginPatterns.some((pattern) => {
        if (pattern === "*") return true;
        if (pattern.startsWith("*.")) return normalizedOrigin.endsWith(pattern.slice(1));
        if (pattern.endsWith(".*")) return normalizedOrigin.startsWith(pattern.slice(0, -1));
        return normalizedOrigin === pattern;
      });
      if (exactAllowed || patternAllowed) return callback(null, true);
      logger.warn("cors_origin_rejected", { origin: normalizedOrigin, allowedOrigins: env.frontendOrigins, allowedPatterns: env.frontendOriginPatterns });
      return callback(new AppError(403, "CORS_ORIGIN_NOT_ALLOWED", "Origin is not allowed by the API CORS policy."));
    },
    methods: ["GET", "POST", "OPTIONS"],
    exposedHeaders: ["x-request-id"],
  }));
  app.use(express.json({ limit: "1mb" }));
  app.use(express.urlencoded({ extended: false, limit: "1mb" }));
  app.use(morgan((tokens, req, res) => JSON.stringify({
    ts: new Date().toISOString(),
    requestId: req.requestId,
    method: tokens.method(req),
    path: tokens.url(req),
    status: Number(tokens.status(res)),
    durationMs: Number(tokens["response-time"](req, res)),
  }), { stream: { write: (line) => logger.info("http_request", JSON.parse(line)) } }));

  app.use(rateLimit({
    windowMs: 60_000,
    limit: 120,
    standardHeaders: "draft-8",
    legacyHeaders: false,
  }));

  app.get("/health", (_req, res) => {
    const stats = queue.stats();
    res.json({ status: "ok", service: "video-upscaler-backend", queue: stats, timestamp: new Date().toISOString() });
  });

  app.use("/api/v1/jobs", buildJobRoutes(createJobController(jobService)));
  app.use(notFoundHandler);
  app.use(errorHandler);
  return app;
}
