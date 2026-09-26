import { asPublicError } from "../utils/errors.js";
import { logger } from "../utils/logger.js";

export function notFoundHandler(req, res) {
  res.status(404).json({ error: { code: "ROUTE_NOT_FOUND", message: "Route not found." } });
}

export function errorHandler(error, req, res, next) {
  if (res.headersSent) return next(error);
  const publicError = asPublicError(error);
  logger.error("request_failed", { method: req.method, path: req.originalUrl, statusCode: publicError.statusCode, error: publicError.message });
  res.status(publicError.statusCode).json({
    error: {
      code: publicError.code,
      message: publicError.message,
      ...(publicError.details ? { details: publicError.details } : {}),
    },
  });
}
