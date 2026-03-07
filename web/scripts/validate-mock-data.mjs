#!/usr/bin/env node
/**
 * Validate Mock Data Script
 *
 * Validates that mock data matches the schema.
 * Run this before deploying to catch schema mismatches early.
 *
 * Usage:
 *   node scripts/validate-mock-data.mjs
 */

import { mockDashboardData } from '../src/mocks/dashboard-mock-data.ts';
import { validateDashboardProps } from '../src/shared/schemas.ts';

console.log('🔍 Validating mock dashboard data...\n');

const result = validateDashboardProps(mockDashboardData);

if (result.success) {
  console.log('✅ Mock data validation PASSED\n');
  console.log('Summary:');
  console.log(`  - Transactions: ${result.data.transactions.length}`);
  console.log(`  - Inflows: ${result.data.metrics.inflows}`);
  console.log(`  - Outflows: ${result.data.metrics.outflows}`);
  console.log(`  - Net cash: ${result.data.metrics.net_cash}`);
  console.log(`  - Segments: ${result.data.metrics.segments.length}`);
  console.log(`  - Pivot categories: ${result.data.pivot.categories.length}`);
  console.log(`  - Pivot months: ${result.data.pivot.months.length}\n`);

  process.exit(0);
} else {
  console.error('❌ Mock data validation FAILED\n');
  console.error('Validation errors:');

  result.error.issues.forEach((issue, index) => {
    console.error(`\n${index + 1}. ${issue.path.join('.')}: ${issue.message}`);
  });

  console.error('\n⚠️  Please fix the mock data before deploying!\n');
  process.exit(1);
}
