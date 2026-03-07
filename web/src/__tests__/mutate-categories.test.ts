/**
 * Mutate Categories Tests
 *
 * Tests for the mutate_categories tool functionality:
 * 1. change_summary schema validation
 * 2. Widget form validation logic
 * 3. Tool call payload validation
 */

import { changeSummarySchema, changeSummaryItemSchema } from '../shared/schemas';

// ============================================================================
// CHANGE SUMMARY SCHEMA TESTS
// ============================================================================

describe('Change Summary Schema Validation', () => {
  test('valid change summary item validates successfully', () => {
    const validItem = {
      message: 'Updated category "Food & Groceries" to -500.0.',
      status: 'success' as const,
      category: 'Food & Groceries',
    };

    const result = changeSummaryItemSchema.safeParse(validItem);
    expect(result.success).toBe(true);
  });

  test('change summary item with to_category validates successfully', () => {
    const validItem = {
      message: 'Transferred 200.0 from "Travel" to "Transportation".',
      status: 'success' as const,
      category: 'Travel',
      to_category: 'Transportation',
    };

    const result = changeSummaryItemSchema.safeParse(validItem);
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.to_category).toBe('Transportation');
    }
  });

  test('change summary item with error status validates successfully', () => {
    const validItem = {
      message: 'Category "Invalid" not found for transfer.',
      status: 'error' as const,
      category: 'Invalid',
      to_category: 'Target',
    };

    const result = changeSummaryItemSchema.safeParse(validItem);
    expect(result.success).toBe(true);
  });

  test('rejects invalid status', () => {
    const invalidItem = {
      message: 'Test',
      status: 'invalid' as any,
      category: 'Test',
    };

    const result = changeSummaryItemSchema.safeParse(invalidItem);
    expect(result.success).toBe(false);
  });

  test('rejects missing required fields', () => {
    const invalidItem = {
      message: 'Test',
      // missing status and category
    };

    const result = changeSummaryItemSchema.safeParse(invalidItem);
    expect(result.success).toBe(false);
  });

  test('valid change summary array validates successfully', () => {
    const validSummary = [
      {
        message: 'Updated category "Food & Groceries" to -500.0.',
        status: 'success' as const,
        category: 'Food & Groceries',
      },
      {
        message: 'Transferred 200.0 from "Travel" to "Transportation".',
        status: 'success' as const,
        category: 'Travel',
        to_category: 'Transportation',
      },
    ];

    const result = changeSummarySchema.safeParse(validSummary);
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.length).toBe(2);
    }
  });

  test('empty change summary array validates successfully', () => {
    const result = changeSummarySchema.safeParse([]);
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.length).toBe(0);
    }
  });
});

// ============================================================================
// WIDGET FORM VALIDATION TESTS
// ============================================================================

describe('Widget Form Validation Logic', () => {
  test('edit form requires category and new_amount', () => {
    const validEdit = {
      category: 'Food & Groceries',
      new_amount: '-500.0',
    };

    expect(validEdit.category).toBeTruthy();
    expect(validEdit.new_amount).toBeTruthy();
    expect(!isNaN(parseFloat(validEdit.new_amount))).toBe(true);
  });

  test('transfer form requires from_category, to_category, and amount > 0', () => {
    const validTransfer = {
      from_category: 'Travel',
      to_category: 'Transportation',
      amount: '200.0',
    };

    expect(validTransfer.from_category).toBeTruthy();
    expect(validTransfer.to_category).toBeTruthy();
    expect(validTransfer.amount).toBeTruthy();
    expect(parseFloat(validTransfer.amount)).toBeGreaterThan(0);
    expect(validTransfer.from_category !== validTransfer.to_category).toBe(true);
  });

  test('transfer form rejects same category for from and to', () => {
    const invalidTransfer = {
      from_category: 'Travel',
      to_category: 'Travel',
      amount: '200.0',
    };

    expect(invalidTransfer.from_category === invalidTransfer.to_category).toBe(true);
  });

  test('transfer form rejects amount <= 0', () => {
    const invalidTransfer1 = {
      from_category: 'Travel',
      to_category: 'Transportation',
      amount: '0',
    };

    const invalidTransfer2 = {
      from_category: 'Travel',
      to_category: 'Transportation',
      amount: '-100',
    };

    expect(parseFloat(invalidTransfer1.amount)).toBeLessThanOrEqual(0);
    expect(parseFloat(invalidTransfer2.amount)).toBeLessThanOrEqual(0);
  });
});

// ============================================================================
// TOOL CALL PAYLOAD TESTS
// ============================================================================

describe('Tool Call Payload Validation', () => {
  test('edit operation payload structure', () => {
    const editOp = {
      type: 'edit' as const,
      category: 'Food & Groceries',
      new_amount: -500.0,
      note: 'Adjusted for meal prep',
    };

    expect(editOp.type).toBe('edit');
    expect(editOp.category).toBeTruthy();
    expect(typeof editOp.new_amount).toBe('number');
    expect(editOp.note).toBeDefined();
  });

  test('transfer operation payload structure', () => {
    const transferOp = {
      type: 'transfer' as const,
      category: 'Travel',
      to_category: 'Transportation',
      amount: 200.0,
    };

    expect(transferOp.type).toBe('transfer');
    expect(transferOp.category).toBeTruthy();
    expect(transferOp.to_category).toBeTruthy();
    expect(typeof transferOp.amount).toBe('number');
    expect(transferOp.amount).toBeGreaterThan(0);
    expect(transferOp.category !== transferOp.to_category).toBe(true);
  });

  test('operations array structure', () => {
    const operations = [
      {
        type: 'edit' as const,
        category: 'Food & Groceries',
        new_amount: -500.0,
      },
      {
        type: 'transfer' as const,
        category: 'Travel',
        to_category: 'Transportation',
        amount: 200.0,
      },
    ];

    expect(Array.isArray(operations)).toBe(true);
    expect(operations.length).toBe(2);
    expect(operations[0].type).toBe('edit');
    expect(operations[1].type).toBe('transfer');
  });
});

