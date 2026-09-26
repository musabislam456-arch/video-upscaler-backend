export class AppError extends Error {
  constructor(statusCode, code, message, details = undefined) {
    super(message);
    this.name = "AppError";
    this.statusCode = statusCode;
    this.code = code;
    this.details = details;
  }
}

export function asPublicError(error) {
  if (error instanceof AppError) {
    return { statusCode: error.statusCode, code: error.code, message: error.message };
  }
  return { statusCode: 500, code: "INTERNAL_ERROR", message: "An unexpected server error occurred." };
}
