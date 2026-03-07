/**
 * Application Configuration
 *
 * Centralized configuration for the Finance App frontend.
 * Allows switching between mock data (dev mode) and real API data (production).
 *
 * Usage:
 * - In development: Use mock data for fast iteration without backend
 * - In production: Use real data from the API server
 *
 * Set the DATA_SOURCE environment variable to control behavior:
 * - DATA_SOURCE=mock → Use mock data from mocks/dashboard-mock-data.ts
 * - DATA_SOURCE=api → Use real data from the API (default)
 */

// ============================================================================
// TYPES
// ============================================================================

export type DataSource = 'mock' | 'api';

export interface AppConfig {
  /**
   * Where to get widget data from
   */
  dataSource: DataSource;

  /**
   * Enable debug logging
   */
  debug: boolean;

  /**
   * Widget version
   */
  version: string;
}

// ============================================================================
// ENVIRONMENT DETECTION
// ============================================================================

/**
 * Get environment variable from multiple sources
 */
export function getEnvVar(key: string): string | undefined {
  try {
    // Try import.meta.env (Vite/ESM) - wrapped in try-catch for IIFE compatibility
    // Note: import.meta is not available in IIFE format, so this will fail gracefully
    if ((globalThis as any).import?.meta?.env?.[key]) {
      return (globalThis as any).import.meta.env[key] as string;
    }
  } catch {
    // import.meta not available in IIFE format
  }
  // Try process.env (Node.js)
  if (typeof process !== 'undefined' && process.env?.[key]) {
    return process.env[key];
  }
  // Try window.__ENV__ (injected by build script)
  if (typeof window !== 'undefined' && (window as any).__ENV__?.[key]) {
    return (window as any).__ENV__[key];
  }
  return undefined;
}

/**
 * Detect if we're running in development mode
 */
function isDevelopment(): boolean {
  // Check if we're in a dev environment
  return getEnvVar('MODE') === 'development' || getEnvVar('NODE_ENV') === 'development';
}

/**
 * Get data source from environment or auto-detect
 */
function getDataSource(): DataSource {
  // Explicit environment variable takes precedence
  const envSource = getEnvVar('DATA_SOURCE');
  if (envSource === 'mock' || envSource === 'api') {
    return envSource;
  }

  // Auto-detect based on environment
  if (isDevelopment()) {
    return 'mock';
  }

  // Default to API mode in production
  return 'api';
}

/**
 * Enable debug mode based on environment
 */
function isDebugEnabled(): boolean {
  return getEnvVar('DEBUG') === 'true' || isDevelopment();
}

// ============================================================================
// CONFIGURATION
// ============================================================================

/**
 * Application configuration object
 */
export const config: AppConfig = {
  dataSource: getDataSource(),
  debug: isDebugEnabled(),
  version: '1.0.0',
};

// ============================================================================
// HELPERS
// ============================================================================

/**
 * Check if we're using mock data
 */
export function isUsingMockData(): boolean {
  return config.dataSource === 'mock';
}

/**
 * Check if we're using tool data
 */
export function isUsingApiData(): boolean {
  return config.dataSource === 'api';
}

/**
 * Log configuration on startup (if debug enabled)
 */
if (config.debug) {
  console.log('[Config] Application configuration:', {
    dataSource: config.dataSource,
    debug: config.debug,
    version: config.version,
    environment: isDevelopment() ? 'development' : 'production',
  });
}
