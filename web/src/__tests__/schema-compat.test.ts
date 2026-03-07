/**
 * Schema Compatibility Tests
 *
 * Ensures that:
 * 1. Mock data validates against the schema
 * 2. Example tool responses validate against the schema
 * 3. Both sources produce compatible data
 *
 * This catches schema mismatches early in development.
 */

import { validateDashboardProps, isDashboardProps } from '../shared/schemas';
import { mockDashboardData } from '../mocks/dashboard-mock-data';

// ============================================================================
// MOCK DATA TESTS
// ============================================================================

describe('Mock Data Schema Compatibility', () => {
  test('mock data validates successfully', () => {
    const result = validateDashboardProps(mockDashboardData);

    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.kind).toBe('dashboard');
      expect(result.data.transactions).toBeInstanceOf(Array);
      expect(result.data.transactions.length).toBeGreaterThanOrEqual(0);
    }
  });

  test('mock data has required fields', () => {
    expect(mockDashboardData.kind).toBe('dashboard');
    expect(mockDashboardData.statement).toBeDefined();
    expect(mockDashboardData.transactions).toBeDefined();
    expect(mockDashboardData.metrics).toBeDefined();
  });

  test('mock transactions have required fields', () => {
    const firstTx = mockDashboardData.transactions[0];

    expect(firstTx).toBeDefined();
    expect(typeof firstTx.id).toBe('string');
    expect(typeof firstTx.transaction_date).toBe('string');
    expect(typeof firstTx.description).toBe('string');
    expect(typeof firstTx.amount).toBe('number');
    expect(typeof firstTx.currency).toBe('string');
    expect(typeof firstTx.category).toBe('string');
  });

  test('mock metrics are calculated correctly', () => {
    const { metrics } = mockDashboardData;

    expect(metrics.inflows).toBeGreaterThan(0);
    expect(metrics.outflows).toBeGreaterThan(0);
    const netFromPivot = Object.values(mockDashboardData.pivot.category_totals).reduce((sum, val) => sum + val, 0);
    expect(metrics.net_cash).toBeCloseTo(netFromPivot);
    expect(metrics.segments).toBeInstanceOf(Array);
    expect(metrics.top_variances.length).toBeGreaterThan(0);
  });

  test('mock pivot data contains categories and months', () => {
    const { pivot } = mockDashboardData;

    expect(pivot.categories.length).toBeGreaterThan(0);
    expect(pivot.months.length).toBeGreaterThan(0);
    expect(pivot.actuals.length).toBe(pivot.categories.length);
    expect(pivot.actuals[0]?.length).toBe(pivot.months.length);
  });

  test('isDashboardProps type guard works', () => {
    expect(isDashboardProps(mockDashboardData)).toBe(true);
    expect(isDashboardProps(null)).toBe(false);
    expect(isDashboardProps({})).toBe(false);
    expect(isDashboardProps({ kind: 'dashboard' })).toBe(false); // missing fields
  });
});

// ============================================================================
// SCHEMA VALIDATION TESTS
// ============================================================================

describe('Schema Validation Edge Cases', () => {
  test('rejects data with wrong kind', () => {
    const badData = {
      ...mockDashboardData,
      kind: 'wrong',
    };

    const result = validateDashboardProps(badData);
    expect(result.success).toBe(false);
  });

  test('rejects data with missing transactions', () => {
    const badData = {
      ...mockDashboardData,
      transactions: undefined,
    };

    const result = validateDashboardProps(badData as any);
    expect(result.success).toBe(false);
  });

  test('rejects data with invalid transaction', () => {
    const badData = {
      ...mockDashboardData,
      transactions: [
        {
          id: '123',
          // missing required fields
        },
      ],
    };

    const result = validateDashboardProps(badData as any);
    expect(result.success).toBe(false);
  });

  test('rejects data with missing metrics', () => {
    const badData = {
      ...mockDashboardData,
      metrics: undefined,
    };

    const result = validateDashboardProps(badData as any);
    expect(result.success).toBe(false);
  });

  test('accepts data with optional fields missing', () => {
    const minimalData = {
      kind: 'dashboard',
      generated_at: new Date().toISOString(),
      statement: {
        id: 'test',
        month: 'January 2024',
        bank: null,
        currency: 'USD',
      },
      transactions: [],
      metrics: {
        inflows: 0,
        outflows: 0,
        internal_transfers: 0,
        net_cash: 0,
        budget_coverage_pct: 0,
        segments: [],
        top_variances: [],
      },
      pivot: {
        categories: [],
        months: [],
        actuals: [],
        budgets: [],
        transaction_counts: [],
        category_totals: {},
        category_budget_totals: {},
        month_totals: {},
        month_budget_totals: {},
        category_shares: {},
        currency: 'USD',
      },
      currency: 'USD',
      banks: [],
      coverage: {
        start: null,
        end: null,
      },
    };

    const result = validateDashboardProps(minimalData);
    expect(result.success).toBe(true);
  });
});

// ============================================================================
// SAMPLE TOOL RESPONSE TEST
// ============================================================================

describe('Sample Tool Response', () => {
  test('sample server response validates correctly', () => {
    // This simulates what the server would return
    const sampleServerResponse = {
      kind: 'dashboard',
      generated_at: '2024-01-15T10:00:00Z',
      statement: {
        id: 'stmt_test',
        month: 'January 2024',
        bank: 'Test Bank',
        currency: 'USD',
      },
      transactions: [
        {
          id: 'txn_001',
          transaction_date: '2024-01-01',
          description: 'Test Transaction',
          amount: 100.00,
          currency: 'USD',
          category: 'Test',
        },
      ],
      metrics: {
        inflows: 100.00,
        outflows: 40,
        internal_transfers: 0,
        net_cash: 60.00,
        budget_coverage_pct: 90,
        segments: [
          { name: 'inflows', actual: 100, budget: 90, variance: 10, variance_pct: 11.1 },
          { name: 'outflows', actual: 40, budget: 45, variance: -5, variance_pct: -11.1 },
          { name: 'internal_transfers', actual: 0, budget: 0, variance: 0, variance_pct: 0 },
        ],
        top_variances: [
          { category: 'Test', actual: -40, budget: -35, variance: -5, variance_pct: 14.2, direction: 'over' },
        ],
      },
      pivot: {
        categories: ['Income', 'Expenses'],
        months: ['2024-01'],
        actuals: [[100], [-40]],
        budgets: [[90], [-35]],
        transaction_counts: [[1], [1]],
        category_totals: { Income: 100, Expenses: -40 },
        category_budget_totals: { Income: 90, Expenses: -35 },
        month_totals: { '2024-01': 60 },
        month_budget_totals: { '2024-01': 55 },
        category_shares: { Income: 0, Expenses: 100 },
        currency: 'USD',
      },
      currency: 'USD',
      banks: ['Test Bank'],
      coverage: { start: '2024-01-01', end: '2024-01-31' },
      version: '1.0.0',
    };

    const result = validateDashboardProps(sampleServerResponse);
    expect(result.success).toBe(true);
  });
});
