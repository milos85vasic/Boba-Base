/**
 * @fileoverview Structured logging utility for BobaLink.
 *
 * Provides a centralized logging system with log levels, contextual prefixes,
 * and debug mode support. All log output respects the user's debug mode setting
 * and includes timestamps and context identifiers.
 *
 * @module shared/logger
 */

/** Log levels ordered by severity. */
type LogLevel = "debug" | "info" | "warn" | "error";

/** Numeric severity for each log level. */
const LEVEL_SEVERITY: Readonly<Record<LogLevel, number>> = {
  debug: 0,
  info: 1,
  warn: 2,
  error: 3,
};

/** Current minimum log level. Set to "debug" when debug mode is enabled. */
let currentMinLevel: LogLevel = "info";

/** Whether debug mode is currently active. */
let debugEnabled = false;

/**
 * Initialize the logger with the current configuration.
 * Called when the extension loads or when config changes.
 *
 * @param isDebug - Whether debug mode should be enabled
 */
export function initLogger(isDebug: boolean): void {
  debugEnabled = isDebug;
  currentMinLevel = isDebug ? "debug" : "info";
}

/**
 * Format a log message with timestamp and context prefix.
 *
 * @param level - The log level
 * @param context - The component context (e.g., "scanner", "api")
 * @param message - The message to format
 * @returns Formatted log string
 */
function formatMessage(level: LogLevel, context: string, message: string): string {
  const timestamp = new Date().toISOString();
  const levelUpper = level.toUpperCase().padStart(5, " ");
  return `[${timestamp}] [${levelUpper}] [${context}] ${message}`;
}

/**
 * Check if a log level should be emitted based on current minimum.
 *
 * @param level - Level to check
 * @returns True if the level should be logged
 */
function shouldLog(level: LogLevel): boolean {
  return LEVEL_SEVERITY[level] >= LEVEL_SEVERITY[currentMinLevel];
}

/**
 * Log a debug message. Only shown when debug mode is enabled.
 *
 * @param context - The component context
 * @param message - The message to log
 * @param data - Optional data to include
 */
export function debug(context: string, message: string, data?: unknown): void {
  if (!shouldLog("debug")) return;
  console.debug(formatMessage("debug", context, message), data ?? "");
}

/**
 * Log an informational message.
 *
 * @param context - The component context
 * @param message - The message to log
 * @param data - Optional data to include
 */
export function info(context: string, message: string, data?: unknown): void {
  if (!shouldLog("info")) return;
  console.info(formatMessage("info", context, message), data ?? "");
}

/**
 * Log a warning message.
 *
 * @param context - The component context
 * @param message - The message to log
 * @param data - Optional data to include
 */
export function warn(context: string, message: string, data?: unknown): void {
  if (!shouldLog("warn")) return;
  console.warn(formatMessage("warn", context, message), data ?? "");
}

/**
 * Log an error message. Always shown.
 *
 * @param context - The component context
 * @param message - The message to log
 * @param error - Optional error object or data
 */
export function error(context: string, message: string, error?: unknown): void {
  if (!shouldLog("error")) return;
  console.error(formatMessage("error", context, message), error ?? "");
}

/**
 * Log the start of an async operation and return an end function.
 * Usage: const end = timed("context", "Operation name"); ...; end();
 *
 * @param context - The component context
 * @param operation - Description of the operation
 * @returns Function to call when the operation completes
 */
export function timed(context: string, operation: string): () => void {
  const startTime = performance.now();
  debug(context, `${operation} started`);

  return (): void => {
    const duration = Math.round(performance.now() - startTime);
    debug(context, `${operation} completed in ${duration}ms`);
  };
}

/**
 * Create a contextual logger bound to a specific component.
 * All log calls include the component prefix automatically.
 *
 * @param context - The component name (e.g., "APIClient", "Scanner")
 * @returns Object with bound log methods
 *
 * @example
 * ```typescript
 * const log = createLogger("MagnetParser");
 * log.info("Parsing magnet link...");
 * log.error("Failed to parse", new Error("Invalid format"));
 * ```
 */
export function createLogger(context: string) {
  return {
    debug: (message: string, data?: unknown): void => debug(context, message, data),
    info: (message: string, data?: unknown): void => info(context, message, data),
    warn: (message: string, data?: unknown): void => warn(context, message, data),
    error: (message: string, errorData?: unknown): void =>
      error(context, message, errorData),
    timed: (operation: string): (() => void) => timed(context, operation),
  };
}

/** Type of a contextual logger returned by createLogger. */
export type Logger = ReturnType<typeof createLogger>;

/**
 * Check if debug mode is currently enabled.
 *
 * @returns True if debug mode is active
 */
export function isDebugEnabled(): boolean {
  return debugEnabled;
}
