import { ApiError } from "@/api/client";

export function isNotFound(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404;
}

export function asApiError(
  error: unknown,
  fallback = "The Martini Shot API could not be reached.",
): ApiError {
  if (error instanceof ApiError) return error;
  return new ApiError("network_error", fallback, 0);
}
