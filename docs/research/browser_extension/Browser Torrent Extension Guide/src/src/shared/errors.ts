/**
 * @fileoverview Custom error classes for BobaLink.
 *
 * Provides domain-specific error types with structured context,
 * HTTP status codes, and user-friendly messages for consistent
 * error handling throughout the extension.
 *
 * @module shared/errors
 */

/**
 * Base error class for all BobaLink-specific errors.
 * Extends Error with additional context for debugging and user feedback.
 */
export class BobaLinkError extends Error {
  /** Error code for programmatic handling */
  readonly code: string;

  /** HTTP status code if applicable, null otherwise */
  readonly statusCode: number | null;

  /** Whether this error is recoverable (user can retry) */
  readonly recoverable: boolean;

  /** Original error that caused this, if any */
  readonly cause: Error | null;

  /** Additional context data for debugging */
  readonly context: Readonly<Record<string, unknown>>;

  constructor(
    message: string,
    options: {
      code?: string;
      statusCode?: number | null;
      recoverable?: boolean;
      cause?: Error | null;
      context?: Record<string, unknown>;
    } = {},
  ) {
    super(message);
    this.name = "BobaLinkError";
    this.code = options.code ?? "BOBA_UNKNOWN";
    this.statusCode = options.statusCode ?? null;
    this.recoverable = options.recoverable ?? false;
    this.cause = options.cause ?? null;
    this.context = Object.freeze({ ...(options.context ?? {}) });

    // Maintain proper prototype chain for instanceof checks
    Object.setPrototypeOf(this, BobaLinkError.prototype);
  }

  /**
   * Get a user-friendly error message for display in the UI.
   *
   * @returns Human-readable error message
   */
  getUserMessage(): string {
    return this.message;
  }

  /**
   * Get detailed error info for debugging/logging.
   *
   * @returns Structured error details
   */
  toJSON(): Record<string, unknown> {
    return {
      name: this.name,
      code: this.code,
      message: this.message,
      statusCode: this.statusCode,
      recoverable: this.recoverable,
      context: this.context,
      cause: this.cause?.message ?? null,
      stack: this.stack,
    };
  }
}

/**
 * Error thrown when authentication fails.
 */
export class AuthError extends BobaLinkError {
  constructor(
    message: string,
    options: {
      statusCode?: number;
      cause?: Error;
      context?: Record<string, unknown>;
    } = {},
  ) {
    super(message, {
      code: "BOBA_AUTH_FAILED",
      statusCode: options.statusCode ?? 401,
      recoverable: true,
      cause: options.cause ?? null,
      context: options.context ?? {},
    });
    this.name = "AuthError";
    Object.setPrototypeOf(this, AuthError.prototype);
  }

  override getUserMessage(): string {
    return `Authentication failed: ${this.message}. Please check your credentials in the extension options.`;
  }
}

/**
 * Error thrown when a network request fails.
 */
export class NetworkError extends BobaLinkError {
  constructor(
    message: string,
    options: {
      statusCode?: number | null;
      cause?: Error;
      context?: Record<string, unknown>;
    } = {},
  ) {
    super(message, {
      code: "BOBA_NETWORK_ERROR",
      statusCode: options.statusCode ?? null,
      recoverable: true,
      cause: options.cause ?? null,
      context: options.context ?? {},
    });
    this.name = "NetworkError";
    Object.setPrototypeOf(this, NetworkError.prototype);
  }

  override getUserMessage(): string {
    return `Connection failed: ${this.message}. Please check that the server is running and the URL is correct.`;
  }
}

/**
 * Error thrown when a torrent operation fails.
 */
export class TorrentError extends BobaLinkError {
  constructor(
    message: string,
    options: {
      statusCode?: number;
      cause?: Error;
      context?: Record<string, unknown>;
    } = {},
  ) {
    super(message, {
      code: "BOBA_TORRENT_ERROR",
      statusCode: options.statusCode ?? 400,
      recoverable: true,
      cause: options.cause ?? null,
      context: options.context ?? {},
    });
    this.name = "TorrentError";
    Object.setPrototypeOf(this, TorrentError.prototype);
  }

  override getUserMessage(): string {
    return `Torrent error: ${this.message}`;
  }
}

/**
 * Error thrown when parsing fails (magnet, bencode, etc.).
 */
