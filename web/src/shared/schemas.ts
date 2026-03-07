import { z } from 'zod';

/**
 * Shared dashboard schemas and types
 *
 * These mirror the Pydantic models in `mcp-server/app/schemas/dashboard.py`
 * and form the single source of truth for dashboard data contracts.
 *
 * Server:
 *   - Builds a `DashboardProps` object via Pydantic
 *   - Returns it from the REST API
 *
 * Client:
 *   - Validates API responses with `dashboardPropsSchema`
 */

// ============================================================================
// TRANSACTION
// ============================================================================

export const transactionSchema = z.object({
  id: z.string(),
  transaction_date: z.string(), // ISO 8601 date string
  description: z.string(),
  amount: z.number(), // Positive = inflow, Negative = outflow
  currency: z.string(),
  category: z.string(),

  // Optional fields
  merchant: z.string().optional(),
  notes: z.string().optional(),
  tags: z.array(z.string()).optional(),
});

export type Transaction = z.infer<typeof transactionSchema>;

// ============================================================================
// STATEMENT
// ============================================================================

export const statementSchema = z.object({
  id: z.string(),
  month: z.string(), // e.g. "2024-01" or "January 2024"
  bank: z.string().nullable().optional(),
  currency: z.string(),

  account_number: z.string().optional().nullable(),
  opening_balance: z.number().optional().nullable(),
  closing_balance: z.number().optional().nullable(),
});

export type Statement = z.infer<typeof statementSchema>;

// ============================================================================
// PIVOT + METRICS
// ============================================================================

export const coverageWindowSchema = z.object({
  start: z.string().nullable().optional(),
  end: z.string().nullable().optional(),
});

export type CoverageWindow = z.infer<typeof coverageWindowSchema>;

export const segmentMetricSchema = z.object({
  name: z.enum(['inflows', 'outflows', 'internal_transfers']),
  actual: z.number(),
  budget: z.number(),
  variance: z.number(),
  variance_pct: z.number(),
});

export type SegmentMetric = z.infer<typeof segmentMetricSchema>;

export const topVarianceSchema = z.object({
  category: z.string(),
  actual: z.number(),
  budget: z.number(),
  variance: z.number(),
  variance_pct: z.number(),
  direction: z.enum(['over', 'under']),
});

export type TopVariance = z.infer<typeof topVarianceSchema>;

export const initialFiltersSchema = z.object({
  bank_name: z.string().nullable().optional(),
  month_year: z.string().nullable().optional(),
  profile: z.string().nullable().optional(), // Household profile filter
  default_tab: z.string().nullable().optional(), // Default tab to show (e.g., "journey", "overview", "cashflow")
});

export type InitialFilters = z.infer<typeof initialFiltersSchema>;

export const pivotTableSchema = z.object({
  categories: z.array(z.string()),
  months: z.array(z.string()),
  actuals: z.array(z.array(z.number())),
  budgets: z.array(z.array(z.number())),
  transaction_counts: z.array(z.array(z.number())),
  category_totals: z.record(z.number()),
  category_budget_totals: z.record(z.number()),
  month_totals: z.record(z.number()),
  month_budget_totals: z.record(z.number()),
  category_shares: z.record(z.number()),
  currency: z.string(),
});

export type PivotTable = z.infer<typeof pivotTableSchema>;

export const metricsSchema = z.object({
  inflows: z.number(),
  outflows: z.number(),
  internal_transfers: z.number(),
  net_cash: z.number(),
  budget_coverage_pct: z.number(),
  latest_month: z.string().nullable().optional(),
  previous_month: z.string().nullable().optional(),
  month_over_month_delta: z.number().nullable().optional(),
  month_over_month_pct: z.number().nullable().optional(),
  segments: z.array(segmentMetricSchema),
  top_variances: z.array(topVarianceSchema),
});

export type Metrics = z.infer<typeof metricsSchema>;

export const categorySummaryDataSchema = z.object({
  category: z.string(),
  month: z.string(),
  bank: z.string(),
  amount: z.number(),
  count: z.number(),
  // Household profile (e.g., "Me", "Partner", "Joint")
  profile: z.string().optional().nullable(),
  // DEPRECATED: Category-level insights removed per issue #88 - use statement_insights instead
  // Keeping field for backward compatibility with existing data, but new saves set null
  insights: z.string().optional().nullable(),
});

export type CategorySummaryData = z.infer<typeof categorySummaryDataSchema>;

// ============================================================================
// USER SETTINGS (for progression tracking)
// ============================================================================

export const userSettingsSchema = z.object({
  functional_currency: z.string().optional().nullable(),
  bank_accounts_count: z.number().optional().nullable(),
  registered_banks: z.array(z.string()).optional().nullable(),
  profiles: z.array(z.string()).optional().nullable(),
  onboarding_complete: z.boolean().optional().nullable(),
});

export type UserSettings = z.infer<typeof userSettingsSchema>;

// ============================================================================
// DAILY TOTALS (for chart builders)
// ============================================================================

export const dailyTotalSchema = z.object({
  date: z.string(),
  inflows: z.number(),
  outflows: z.number(),
  net: z.number(),
});

export type DailyTotal = z.infer<typeof dailyTotalSchema>;

// ============================================================================
// CATEGORY BREAKDOWN (for chart builders)
// ============================================================================

export const categoryBreakdownSchema = z.object({
  category: z.string(),
  amount: z.number(),
  percentage: z.number().optional(),
  count: z.number().optional(),
});

export type CategoryBreakdown = z.infer<typeof categoryBreakdownSchema>;

// ============================================================================
// CHANGE SUMMARY (for mutate_categories endpoint)
// ============================================================================

export const changeSummaryItemSchema = z.object({
  message: z.string(),
  status: z.enum(['success', 'error']),
  category: z.string(),
  to_category: z.string().optional(),
});

export type ChangeSummaryItem = z.infer<typeof changeSummaryItemSchema>;

export const changeSummarySchema = z.array(changeSummaryItemSchema);

export type ChangeSummary = z.infer<typeof changeSummarySchema>;

// ============================================================================
// DASHBOARD PROPS
// ============================================================================

export const dashboardPropsSchema = z.object({
  kind: z.literal('dashboard'),
  generated_at: z.string(),

  statement: statementSchema,
  transactions: z.array(transactionSchema),
  metrics: metricsSchema,
  pivot: pivotTableSchema,
  category_summaries: z.array(categorySummaryDataSchema).optional().default([]),
  currency: z.string(),
  banks: z.array(z.string()),
  coverage: coverageWindowSchema,

  // Available filter options (always contains ALL options regardless of current filter)
  // These allow users to change filters even when AI requested filtered data
  available_months: z.array(z.string()).optional().default([]),
  available_banks: z.array(z.string()).optional().default([]),
  available_profiles: z.array(z.string()).optional().default([]), // Household profiles in use

  // Fields for widget initialization and insights
  initial_filters: initialFiltersSchema.optional().nullable(),
  statement_insights: z.string().optional().nullable(),
  
  // User settings for progression tracking (only includes actually set values, not defaults)
  user_settings: userSettingsSchema.optional().nullable(),

  summary_count: z.number().optional(),
  version: z.string().optional().nullable(),
});

export type DashboardProps = z.infer<typeof dashboardPropsSchema>;

export type ValidationResult<T> = z.SafeParseReturnType<unknown, T>;

export function validateDashboardProps(
  data: unknown
): ValidationResult<DashboardProps> {
  return dashboardPropsSchema.safeParse(data);
}

export function isDashboardProps(data: unknown): data is DashboardProps {
  const result = validateDashboardProps(data);
  return result.success;
}
