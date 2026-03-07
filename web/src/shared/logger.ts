/**
 * Shared Logger - Structured Logging for Widgets
 *
 * Provides consistent logging across all widget components with:
 * - Log levels (debug, info, warn, error)
 * - Structured data logging
 * - Error classification for better debugging
 * - Development vs production modes
 */

// ============================================================================
// TYPES
// ============================================================================

export type LogLevel = 'debug' | 'info' | 'warn' | 'error';

export type ErrorType =
  | 'validation'
  | 'network'
  | 'parsing'
  | 'rendering'
  | 'unknown';

export interface LogContext {
  [key: string]: unknown;
}

export interface Logger {
  debug(message: string, context?: LogContext): void;
  info(message: string, context?: LogContext): void;
  warn(message: string, context?: LogContext): void;
  error(message: string, error?: Error | unknown, context?: LogContext): void;
  validationError(
    context: string,
    error: unknown,
    data?: unknown
  ): void;
}

// ============================================================================
// CONFIGURATION
// ============================================================================

const isDev =
  typeof process !== 'undefined'
    ? process.env.NODE_ENV !== 'production'
    : true;

const LOG_LEVELS: Record<LogLevel, number> = {
  debug: 0,
  info: 1,
  warn: 2,
  error: 3,
};

const MIN_LOG_LEVEL: LogLevel = isDev ? 'debug' : 'info';

// ============================================================================
// ERROR CLASSIFICATION
// ============================================================================

/**
 * Classify an error into a known error type for better handling
 */
export function classifyError(error: unknown): ErrorType {
  if (!error) return 'unknown';

  // Check for Zod validation errors
  if (
    typeof error === 'object' &&
    error !== null &&
    'issues' in error &&
    Array.isArray((error as { issues: unknown[] }).issues)
  ) {
    return 'validation';
  }

  // Check for fetch/network errors
  if (error instanceof TypeError && error.message.includes('fetch')) {
    return 'network';
  }

  // Check for JSON parsing errors
  if (error instanceof SyntaxError && error.message.includes('JSON')) {
    return 'parsing';
  }

  // Check for React rendering errors
  if (
    error instanceof Error &&
    (error.message.includes('React') ||
      error.message.includes('render') ||
      error.message.includes('component'))
  ) {
    return 'rendering';
  }

  return 'unknown';
}

/**
 * Get a user-friendly message for an error type
 */
export function getErrorTypeMessage(type: ErrorType): string {
  switch (type) {
    case 'validation':
      return 'Data validation failed. The received data does not match the expected format.';
    case 'network':
      return 'Network error. Unable to communicate with the server.';
    case 'parsing':
      return 'Parsing error. The response could not be parsed.';
    case 'rendering':
      return 'Rendering error. The component encountered an issue while displaying.';
    default:
      return 'An unexpected error occurred.';
  }
}

// ============================================================================
// LOGGER FACTORY
// ============================================================================

/**
 * Create a logger instance with a specific namespace
 */
export function createLogger(namespace: string): Logger {
  const shouldLog = (level: LogLevel): boolean => {
    return LOG_LEVELS[level] >= LOG_LEVELS[MIN_LOG_LEVEL];
  };

  const formatMessage = (level: LogLevel, message: string): string => {
    const timestamp = new Date().toISOString();
    return `[${timestamp}] [${level.toUpperCase()}] [${namespace}] ${message}`;
  };

  const logWithContext = (
    level: LogLevel,
    message: string,
    context?: LogContext
  ): void => {
    if (!shouldLog(level)) return;

    const formatted = formatMessage(level, message);
    const consoleMethod =
      level === 'error'
        ? console.error
        : level === 'warn'
        ? console.warn
        : level === 'debug'
        ? console.debug
        : console.log;

    if (context && Object.keys(context).length > 0) {
      consoleMethod(formatted, context);
    } else {
      consoleMethod(formatted);
    }
  };

  return {
    debug(message: string, context?: LogContext): void {
      logWithContext('debug', message, context);
    },

    info(message: string, context?: LogContext): void {
      logWithContext('info', message, context);
    },

    warn(message: string, context?: LogContext): void {
      logWithContext('warn', message, context);
    },

    error(
      message: string,
      error?: Error | unknown,
      context?: LogContext
    ): void {
      const errorType = classifyError(error);
      const errorContext: LogContext = {
        ...context,
        errorType,
        errorMessage:
          error instanceof Error ? error.message : String(error),
      };

      if (error instanceof Error && error.stack) {
        errorContext.stack = error.stack;
      }

      logWithContext('error', message, errorContext);
    },

    validationError(
      ctx: string,
      error: unknown,
      data?: unknown
    ): void {
      const issues =
        error && typeof error === 'object' && 'issues' in error
          ? (error as { issues: unknown[] }).issues
          : [];

      logWithContext('error', `Validation failed in ${ctx}`, {
        issueCount: issues.length,
        issues: issues.slice(0, 5), // First 5 issues
        dataSnapshot: data
          ? JSON.stringify(data).slice(0, 500)
          : undefined,
      });
    },
  };
}

// ============================================================================
// DEFAULT LOGGER
// ============================================================================

export const logger = createLogger('widget');