export class ParseError extends BobaLinkError {
  constructor(
    message: string,
    options: {
      cause?: Error;
      context?: Record<string, unknown>;
    } = {},
  ) {
    super(message, {
      code: "BOBA_PARSE_ERROR",
      statusCode: null,
      recoverable: false,
      cause: options.cause ?? null,
      context: options.context ?? {},
    });
    this.name = "ParseError";
    Object.setPrototypeOf(this, ParseError.prototype);
  }

  override getUserMessage(): string {
    return `Failed to parse: ${this.message}`;
  }
}

/**
 * Error thrown when configuration is invalid.
 */
export class ConfigError extends BobaLinkError {
  constructor(
    message: string,
    options: {
      cause?: Error;
      context?: Record<string, unknown>;
    } = {},
  ) {
    super(message, {
      code: "BOBA_CONFIG_ERROR",
      statusCode: null,
      recoverable: true,
      cause: options.cause ?? null,
      context: options.context ?? {},
    });
    this.name = "ConfigError";
    Object.setPrototypeOf(this, ConfigError.prototype);
  }

  override getUserMessage(): string {
    return `Configuration error: ${this.message}. Please check your settings.`;
  }
}

/**
 * Error thrown when storage operations fail.
 */
export class StorageError extends BobaLinkError {
  constructor(
    message: string,
    options: {
      cause?: Error;
      context?: Record<string, unknown>;
    } = {},
  ) {
    super(message, {
      code: "BOBA_STORAGE_ERROR",
      statusCode: null,
      recoverable: true,
      cause: options.cause ?? null,
      context: options.context ?? {},
    });
    this.name = "StorageError";
    Object.setPrototypeOf(this, StorageError.prototype);
  }
}

/**
 * Error thrown when rate limiting is triggered.
 */
export class RateLimitError extends BobaLinkError {
  /** When the rate limit will reset */
  readonly retryAfter: number;

  constructor(
    message: string,
    retryAfter: number,
    options: {
      context?: Record<string, unknown>;
    } = {},
  ) {
    super(message, {
      code: "BOBA_RATE_LIMITED",
      statusCode: 429,
      recoverable: true,
      context: options.context ?? {},
    });
    this.name = "RateLimitError";
    this.retryAfter = retryAfter;
    Object.setPrototypeOf(this, RateLimitError.prototype);
  }

  override getUserMessage(): string {
    return `Rate limited: ${this.message}. Please wait ${Math.ceil(this.retryAfter / 1000)} seconds before retrying.`;
  }
}

/**
 * Error thrown when the server returns a non-success response.
 */
export class ServerError extends BobaLinkError {
  constructor(
    message: string,
    statusCode: number,
    options: {
      cause?: Error;
      context?: Record<string, unknown>;
    } = {},
  ) {
    super(message, {
      code: `BOBA_SERVER_${statusCode}`,
      statusCode,
      recoverable: statusCode >= 500 || statusCode === 429,
      cause: options.cause ?? null,
      context: options.context ?? {},
    });
    this.name = "ServerError";
    Object.setPrototypeOf(this, ServerError.prototype);
  }

  override getUserMessage(): string {
    return `Server error (${this.statusCode}): ${this.message}`;
  }
}

/**
 * Type guard to check if an unknown value is a BobaLinkError.
 *
 * @param value - Value to check
 * @returns True if the value is a BobaLinkError instance
 */
export function isBobaLinkError(value: unknown): value is BobaLinkError {
  return value instanceof BobaLinkError;
}

/**
 * Convert an unknown error into a BobaLinkError.
 * Normalizes Error objects, strings, and other values into our error type.
 *
 * @param error - The unknown error value
 * @param context - Additional context to attach
 * @returns A BobaLinkError instance
 */
export function normalizeError(
  error: unknown,
  context: Record<string, unknown> = {},
): BobaLinkError {
  if (error instanceof BobaLinkError) {
    return error;
  }

  if (error instanceof Error) {
    return new BobaLinkError(error.message, {
      cause: error,
      context,
      code: "BOBA_UNKNOWN",
      recoverable: true,
    });
  }

  const message =
    typeof error === "string" ? error : "An unknown error occurred";
  return new BobaLinkError(message, {
    context: { originalValue: error, ...context },
    code: "BOBA_UNKNOWN",
    recoverable: true,
  });
}
