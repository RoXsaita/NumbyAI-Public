/**
 * Chart Builders - Vega-Lite Spec Generators
 *
 * These functions generate Vega-Lite chart specifications from raw data.
 * Previously, these specs were generated server-side (bad coupling).
 * Now they're generated client-side, allowing easy customization.
 *
 * Benefits:
 * - Widget controls visualization
 * - Easy to customize colors/styles
 * - Can switch chart libraries without server changes
 * - A/B test different chart types
 */

import type { DailyTotal, CategoryBreakdown } from '../shared/schemas';

// ============================================================================
// TYPES
// ============================================================================

/**
 * Vega-Lite spec (simplified type - full spec is very complex)
 */
export type VegaLiteSpec = Record<string, unknown>;

// ============================================================================
// TIME SERIES CHART
// ============================================================================

/**
 * Build a time series chart showing daily inflows/outflows
 */
export function buildTimeSeriesChart(
  dailyTotals: DailyTotal[],
  currency: string = 'USD'
): VegaLiteSpec {
  return {
    width: 'container',
    height: 300,
    data: { values: dailyTotals },
    layer: [
      // Inflows line (green)
      {
        mark: { type: 'line', point: true, color: '#10b981' },
        encoding: {
          x: {
            field: 'date',
            type: 'temporal',
            title: 'Date',
            axis: { format: '%b %d' },
          },
          y: {
            field: 'inflows',
            type: 'quantitative',
            title: `Amount (${currency})`,
          },
          tooltip: [
            { field: 'date', type: 'temporal', title: 'Date' },
            { field: 'inflows', type: 'quantitative', title: 'Inflows', format: ',.2f' },
          ],
        },
      },
      // Outflows line (red)
      {
        mark: { type: 'line', point: true, color: '#ef4444' },
        encoding: {
          x: { field: 'date', type: 'temporal' },
          y: { field: 'outflows', type: 'quantitative' },
          tooltip: [
            { field: 'date', type: 'temporal', title: 'Date' },
            { field: 'outflows', type: 'quantitative', title: 'Outflows', format: ',.2f' },
          ],
        },
      },
    ],
  };
}

// ============================================================================
// CATEGORY BREAKDOWN CHART
// ============================================================================

/**
 * Build a donut chart showing spending by category
 */
export function buildCategoryDonutChart(
  categories: CategoryBreakdown[],
  topN: number = 10
): VegaLiteSpec {
  // Take top N categories
  const topCategories = categories.slice(0, topN);

  return {
    width: 'container',
    height: 300,
    data: {
      values: topCategories.map((cat) => ({
        category: cat.category,
        amount: cat.amount,
      })),
    },
    mark: { type: 'arc', innerRadius: 60, outerRadius: 120 },
    encoding: {
      theta: { field: 'amount', type: 'quantitative' },
      color: {
        field: 'category',
        type: 'nominal',
        scale: { scheme: 'category20' },
      },
      tooltip: [
        { field: 'category', type: 'nominal', title: 'Category' },
        { field: 'amount', type: 'quantitative', title: 'Amount', format: ',.2f' },
      ],
    },
  };
}

/**
 * Build a horizontal bar chart showing category breakdown
 */
export function buildCategoryBarChart(
  categories: CategoryBreakdown[],
  topN: number = 10
): VegaLiteSpec {
  const topCategories = categories.slice(0, topN);

  return {
    width: 'container',
    height: 300,
    data: {
      values: topCategories.map((cat) => ({
        category: cat.category,
        amount: cat.amount,
      })),
    },
    mark: { type: 'bar', color: '#3b82f6' },
    encoding: {
      y: {
        field: 'category',
        type: 'nominal',
        sort: '-x',
        title: 'Category',
      },
      x: {
        field: 'amount',
        type: 'quantitative',
        title: 'Amount',
      },
      tooltip: [
        { field: 'category', type: 'nominal', title: 'Category' },
        { field: 'amount', type: 'quantitative', title: 'Amount', format: ',.2f' },
      ],
    },
  };
}

// ============================================================================
// NET CHANGE CHART
// ============================================================================

/**
 * Build a simple line chart showing cumulative net change over time
 */
export function buildNetChangeChart(
  dailyTotals: DailyTotal[],
  currency: string = 'USD'
): VegaLiteSpec {
  // Calculate cumulative net change
  let cumulative = 0;
  const cumulativeData = dailyTotals.map((day) => {
    cumulative += day.net;
    return {
      date: day.date,
      cumulative_net: cumulative,
    };
  });

  return {
    width: 'container',
    height: 200,
    data: { values: cumulativeData },
    mark: {
      type: 'area',
      line: { color: '#6366f1' },
      color: { gradient: 'linear', stops: [{ offset: 0, color: '#6366f1' }, { offset: 1, color: '#a5b4fc' }] },
    },
    encoding: {
      x: {
        field: 'date',
        type: 'temporal',
        title: 'Date',
        axis: { format: '%b %d' },
      },
      y: {
        field: 'cumulative_net',
        type: 'quantitative',
        title: `Cumulative Net (${currency})`,
      },
      tooltip: [
        { field: 'date', type: 'temporal', title: 'Date' },
        { field: 'cumulative_net', type: 'quantitative', title: 'Net', format: ',.2f' },
      ],
    },
  };
}

// ============================================================================
// EXPORTS
// ============================================================================

export const chartBuilders = {
  timeSeries: buildTimeSeriesChart,
  categoryDonut: buildCategoryDonutChart,
  categoryBar: buildCategoryBarChart,
  netChange: buildNetChangeChart,
};
