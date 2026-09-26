import crypto from "node:crypto";

export function requestId(req, res, next) {
  const id = req.get("x-request-id")?.slice(0, 100) || crypto.randomUUID();
  res.setHeader("x-request-id", id);
  req.requestId = id;
  next();
}
