/**
 * Data Transformers - Client-Side Data Processing
 *
 * These helpers convert raw pivot data into UI-friendly structures.
 */

import type { PivotTable, CategorySummaryData } from '../shared/schemas';

// ============================================================================
// FORMATTING
// ============================================================================

const CURRENCY_SYMBOLS: Record<string, string> = {
  'USD': '$',
  'EUR': '€',
  'GBP': '£',
  'PLN': 'zł',
  'JPY': '¥',
  'CAD': 'C$',
  'AUD': 'A$',
};

export function formatCurrency(amount: number, currency: string = 'USD'): string {
  try {
    const formatter = new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: currency.toUpperCase(),
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
    return formatter.format(amount);
  } catch (e) {
    console.warn('Currency formatting failed, using fallback:', currency, e);
    const symbol = CURRENCY_SYMBOLS[currency.toUpperCase()] || currency;
    const sign = amount < 0 ? '-' : '';
    const absAmount = Math.abs(amount);
    return `${sign}${symbol}${absAmount.toFixed(2)}`;
  }
}

export function formatDate(dateString: string): string {
  try {
    const date = new Date(dateString);
    // Check for invalid date
    if (isNaN(date.getTime())) {
      return dateString;
    }
    return new Intl.DateTimeFormat('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    }).format(date);
  } catch {
    return dateString;
  }
}

export function formatPercentage(value: number): string {
  return `${value.toFixed(1)}%`;
}

export function formatMonthLabel(monthId: string): string {
  try {
    const [year, month] = monthId.split('-').map(Number);
    if (!year || !month) {
      return monthId;
    }
    const date = new Date(year, month - 1, 1);
    if (isNaN(date.getTime())) {
        return monthId;
    }
    return new Intl.DateTimeFormat('en-US', {
      month: 'short',
      year: 'numeric',
    }).format(date);
  } catch (e) {
    return monthId;
  }
}

// ============================================================================
// PIVOT HELPERS
// ============================================================================

export type PivotRowDisplay = {
  category: string;
  sharePct: number;
  totalActual: number;
  totalBudget: number;
  variance: number;
  variancePct: number;
  monthly: Array<{
    month: string;
    label: string;
    actual: number;
    budget: number;
    variance: number;
    variancePct: number;
  }>;
};

const toVariancePct = (variance: number, budget: number): number => {
  if (!budget) {
    return 0;
  }
  return (variance / Math.abs(budget)) * 100;
};

export function buildPivotRowDisplays(pivot: PivotTable): PivotRowDisplay[] {
  return pivot.categories.map((category, idx) => {
    const totalActual = pivot.category_totals[category] ?? 0;
    const totalBudget = pivot.category_budget_totals[category] ?? 0;
    const classification = classifyCategory(category, totalActual);
    const normalizeForVariance = (value: number): number =>
      classification === 'outflows' ? Math.abs(value) : value;

    const totalVariance = normalizeForVariance(totalActual) - normalizeForVariance(totalBudget);
    const variancePct = toVariancePct(totalVariance, normalizeForVariance(totalBudget));
    const sharePct = pivot.category_shares[category] ?? 0;

    const monthly = pivot.months.map((month, monthIdx) => {
      const actual = pivot.actuals[idx]?.[monthIdx] ?? 0;
      const budget = pivot.budgets[idx]?.[monthIdx] ?? 0;
      const normalizedActual = normalizeForVariance(actual);
      const normalizedBudget = normalizeForVariance(budget);
      const variance = normalizedActual - normalizedBudget;

      return {
        month,
        label: formatMonthLabel(month),
        actual,
        budget,
        variance,
        variancePct: toVariancePct(variance, normalizedBudget),
      };
    });

    return {
      category,
      sharePct,
      totalActual,
      totalBudget,
      variance: totalVariance,
      variancePct,
      monthly,
    };
  });
}

/**
 * Build a normalized month trend dataset for sparklines/bars.
 */
export function buildMonthTrend(pivot: PivotTable): Array<{ month: string; value: number }> {
  return pivot.months.map((month) => ({
    month,
    value: pivot.month_totals[month] ?? 0,
  }));
}

export function getBudgetRatio(actual: number, budget: number | null | undefined): number {
  if (!budget) {
    return 1;
  }
  const ratio = actual / budget;
  if (!Number.isFinite(ratio)) {
    return 1;
  }
  return Math.max(0, Math.min(Math.abs(ratio), 2));
}

// ============================================================================
// CATEGORY CLASSIFICATION
// ============================================================================

export type CategoryClassification = 'inflows' | 'outflows' | 'internal_transfers';

const INTERNAL_TRANSFER_CATEGORIES = ['Internal Transfers', 'Internal Transfer', 'Transfer', 'Account Transfer'];
const INTERNAL_TRANSFER_KEYWORDS = ['transfer', 'transfers', 'cash', 'savings'];
const CATEGORY_CLASSIFICATIONS: Record<string, CategoryClassification> = {
  'income': 'inflows',
  'internal transfers': 'internal_transfers',
  'internal transfer': 'internal_transfers',
  'transfer': 'internal_transfers',
  'account transfer': 'internal_transfers',
  'savings': 'internal_transfers',
  'housing & utilities': 'outflows',
  'food & groceries': 'outflows',
  'transportation': 'outflows',
  'insurance': 'outflows',
  'healthcare': 'outflows',
  'shopping': 'outflows',
  'entertainment': 'outflows',
  'travel': 'outflows',
  'debt payments': 'outflows',
  'investments': 'outflows',
  'other': 'outflows',
};

export function classifyCategory(categoryName: string, totalAmount: number): CategoryClassification {
  const lower = categoryName.trim().toLowerCase();

  const knownClassification = CATEGORY_CLASSIFICATIONS[lower];
  if (knownClassification) {
    return knownClassification;
  }
  
  // First check exact category names
  const isExactTransfer = INTERNAL_TRANSFER_CATEGORIES.some(tc => lower === tc.toLowerCase());
  
  // Then check keywords (but only for exact word matches, not substring)
  const hasTransferKeyword = INTERNAL_TRANSFER_KEYWORDS.some(kw => {
    const kwLower = kw.toLowerCase();
    return lower === kwLower || 
           lower.startsWith(kwLower + ' ') ||
           lower.endsWith(' ' + kwLower) ||
           lower.includes(' ' + kwLower + ' ');
  });
  
  if (isExactTransfer || hasTransferKeyword) {
    return 'internal_transfers';
  }
  
  // Otherwise classify by amount
  if (totalAmount >= 0) {
    return 'inflows';
  }
  return 'outflows';
}

// ============================================================================
// MONTHLY FLOW SERIES
// ============================================================================

export type MonthFlowPoint = {
  month: string;
  label: string;
  inflow: number;
  outflow: number;
  internalTransfer: number;
  net: number;
  budgetOutflow: number;
};

const roundTwo = (value: number): number => Math.round(value * 100) / 100;

export function buildMonthlyFlowSeries(pivot: PivotTable): MonthFlowPoint[] {
  return pivot.months.map((month, monthIdx) => {
    let inflowTotal = 0;
    let outflowTotal = 0;
    let internalTransferTotal = 0;
    let budgetOutflowTotal = 0;

    pivot.categories.forEach((category, categoryIdx) => {
      const actual = pivot.actuals[categoryIdx]?.[monthIdx] ?? 0;
      const budget = pivot.budgets[categoryIdx]?.[monthIdx] ?? 0;
      const categoryTotal = pivot.category_totals[category] ?? actual;
      const classification = classifyCategory(category, categoryTotal);

      if (classification === 'inflows') {
        inflowTotal += actual;
      } else if (classification === 'internal_transfers') {
        // Internal transfers are excluded from flow visuals
        internalTransferTotal += 0;
      } else {
        outflowTotal += Math.abs(actual);
        budgetOutflowTotal += Math.abs(budget);
      }
    });

    const net = inflowTotal - outflowTotal;

    return {
      month,
      label: formatMonthLabel(month),
      inflow: roundTwo(inflowTotal),
      outflow: roundTwo(outflowTotal),
      internalTransfer: roundTwo(internalTransferTotal),
      net: roundTwo(net),
      budgetOutflow: roundTwo(budgetOutflowTotal),
    };
  });
}

// ============================================================================
// BANK FILTERING
// ============================================================================

export function buildBankFilteredPivot(
  originalPivot: PivotTable,
  summaries: CategorySummaryData[],
  bankNames: string[],
  profiles?: string[]
): PivotTable {
  const hasBankFilter = bankNames && bankNames.length > 0;
  const hasProfileFilter = profiles && profiles.length > 0;
  
  if (!hasBankFilter && !hasProfileFilter) return originalPivot;

  const filteredSummaries = summaries.filter(s => {
    const matchesBank = !hasBankFilter || bankNames.includes(s.bank);
    const matchesProfile = !hasProfileFilter || (s.profile && profiles.includes(s.profile));
    return matchesBank && matchesProfile;
  });
  
  // Initialize structures
  // Use map to create copies
  const actuals = originalPivot.categories.map(() => originalPivot.months.map(() => 0));
  const counts = originalPivot.categories.map(() => originalPivot.months.map(() => 0));
  
  // Keep budgets as is
  const budgets = originalPivot.budgets;
  
  const categoryTotals: Record<string, number> = {};
  const monthTotals: Record<string, number> = {};
  originalPivot.months.forEach(m => monthTotals[m] = 0);
  
  // Fill actuals and counts
  filteredSummaries.forEach(summary => {
    const catIdx = originalPivot.categories.indexOf(summary.category);
    const monthIdx = originalPivot.months.indexOf(summary.month);
    
    if (catIdx >= 0 && monthIdx >= 0) {
        actuals[catIdx][monthIdx] += summary.amount;
        counts[catIdx][monthIdx] += summary.count;
    }
  });

  // Recalculate totals
  originalPivot.categories.forEach((cat, idx) => {
      let sum = 0;
      actuals[idx].forEach(val => sum += val);
      categoryTotals[cat] = sum;
  });
  
  originalPivot.months.forEach((month, idx) => {
      let sum = 0;
      originalPivot.categories.forEach((_, catIdx) => {
          sum += actuals[catIdx][idx];
      });
      monthTotals[month] = sum;
  });
  
  // Recalculate shares (expense only)
  const expenseTotalAbs = Object.entries(categoryTotals)
    .filter(([cat, val]) => val < 0 && classifyCategory(cat, val) === 'outflows')
    .reduce((sum, [_, val]) => sum + Math.abs(val), 0);

  const categoryShares: Record<string, number> = {};
  originalPivot.categories.forEach(cat => {
      const val = categoryTotals[cat] || 0;
      if (val < 0 && classifyCategory(cat, val) === 'outflows' && expenseTotalAbs > 0) {
          categoryShares[cat] = (Math.abs(val) / expenseTotalAbs) * 100;
      } else {
          categoryShares[cat] = 0;
      }
  });

  return {
      ...originalPivot,
      actuals,
      transaction_counts: counts,
      category_totals: categoryTotals,
      month_totals: monthTotals,
      category_shares: categoryShares
  };
}

// ============================================================================
// TREND ANALYSIS HELPERS
// ============================================================================

/**
 * Category trend data point for multi-line charts
 */
export type CategoryTrendPoint = {
  month: string;
  label: string;
  values: Record<string, number>;
};

/**
 * Build category-specific trend series for selected categories
 */
export function buildCategoryTrendSeries(
  pivot: PivotTable,
  selectedCategories: string[],
  months?: string[]
): CategoryTrendPoint[] {
  const categoriesToUse = selectedCategories.length > 0 
    ? selectedCategories 
    : pivot.categories;

  const monthsToUse = months && months.length > 0 
    ? pivot.months.filter(m => months.includes(m))
    : pivot.months;

  return monthsToUse
    .map((month) => {
      const monthIdx = pivot.months.indexOf(month);
      if (monthIdx === -1) return null;

      const values: Record<string, number> = {};
      
      categoriesToUse.forEach(category => {
        const catIdx = pivot.categories.indexOf(category);
        if (catIdx >= 0) {
          values[category] = pivot.actuals[catIdx]?.[monthIdx] ?? 0;
        }
      });

      return {
        month,
        label: formatMonthLabel(month),
        values,
      };
    })
    .filter((point): point is CategoryTrendPoint => point !== null);
}

/**
 * Distribution data point showing percentage breakdown
 */
export type DistributionPoint = {
  month: string;
  label: string;
  categories: Array<{
    category: string;
    amount: number;
    percentage: number;
  }>;
  total: number;
};

/**
 * Build spending distribution series for stacked percentage charts
 */
export function buildDistributionSeries(
  pivot: PivotTable,
  selectedCategories?: string[],
  months?: string[]
): DistributionPoint[] {
  const monthsToUse = months && months.length > 0 
    ? pivot.months.filter(m => months.includes(m))
    : pivot.months;

  return monthsToUse
    .map((month) => {
      const monthIdx = pivot.months.indexOf(month);
      if (monthIdx === -1) return null;

      const categoryData: Array<{ category: string; amount: number }> = [];
      
      pivot.categories.forEach((category, catIdx) => {
        const actual = pivot.actuals[catIdx]?.[monthIdx] ?? 0;
        const categoryTotal = pivot.category_totals[category] ?? actual;
        const classification = classifyCategory(category, categoryTotal);
        
        // Only include outflows for distribution chart
        if (classification === 'outflows') {
          // Filter by selected categories if provided
          if (!selectedCategories || selectedCategories.length === 0 || selectedCategories.includes(category)) {
            categoryData.push({
              category,
              amount: Math.abs(actual),
            });
          }
        }
      });

      const total = categoryData.reduce((sum, c) => sum + c.amount, 0);
      
      const categories = categoryData
        .map(c => ({
          category: c.category,
          amount: c.amount,
          percentage: total > 0 ? (c.amount / total) * 100 : 0,
        }))
        .sort((a, b) => b.amount - a.amount);

      return {
        month,
        label: formatMonthLabel(month),
        categories,
        total,
      };
    })
    .filter((point): point is DistributionPoint => point !== null);
}

/**
 * Budget vs Actual data point
 */
export type BudgetVsActualPoint = {
  month: string;
  label: string;
  actual: number;
  budget: number;
  variance: number;
  variancePct: number;
};

/**
 * Build budget vs actual comparison series
 */
export function buildBudgetVsActualSeries(
  pivot: PivotTable,
  selectedCategories?: string[],
  months?: string[]
): BudgetVsActualPoint[] {
  const monthsToUse = months && months.length > 0 
    ? pivot.months.filter(m => months.includes(m))
    : pivot.months;

  return monthsToUse
    .map((month) => {
      const monthIdx = pivot.months.indexOf(month);
      if (monthIdx === -1) return null;

      let actualTotal = 0;
      let budgetTotal = 0;

      pivot.categories.forEach((category, catIdx) => {
        const categoryTotal = pivot.category_totals[category] ?? 0;
        const classification = classifyCategory(category, categoryTotal);
        
        // Only include outflows for budget comparison
        if (classification === 'outflows') {
          if (!selectedCategories || selectedCategories.length === 0 || selectedCategories.includes(category)) {
            actualTotal += Math.abs(pivot.actuals[catIdx]?.[monthIdx] ?? 0);
            budgetTotal += Math.abs(pivot.budgets[catIdx]?.[monthIdx] ?? 0);
          }
        }
      });

      const variance = actualTotal - budgetTotal;
      const variancePct = budgetTotal > 0 ? (variance / budgetTotal) * 100 : 0;

      return {
        month,
        label: formatMonthLabel(month),
        actual: roundTwo(actualTotal),
        budget: roundTwo(budgetTotal),
        variance: roundTwo(variance),
        variancePct: roundTwo(variancePct),
      };
    })
    .filter((point): point is BudgetVsActualPoint => point !== null);
}

/**
 * Trend insights derived from pivot data
 */
export type TrendInsights = {
  savingsRate: number; // Percentage of income saved
  avgMonthlySpend: number;
  avgMonthlyIncome: number;
  topMover: {
    category: string;
    change: number;
    changePct: number;
    direction: 'up' | 'down';
  } | null;
  spendingTrend: 'increasing' | 'decreasing' | 'stable';
  netCashTrend: Array<{ month: string; value: number; cumulative: number }>;
};

/**
 * Calculate trend insights from monthly flow data
 */
export function calculateTrendInsights(
  monthlyFlow: MonthFlowPoint[],
  pivot: PivotTable,
  months?: string[]
): TrendInsights {
  const monthsToUse = months && months.length > 0 
    ? pivot.months.filter(m => months.includes(m))
    : pivot.months;

  // Calculate savings rate (average across all months)
  const totalInflow = monthlyFlow.reduce((sum, m) => sum + m.inflow, 0);
  const totalOutflow = monthlyFlow.reduce((sum, m) => sum + m.outflow, 0);
  const savingsRate = totalInflow > 0 
    ? ((totalInflow - totalOutflow) / totalInflow) * 100 
    : 0;

  // Average monthly metrics
  const monthCount = monthlyFlow.length || 1;
  const avgMonthlySpend = totalOutflow / monthCount;
  const avgMonthlyIncome = totalInflow / monthCount;

  // Find top mover (category with biggest MoM change in last 2 months)
  let topMover: TrendInsights['topMover'] = null;
  
  if (monthsToUse.length >= 2) {
    const lastMonth = monthsToUse[monthsToUse.length - 1];
    const prevMonth = monthsToUse[monthsToUse.length - 2];
    const lastMonthIdx = pivot.months.indexOf(lastMonth);
    const prevMonthIdx = pivot.months.indexOf(prevMonth);

    if (lastMonthIdx >= 0 && prevMonthIdx >= 0) {
      let maxChange = 0;
      
      pivot.categories.forEach((category, catIdx) => {
        const lastValue = Math.abs(pivot.actuals[catIdx]?.[lastMonthIdx] ?? 0);
        const prevValue = Math.abs(pivot.actuals[catIdx]?.[prevMonthIdx] ?? 0);
        const change = lastValue - prevValue;
        const changePct = prevValue > 0 ? (change / prevValue) * 100 : 0;
        
        if (Math.abs(change) > Math.abs(maxChange)) {
          maxChange = change;
          topMover = {
            category,
            change: roundTwo(change),
            changePct: roundTwo(changePct),
            direction: change >= 0 ? 'up' : 'down',
          };
        }
      });
    }
  }
    
  // Determine spending trend
  let spendingTrend: TrendInsights['spendingTrend'] = 'stable';
  if (monthlyFlow.length >= 2) {
    const recentMonths = monthlyFlow.slice(-3);
    const firstHalf = recentMonths.slice(0, Math.ceil(recentMonths.length / 2));
    const secondHalf = recentMonths.slice(Math.ceil(recentMonths.length / 2));
    
    const firstAvg = firstHalf.reduce((s, m) => s + m.outflow, 0) / (firstHalf.length || 1);
    const secondAvg = secondHalf.reduce((s, m) => s + m.outflow, 0) / (secondHalf.length || 1);
    
    const changePct = firstAvg > 0 ? ((secondAvg - firstAvg) / firstAvg) * 100 : 0;
    
    if (changePct > 5) spendingTrend = 'increasing';
    else if (changePct < -5) spendingTrend = 'decreasing';
  }

  // Build cumulative net cash trend
  let cumulative = 0;
  const netCashTrend = monthlyFlow.map(m => {
    cumulative += m.net;
    return {
      month: m.month,
      value: m.net,
      cumulative: roundTwo(cumulative),
    };
  });

  return {
    savingsRate: roundTwo(savingsRate),
    avgMonthlySpend: roundTwo(avgMonthlySpend),
    avgMonthlyIncome: roundTwo(avgMonthlyIncome),
    topMover,
    spendingTrend,
    netCashTrend,
  };
}

/**
 * Category color palette for trend charts
 */
export const CATEGORY_COLORS = [
  '#dc2626', // red-600 (primary)
  '#2563eb', // blue-600
  '#16a34a', // green-600
  '#ca8a04', // yellow-600
  '#9333ea', // purple-600
  '#0891b2', // cyan-600
  '#ea580c', // orange-600
  '#db2777', // pink-600
  '#4f46e5', // indigo-600
  '#65a30d', // lime-600
  '#0d9488', // teal-600
  '#7c3aed', // violet-600
];

/**
 * Get a consistent color for a category based on its index
 */
export function getCategoryColor(category: string, allCategories: string[]): string {
  const idx = allCategories.indexOf(category);
  return CATEGORY_COLORS[idx % CATEGORY_COLORS.length];
}

// ============================================================================
// BUDGET DATA TRANSFORMERS
// ============================================================================

/**
 * Budget progress data point for horizontal gauge charts
 */
export type BudgetProgressData = {
  category: string;
  budget: number;
  actual: number;
  utilization: number; // 0-1 ratio
  utilizationPct: number; // 0-100 percentage
  variance: number;
  variancePct: number;
  status: 'under' | 'on-track' | 'over'; // <85%, 85-100%, >100%
};

/**
 * Build budget progress data for horizontal gauge visualization
 */
export function buildBudgetProgressData(pivot: PivotTable): BudgetProgressData[] {
  return pivot.categories
    .map((category, idx) => {
      const totalActual = pivot.category_totals[category] ?? 0;
      const totalBudget = pivot.category_budget_totals[category] ?? 0;
      const classificationAmount = totalBudget !== 0 ? totalBudget : totalActual;
      const classification = classifyCategory(category, classificationAmount);

      // Only include outflows for budget tracking
      if (classification !== 'outflows') {
        return null;
      }

      const absActual = Math.abs(totalActual);
      const absBudget = Math.abs(totalBudget);

      if (absBudget === 0) {
        return null; // Skip categories with no budget
      }

      const utilization = absActual / absBudget;
      const utilizationPct = utilization * 100;
      const variance = absActual - absBudget;
      const variancePct = (variance / absBudget) * 100;

      let status: 'under' | 'on-track' | 'over';
      if (utilizationPct < 85) {
        status = 'under';
      } else if (utilizationPct <= 100) {
        status = 'on-track';
      } else {
        status = 'over';
      }

      return {
        category,
        budget: absBudget,
        actual: absActual,
        utilization,
        utilizationPct: roundTwo(utilizationPct),
        variance: roundTwo(variance),
        variancePct: roundTwo(variancePct),
        status,
      };
    })
    .filter((item): item is BudgetProgressData => item !== null)
    .sort((a, b) => b.budget - a.budget); // Sort by budget amount descending
}

/**
 * Budget allocation data point for donut chart
 */
export type BudgetAllocationData = {
  category: string;
  amount: number;
  percentage: number;
};

/**
 * Build budget allocation data for donut visualization
 */
export function buildBudgetAllocationData(pivot: PivotTable): BudgetAllocationData[] {
  // Sum all outflow budgets
  let totalOutflowBudget = 0;
  const categoryBudgets: Record<string, number> = {};

  pivot.categories.forEach((category, idx) => {
    const totalActual = pivot.category_totals[category] ?? 0;
    const totalBudgetAmount = pivot.category_budget_totals[category] ?? 0;
    const classificationAmount = totalBudgetAmount !== 0 ? totalBudgetAmount : totalActual;
    const classification = classifyCategory(category, classificationAmount);

    if (classification === 'outflows') {
      const budget = Math.abs(totalBudgetAmount);
      if (budget > 0) {
        categoryBudgets[category] = budget;
        totalOutflowBudget += budget;
      }
    }
  });

  if (totalOutflowBudget === 0) {
    return [];
  }

  return Object.entries(categoryBudgets)
    .map(([category, amount]) => ({
      category,
      amount,
      percentage: roundTwo((amount / totalOutflowBudget) * 100),
    }))
    .sort((a, b) => b.amount - a.amount); // Sort by amount descending
}
