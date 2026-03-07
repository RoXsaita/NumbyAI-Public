/**
 * Validation Helpers - Runtime Data Validation
 *
 * Wraps Zod validation with logging and error handling.
 * Ensures that data from the API matches our schema.
 *
 * Benefits:
 * - Fail fast on bad data
 * - Detailed error logs for debugging
 * - Type-safe data after validation
 * - Centralized validation logic
 */

import { createLogger, classifyError, type ErrorType } from '../shared/logger';
import {
  validateDashboardProps,
  type DashboardProps,
  type ValidationResult,
} from '../shared/schemas';

const logger = createLogger('validation');

// ============================================================================
// VALIDATION WITH LOGGING
// ============================================================================

/**
 * Validate dashboard props with detailed logging
 */
export function validateAndLogDashboardProps(
  data: unknown,
  context: string = 'unknown'
): ValidationResult<DashboardProps> {
  logger.debug('Validating dashboard props', {
    context,
    hasData: data !== null && data !== undefined,
  });

  const result = validateDashboardProps(data);

  if (result.success) {
    logger.info('Validation succeeded', {
      context,
      transaction_count: result.data.transactions.length,
      metrics: {
        inflows: result.data.metrics.inflows,
        outflows: result.data.metrics.outflows,
        net_cash: result.data.metrics.net_cash,
      },
    });
  } else {
    logger.validationError(context, result.error, data);
  }

  return result;
}

/**
 * Get a user-friendly error message from a validation error
 */
export function getValidationErrorMessage(error: any): string {
  if (!error || !error.issues) {
    return 'Invalid data structure received from the API.';
  }

  // Get the first few issues
  const issues = error.issues.slice(0, 3);
  const messages = issues.map((issue: any) => {
    const path = issue.path.join('.');
    return `${path}: ${issue.message}`;
  });

  let message = 'Data validation failed:\n' + messages.join('\n');

  if (error.issues.length > 3) {
    message += `\n... and ${error.issues.length - 3} more issue(s)`;
  }

  return message;
}

/**
 * Classify validation error for structured error handling
 */
export function getValidationErrorType(error: any): ErrorType {
  return classifyError(error);
}

// ============================================================================
// VALIDATION GUARDS
// ============================================================================

/**
 * Check if data is likely valid dashboard props (quick check before full validation)
 */
export function looksLikeDashboardProps(data: unknown): boolean {
  if (!data || typeof data !== 'object') {
    return false;
  }

  const obj = data as Record<string, unknown>;

  // Quick structural checks
  return (
    obj.kind === 'dashboard' &&
    typeof obj.statement === 'object' &&
    Array.isArray(obj.transactions) &&
    typeof obj.metrics === 'object'
  );
}
