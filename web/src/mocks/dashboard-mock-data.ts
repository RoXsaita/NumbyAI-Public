import type { DashboardProps } from '../shared/schemas';

// ─────────────────────────────────────────────────────────────────────────────
// Full-year 2024 demo dataset — USD, Chase + Amex, January–December 2024
// ─────────────────────────────────────────────────────────────────────────────

const MONTHS = [
  '2024-01', '2024-02', '2024-03', '2024-04', '2024-05', '2024-06',
  '2024-07', '2024-08', '2024-09', '2024-10', '2024-11', '2024-12',
];

const CATEGORIES = [
  'Income',
  'Housing & Utilities',
  'Food & Groceries',
  'Transportation',
  'Entertainment',
  'Health & Fitness',
  'Shopping',
  'Internal Transfers',
];

// Actuals [Jan … Dec] per category
const ACTUALS: number[][] = [
  // Income — salary + June raise + Dec bonus
  [5000, 5000, 5000, 5000, 5000, 5200, 5200, 5200, 5200, 5200, 5200, 5700],
  // Housing & Utilities — rent + utilities, slight July bump
  [-1800, -1800, -1800, -1800, -1800, -1800, -1850, -1850, -1850, -1850, -1850, -1850],
  // Food & Groceries — summer + holiday creep
  [-580, -540, -620, -590, -610, -640, -680, -660, -590, -620, -730, -850],
  // Transportation — summer road trips, holiday travel
  [-290, -270, -310, -320, -280, -350, -380, -340, -295, -310, -280, -320],
  // Entertainment — summer peak, holiday spike
  [-180, -160, -200, -220, -280, -310, -350, -290, -200, -220, -280, -420],
  // Health & Fitness — flat gym + annual physicals
  [-100, -100, -100, -100, -100, -100, -100, -100, -100, -100, -100, -100],
  // Shopping — back-to-school Aug, Black Friday Nov, Christmas Dec
  [-250, -180, -290, -340, -260, -310, -280, -480, -350, -290, -520, -780],
  // Internal Transfers — monthly savings transfer
  [-500, -500, -500, -500, -500, -500, -500, -500, -500, -500, -500, -500],
];

// Budgets [Jan … Dec] per category
const BUDGETS: number[][] = [
  [5000, 5000, 5000, 5000, 5000, 5200, 5200, 5200, 5200, 5200, 5200, 5200],
  [-1800, -1800, -1800, -1800, -1800, -1800, -1850, -1850, -1850, -1850, -1850, -1850],
  [-600, -600, -600, -600, -600, -600, -600, -600, -600, -600, -600, -700],
  [-300, -300, -300, -300, -300, -300, -300, -300, -300, -300, -300, -300],
  [-200, -200, -200, -200, -250, -300, -300, -250, -200, -200, -250, -350],
  [-100, -100, -100, -100, -100, -100, -100, -100, -100, -100, -100, -100],
  [-250, -250, -250, -300, -250, -300, -300, -400, -300, -300, -500, -700],
  [-500, -500, -500, -500, -500, -500, -500, -500, -500, -500, -500, -500],
];

// Transaction counts [Jan … Dec] per category
const TX_COUNTS: number[][] = [
  [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2],
  [3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3],
  [8, 7, 9, 8, 9, 10, 11, 10, 8, 9, 12, 14],
  [5, 4, 6, 5, 5, 7, 8, 7, 5, 6, 5, 6],
  [4, 3, 4, 5, 6, 7, 8, 6, 4, 5, 6, 8],
  [2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2],
  [3, 2, 4, 5, 4, 5, 4, 7, 5, 4, 8, 12],
  [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
];

// ─── derived totals ───────────────────────────────────────────────────────────

function sum(arr: number[]): number {
  return arr.reduce((a, b) => a + b, 0);
}

const categoryTotals: Record<string, number> = {};
const categoryBudgetTotals: Record<string, number> = {};
const categoryShares: Record<string, number> = {};

CATEGORIES.forEach((cat, i) => {
  categoryTotals[cat] = sum(ACTUALS[i]);
  categoryBudgetTotals[cat] = sum(BUDGETS[i]);
});

// Shares = % of total spending outflows (income & transfers excluded)
const totalOutflows = Math.abs(
  sum(ACTUALS[1]) + sum(ACTUALS[2]) + sum(ACTUALS[3]) +
  sum(ACTUALS[4]) + sum(ACTUALS[5]) + sum(ACTUALS[6])
);
CATEGORIES.forEach((cat, i) => {
  if (cat === 'Income' || cat === 'Internal Transfers') {
    categoryShares[cat] = 0;
  } else {
    categoryShares[cat] = parseFloat((Math.abs(categoryTotals[cat]) / totalOutflows * 100).toFixed(1));
  }
});

const monthTotals: Record<string, number> = {};
const monthBudgetTotals: Record<string, number> = {};
MONTHS.forEach((m, mi) => {
  monthTotals[m] = parseFloat(
    CATEGORIES.reduce((acc, _, ci) => acc + ACTUALS[ci][mi], 0).toFixed(2)
  );
  monthBudgetTotals[m] = parseFloat(
    CATEGORIES.reduce((acc, _, ci) => acc + BUDGETS[ci][mi], 0).toFixed(2)
  );
});

// ─── individual transactions (representative sample across the year) ───────────

export const mockDashboardData: DashboardProps = {
  kind: 'dashboard',
  generated_at: '2024-12-31T23:59:00Z',
  version: '2.0.0',

  statement: {
    id: 'stmt_fullyear_2024',
    month: 'Jan–Dec 2024',
    bank: 'Chase Bank',
    currency: 'USD',
  },

  currency: 'USD',
  banks: ['Chase', 'Amex'],
  coverage: { start: '2024-01-01', end: '2024-12-31' },

  available_months: MONTHS,
  available_banks: ['Chase', 'Amex'],
  available_profiles: [],

  // ── transactions ────────────────────────────────────────────────────────────
  transactions: [
    // January
    { id: 'txn_jan_01', transaction_date: '2024-01-01', description: 'Salary – Acme Corp', amount: 5000, currency: 'USD', category: 'Income' },
    { id: 'txn_jan_02', transaction_date: '2024-01-02', description: 'Rent – 412 Oak St', amount: -1500, currency: 'USD', category: 'Housing & Utilities' },
    { id: 'txn_jan_03', transaction_date: '2024-01-03', description: 'Con Edison Electric', amount: -180, currency: 'USD', category: 'Housing & Utilities' },
    { id: 'txn_jan_04', transaction_date: '2024-01-04', description: 'NYC Water & Sewer', amount: -120, currency: 'USD', category: 'Housing & Utilities' },
    { id: 'txn_jan_05', transaction_date: '2024-01-06', description: 'Whole Foods Market', amount: -142, currency: 'USD', category: 'Food & Groceries' },
    { id: 'txn_jan_06', transaction_date: '2024-01-10', description: 'Trader Joe\'s', amount: -98, currency: 'USD', category: 'Food & Groceries' },
    { id: 'txn_jan_07', transaction_date: '2024-01-13', description: 'Chipotle', amount: -22, currency: 'USD', category: 'Food & Groceries' },
    { id: 'txn_jan_08', transaction_date: '2024-01-15', description: 'MTA Metro Card', amount: -132, currency: 'USD', category: 'Transportation' },
    { id: 'txn_jan_09', transaction_date: '2024-01-19', description: 'Lyft', amount: -28, currency: 'USD', category: 'Transportation' },
    { id: 'txn_jan_10', transaction_date: '2024-01-20', description: 'Planet Fitness', amount: -25, currency: 'USD', category: 'Health & Fitness' },
    { id: 'txn_jan_11', transaction_date: '2024-01-21', description: 'Spotify Premium', amount: -11, currency: 'USD', category: 'Entertainment' },
    { id: 'txn_jan_12', transaction_date: '2024-01-25', description: 'Amazon – Household', amount: -128, currency: 'USD', category: 'Shopping' },
    { id: 'txn_jan_13', transaction_date: '2024-01-31', description: 'Transfer to Savings', amount: -500, currency: 'USD', category: 'Internal Transfers' },

    // February
    { id: 'txn_feb_01', transaction_date: '2024-02-01', description: 'Salary – Acme Corp', amount: 5000, currency: 'USD', category: 'Income' },
    { id: 'txn_feb_02', transaction_date: '2024-02-02', description: 'Rent – 412 Oak St', amount: -1500, currency: 'USD', category: 'Housing & Utilities' },
    { id: 'txn_feb_03', transaction_date: '2024-02-04', description: 'Con Edison Electric', amount: -175, currency: 'USD', category: 'Housing & Utilities' },
    { id: 'txn_feb_04', transaction_date: '2024-02-08', description: 'Trader Joe\'s', amount: -87, currency: 'USD', category: 'Food & Groceries' },
    { id: 'txn_feb_05', transaction_date: '2024-02-10', description: 'Whole Foods Market', amount: -120, currency: 'USD', category: 'Food & Groceries' },
    { id: 'txn_feb_06', transaction_date: '2024-02-14', description: 'Valentine\'s Dinner', amount: -95, currency: 'USD', category: 'Entertainment' },
    { id: 'txn_feb_07', transaction_date: '2024-02-15', description: 'MTA Metro Card', amount: -132, currency: 'USD', category: 'Transportation' },
    { id: 'txn_feb_08', transaction_date: '2024-02-20', description: 'Planet Fitness', amount: -25, currency: 'USD', category: 'Health & Fitness' },
    { id: 'txn_feb_09', transaction_date: '2024-02-28', description: 'Transfer to Savings', amount: -500, currency: 'USD', category: 'Internal Transfers' },

    // March
    { id: 'txn_mar_01', transaction_date: '2024-03-01', description: 'Salary – Acme Corp', amount: 5000, currency: 'USD', category: 'Income' },
    { id: 'txn_mar_02', transaction_date: '2024-03-02', description: 'Rent – 412 Oak St', amount: -1500, currency: 'USD', category: 'Housing & Utilities' },
    { id: 'txn_mar_03', transaction_date: '2024-03-05', description: 'Whole Foods Market', amount: -155, currency: 'USD', category: 'Food & Groceries' },
    { id: 'txn_mar_04', transaction_date: '2024-03-12', description: 'Chipotle', amount: -21, currency: 'USD', category: 'Food & Groceries' },
    { id: 'txn_mar_05', transaction_date: '2024-03-14', description: 'MTA Metro Card', amount: -132, currency: 'USD', category: 'Transportation' },
    { id: 'txn_mar_06', transaction_date: '2024-03-18', description: 'Netflix', amount: -18, currency: 'USD', category: 'Entertainment' },
    { id: 'txn_mar_07', transaction_date: '2024-03-20', description: 'Target – Spring Refresh', amount: -165, currency: 'USD', category: 'Shopping' },
    { id: 'txn_mar_08', transaction_date: '2024-03-25', description: 'Planet Fitness', amount: -25, currency: 'USD', category: 'Health & Fitness' },
    { id: 'txn_mar_09', transaction_date: '2024-03-31', description: 'Transfer to Savings', amount: -500, currency: 'USD', category: 'Internal Transfers' },

    // April
    { id: 'txn_apr_01', transaction_date: '2024-04-01', description: 'Salary – Acme Corp', amount: 5000, currency: 'USD', category: 'Income' },
    { id: 'txn_apr_02', transaction_date: '2024-04-02', description: 'Rent – 412 Oak St', amount: -1500, currency: 'USD', category: 'Housing & Utilities' },
    { id: 'txn_apr_03', transaction_date: '2024-04-06', description: 'Whole Foods Market', amount: -148, currency: 'USD', category: 'Food & Groceries' },
    { id: 'txn_apr_04', transaction_date: '2024-04-12', description: 'Uber', amount: -45, currency: 'USD', category: 'Transportation' },
    { id: 'txn_apr_05', transaction_date: '2024-04-15', description: 'Concert Tickets', amount: -140, currency: 'USD', category: 'Entertainment' },
    { id: 'txn_apr_06', transaction_date: '2024-04-18', description: 'Amazon – Spring Wardrobe', amount: -220, currency: 'USD', category: 'Shopping' },
    { id: 'txn_apr_07', transaction_date: '2024-04-25', description: 'Planet Fitness', amount: -25, currency: 'USD', category: 'Health & Fitness' },
    { id: 'txn_apr_08', transaction_date: '2024-04-30', description: 'Transfer to Savings', amount: -500, currency: 'USD', category: 'Internal Transfers' },

    // May
    { id: 'txn_may_01', transaction_date: '2024-05-01', description: 'Salary – Acme Corp', amount: 5000, currency: 'USD', category: 'Income' },
    { id: 'txn_may_02', transaction_date: '2024-05-02', description: 'Rent – 412 Oak St', amount: -1500, currency: 'USD', category: 'Housing & Utilities' },
    { id: 'txn_may_03', transaction_date: '2024-05-07', description: 'Whole Foods Market', amount: -162, currency: 'USD', category: 'Food & Groceries' },
    { id: 'txn_may_04', transaction_date: '2024-05-12', description: 'Memorial Day BBQ – Costco', amount: -148, currency: 'USD', category: 'Food & Groceries' },
    { id: 'txn_may_05', transaction_date: '2024-05-15', description: 'MTA Metro Card', amount: -132, currency: 'USD', category: 'Transportation' },
    { id: 'txn_may_06', transaction_date: '2024-05-20', description: 'Hulu + Disney Bundle', amount: -26, currency: 'USD', category: 'Entertainment' },
    { id: 'txn_may_07', transaction_date: '2024-05-22', description: 'Planet Fitness', amount: -25, currency: 'USD', category: 'Health & Fitness' },
    { id: 'txn_may_08', transaction_date: '2024-05-31', description: 'Transfer to Savings', amount: -500, currency: 'USD', category: 'Internal Transfers' },

    // June — raise kicks in
    { id: 'txn_jun_01', transaction_date: '2024-06-01', description: 'Salary – Acme Corp', amount: 5200, currency: 'USD', category: 'Income' },
    { id: 'txn_jun_02', transaction_date: '2024-06-02', description: 'Rent – 412 Oak St', amount: -1500, currency: 'USD', category: 'Housing & Utilities' },
    { id: 'txn_jun_04', transaction_date: '2024-06-04', description: 'Con Edison Electric', amount: -175, currency: 'USD', category: 'Housing & Utilities' },
    { id: 'txn_jun_05', transaction_date: '2024-06-08', description: 'Whole Foods Market', amount: -178, currency: 'USD', category: 'Food & Groceries' },
    { id: 'txn_jun_06', transaction_date: '2024-06-15', description: 'Uber – Airport', amount: -68, currency: 'USD', category: 'Transportation' },
    { id: 'txn_jun_07', transaction_date: '2024-06-18', description: 'Broadway Show', amount: -180, currency: 'USD', category: 'Entertainment' },
    { id: 'txn_jun_08', transaction_date: '2024-06-20', description: 'REI – Outdoor Gear', amount: -195, currency: 'USD', category: 'Shopping' },
    { id: 'txn_jun_09', transaction_date: '2024-06-30', description: 'Transfer to Savings', amount: -500, currency: 'USD', category: 'Internal Transfers' },

    // July — summer peak
    { id: 'txn_jul_01', transaction_date: '2024-07-01', description: 'Salary – Acme Corp', amount: 5200, currency: 'USD', category: 'Income' },
    { id: 'txn_jul_02', transaction_date: '2024-07-02', description: 'Rent – 412 Oak St', amount: -1550, currency: 'USD', category: 'Housing & Utilities' },
    { id: 'txn_jul_03', transaction_date: '2024-07-03', description: 'Con Edison Electric – A/C spike', amount: -195, currency: 'USD', category: 'Housing & Utilities' },
    { id: 'txn_jul_04', transaction_date: '2024-07-07', description: 'Whole Foods Market', amount: -185, currency: 'USD', category: 'Food & Groceries' },
    { id: 'txn_jul_05', transaction_date: '2024-07-10', description: 'Farmer\'s Market', amount: -62, currency: 'USD', category: 'Food & Groceries' },
    { id: 'txn_jul_06', transaction_date: '2024-07-15', description: 'Amtrak – Weekend Trip', amount: -210, currency: 'USD', category: 'Transportation' },
    { id: 'txn_jul_07', transaction_date: '2024-07-19', description: 'Rooftop Bar', amount: -95, currency: 'USD', category: 'Entertainment' },
    { id: 'txn_jul_08', transaction_date: '2024-07-22', description: 'Summer Concert', amount: -75, currency: 'USD', category: 'Entertainment' },
    { id: 'txn_jul_09', transaction_date: '2024-07-25', description: 'Planet Fitness', amount: -25, currency: 'USD', category: 'Health & Fitness' },
    { id: 'txn_jul_10', transaction_date: '2024-07-31', description: 'Transfer to Savings', amount: -500, currency: 'USD', category: 'Internal Transfers' },

    // August — back to school
    { id: 'txn_aug_01', transaction_date: '2024-08-01', description: 'Salary – Acme Corp', amount: 5200, currency: 'USD', category: 'Income' },
    { id: 'txn_aug_02', transaction_date: '2024-08-02', description: 'Rent – 412 Oak St', amount: -1550, currency: 'USD', category: 'Housing & Utilities' },
    { id: 'txn_aug_03', transaction_date: '2024-08-05', description: 'Whole Foods Market', amount: -172, currency: 'USD', category: 'Food & Groceries' },
    { id: 'txn_aug_04', transaction_date: '2024-08-12', description: 'Amazon – Back-to-School', amount: -290, currency: 'USD', category: 'Shopping' },
    { id: 'txn_aug_05', transaction_date: '2024-08-15', description: 'Target – Home Office', amount: -155, currency: 'USD', category: 'Shopping' },
    { id: 'txn_aug_06', transaction_date: '2024-08-18', description: 'MTA Metro Card', amount: -132, currency: 'USD', category: 'Transportation' },
    { id: 'txn_aug_07', transaction_date: '2024-08-22', description: 'Museum Memberships', amount: -85, currency: 'USD', category: 'Entertainment' },
    { id: 'txn_aug_08', transaction_date: '2024-08-25', description: 'Planet Fitness', amount: -25, currency: 'USD', category: 'Health & Fitness' },
    { id: 'txn_aug_09', transaction_date: '2024-08-31', description: 'Transfer to Savings', amount: -500, currency: 'USD', category: 'Internal Transfers' },

    // September
    { id: 'txn_sep_01', transaction_date: '2024-09-01', description: 'Salary – Acme Corp', amount: 5200, currency: 'USD', category: 'Income' },
    { id: 'txn_sep_02', transaction_date: '2024-09-02', description: 'Rent – 412 Oak St', amount: -1550, currency: 'USD', category: 'Housing & Utilities' },
    { id: 'txn_sep_03', transaction_date: '2024-09-07', description: 'Whole Foods Market', amount: -148, currency: 'USD', category: 'Food & Groceries' },
    { id: 'txn_sep_04', transaction_date: '2024-09-12', description: 'Chipotle', amount: -23, currency: 'USD', category: 'Food & Groceries' },
    { id: 'txn_sep_05', transaction_date: '2024-09-15', description: 'MTA Metro Card', amount: -132, currency: 'USD', category: 'Transportation' },
    { id: 'txn_sep_06', transaction_date: '2024-09-20', description: 'Apple Fitness+', amount: -80, currency: 'USD', category: 'Health & Fitness' },
    { id: 'txn_sep_07', transaction_date: '2024-09-22', description: 'Fall Market – Shopping', amount: -188, currency: 'USD', category: 'Shopping' },
    { id: 'txn_sep_08', transaction_date: '2024-09-30', description: 'Transfer to Savings', amount: -500, currency: 'USD', category: 'Internal Transfers' },

    // October
    { id: 'txn_oct_01', transaction_date: '2024-10-01', description: 'Salary – Acme Corp', amount: 5200, currency: 'USD', category: 'Income' },
    { id: 'txn_oct_02', transaction_date: '2024-10-02', description: 'Rent – 412 Oak St', amount: -1550, currency: 'USD', category: 'Housing & Utilities' },
    { id: 'txn_oct_03', transaction_date: '2024-10-05', description: 'Whole Foods Market', amount: -162, currency: 'USD', category: 'Food & Groceries' },
    { id: 'txn_oct_04', transaction_date: '2024-10-10', description: 'MTA Metro Card', amount: -132, currency: 'USD', category: 'Transportation' },
    { id: 'txn_oct_05', transaction_date: '2024-10-15', description: 'Halloween – Party Supplies', amount: -145, currency: 'USD', category: 'Shopping' },
    { id: 'txn_oct_06', transaction_date: '2024-10-20', description: 'Spotify Premium', amount: -11, currency: 'USD', category: 'Entertainment' },
    { id: 'txn_oct_07', transaction_date: '2024-10-24', description: 'Planet Fitness', amount: -25, currency: 'USD', category: 'Health & Fitness' },
    { id: 'txn_oct_08', transaction_date: '2024-10-31', description: 'Transfer to Savings', amount: -500, currency: 'USD', category: 'Internal Transfers' },

    // November — Black Friday
    { id: 'txn_nov_01', transaction_date: '2024-11-01', description: 'Salary – Acme Corp', amount: 5200, currency: 'USD', category: 'Income' },
    { id: 'txn_nov_02', transaction_date: '2024-11-02', description: 'Rent – 412 Oak St', amount: -1550, currency: 'USD', category: 'Housing & Utilities' },
    { id: 'txn_nov_03', transaction_date: '2024-11-04', description: 'Con Edison Electric', amount: -185, currency: 'USD', category: 'Housing & Utilities' },
    { id: 'txn_nov_04', transaction_date: '2024-11-08', description: 'Whole Foods Market', amount: -198, currency: 'USD', category: 'Food & Groceries' },
    { id: 'txn_nov_05', transaction_date: '2024-11-14', description: 'Trader Joe\'s', amount: -145, currency: 'USD', category: 'Food & Groceries' },
    { id: 'txn_nov_06', transaction_date: '2024-11-21', description: 'Thanksgiving Groceries – Costco', amount: -225, currency: 'USD', category: 'Food & Groceries' },
    { id: 'txn_nov_07', transaction_date: '2024-11-25', description: 'Airbnb – Thanksgiving Weekend', amount: -280, currency: 'USD', category: 'Entertainment' },
    { id: 'txn_nov_08', transaction_date: '2024-11-29', description: 'Black Friday – Amazon', amount: -320, currency: 'USD', category: 'Shopping' },
    { id: 'txn_nov_09', transaction_date: '2024-11-30', description: 'Transfer to Savings', amount: -500, currency: 'USD', category: 'Internal Transfers' },

    // December — bonus month, holiday spending
    { id: 'txn_dec_01', transaction_date: '2024-12-01', description: 'Salary – Acme Corp', amount: 5200, currency: 'USD', category: 'Income' },
    { id: 'txn_dec_02', transaction_date: '2024-12-02', description: 'Year-End Bonus', amount: 500, currency: 'USD', category: 'Income' },
    { id: 'txn_dec_03', transaction_date: '2024-12-02', description: 'Rent – 412 Oak St', amount: -1550, currency: 'USD', category: 'Housing & Utilities' },
    { id: 'txn_dec_04', transaction_date: '2024-12-04', description: 'Con Edison Electric', amount: -200, currency: 'USD', category: 'Housing & Utilities' },
    { id: 'txn_dec_05', transaction_date: '2024-12-05', description: 'Whole Foods Market', amount: -220, currency: 'USD', category: 'Food & Groceries' },
    { id: 'txn_dec_06', transaction_date: '2024-12-07', description: 'Holiday Party Catering', amount: -185, currency: 'USD', category: 'Food & Groceries' },
    { id: 'txn_dec_10', transaction_date: '2024-12-10', description: 'MTA Metro Card', amount: -132, currency: 'USD', category: 'Transportation' },
    { id: 'txn_dec_11', transaction_date: '2024-12-12', description: 'Nutcracker Ballet', amount: -120, currency: 'USD', category: 'Entertainment' },
    { id: 'txn_dec_13', transaction_date: '2024-12-14', description: 'Holiday Gifts – Amazon', amount: -380, currency: 'USD', category: 'Shopping' },
    { id: 'txn_dec_14', transaction_date: '2024-12-17', description: 'Holiday Gifts – Apple Store', amount: -250, currency: 'USD', category: 'Shopping' },
    { id: 'txn_dec_20', transaction_date: '2024-12-20', description: 'NYE Dinner Reservation', amount: -200, currency: 'USD', category: 'Entertainment' },
    { id: 'txn_dec_21', transaction_date: '2024-12-22', description: 'Christmas Dinner – Whole Foods', amount: -180, currency: 'USD', category: 'Food & Groceries' },
    { id: 'txn_dec_25', transaction_date: '2024-12-25', description: 'Planet Fitness', amount: -25, currency: 'USD', category: 'Health & Fitness' },
    { id: 'txn_dec_26', transaction_date: '2024-12-26', description: 'Airbnb – NYE Getaway', amount: -100, currency: 'USD', category: 'Entertainment' },
    { id: 'txn_dec_31', transaction_date: '2024-12-31', description: 'Transfer to Savings', amount: -500, currency: 'USD', category: 'Internal Transfers' },
  ],

  // ── pivot table ─────────────────────────────────────────────────────────────
  pivot: {
    categories: CATEGORIES,
    months: MONTHS,
    actuals: ACTUALS,
    budgets: BUDGETS,
    transaction_counts: TX_COUNTS,
    category_totals: categoryTotals,
    category_budget_totals: categoryBudgetTotals,
    month_totals: monthTotals,
    month_budget_totals: monthBudgetTotals,
    category_shares: categoryShares,
    currency: 'USD',
  },

  // ── metrics (full-year aggregate, latest month = Dec 2024) ─────────────────
  metrics: {
    inflows: 61900,
    outflows: 41995,
    internal_transfers: 6000,
    net_cash: 13905,
    budget_coverage_pct: 103.4,
    latest_month: '2024-12',
    previous_month: '2024-11',
    month_over_month_delta: -60,
    month_over_month_pct: -6.4,
    segments: [
      { name: 'inflows',            actual: 5700, budget: 5200, variance: 500,  variance_pct: 9.6 },
      { name: 'outflows',           actual: 4320, budget: 4000, variance: 320,  variance_pct: 8.0 },
      { name: 'internal_transfers', actual: 500,  budget: 500,  variance: 0,    variance_pct: 0.0 },
    ],
    top_variances: [
      { category: 'Food & Groceries',    actual: -850, budget: -700, variance: -150, variance_pct: 21.4, direction: 'over' },
      { category: 'Entertainment',       actual: -420, budget: -350, variance: -70,  variance_pct: 20.0, direction: 'over' },
      { category: 'Shopping',            actual: -780, budget: -700, variance: -80,  variance_pct: 11.4, direction: 'over' },
      { category: 'Income',              actual: 5700, budget: 5200, variance: 500,  variance_pct: 9.6,  direction: 'over' },
    ],
  },

  // ── category summaries (per category × month × bank) ───────────────────────
  category_summaries: [
    // January
    { category: 'Income',              month: '2024-01', bank: 'Chase', amount: 5000,  count: 1 },
    { category: 'Housing & Utilities', month: '2024-01', bank: 'Chase', amount: -1800, count: 3 },
    { category: 'Food & Groceries',    month: '2024-01', bank: 'Chase', amount: -580,  count: 8 },
    { category: 'Transportation',      month: '2024-01', bank: 'Chase', amount: -290,  count: 5 },
    { category: 'Entertainment',       month: '2024-01', bank: 'Amex',  amount: -180,  count: 4 },
    { category: 'Health & Fitness',    month: '2024-01', bank: 'Chase', amount: -100,  count: 2 },
    { category: 'Shopping',            month: '2024-01', bank: 'Amex',  amount: -250,  count: 3 },
    { category: 'Internal Transfers',  month: '2024-01', bank: 'Chase', amount: -500,  count: 1 },
    // February
    { category: 'Income',              month: '2024-02', bank: 'Chase', amount: 5000,  count: 1 },
    { category: 'Housing & Utilities', month: '2024-02', bank: 'Chase', amount: -1800, count: 3 },
    { category: 'Food & Groceries',    month: '2024-02', bank: 'Chase', amount: -540,  count: 7 },
    { category: 'Transportation',      month: '2024-02', bank: 'Chase', amount: -270,  count: 4 },
    { category: 'Entertainment',       month: '2024-02', bank: 'Amex',  amount: -160,  count: 3 },
    { category: 'Health & Fitness',    month: '2024-02', bank: 'Chase', amount: -100,  count: 2 },
    { category: 'Shopping',            month: '2024-02', bank: 'Amex',  amount: -180,  count: 2 },
    { category: 'Internal Transfers',  month: '2024-02', bank: 'Chase', amount: -500,  count: 1 },
    // March
    { category: 'Income',              month: '2024-03', bank: 'Chase', amount: 5000,  count: 1 },
    { category: 'Housing & Utilities', month: '2024-03', bank: 'Chase', amount: -1800, count: 3 },
    { category: 'Food & Groceries',    month: '2024-03', bank: 'Chase', amount: -620,  count: 9 },
    { category: 'Transportation',      month: '2024-03', bank: 'Chase', amount: -310,  count: 6 },
    { category: 'Entertainment',       month: '2024-03', bank: 'Amex',  amount: -200,  count: 4 },
    { category: 'Health & Fitness',    month: '2024-03', bank: 'Chase', amount: -100,  count: 2 },
    { category: 'Shopping',            month: '2024-03', bank: 'Amex',  amount: -290,  count: 4 },
    { category: 'Internal Transfers',  month: '2024-03', bank: 'Chase', amount: -500,  count: 1 },
    // April
    { category: 'Income',              month: '2024-04', bank: 'Chase', amount: 5000,  count: 1 },
    { category: 'Housing & Utilities', month: '2024-04', bank: 'Chase', amount: -1800, count: 3 },
    { category: 'Food & Groceries',    month: '2024-04', bank: 'Chase', amount: -590,  count: 8 },
    { category: 'Transportation',      month: '2024-04', bank: 'Chase', amount: -320,  count: 5 },
    { category: 'Entertainment',       month: '2024-04', bank: 'Amex',  amount: -220,  count: 5 },
    { category: 'Health & Fitness',    month: '2024-04', bank: 'Chase', amount: -100,  count: 2 },
    { category: 'Shopping',            month: '2024-04', bank: 'Amex',  amount: -340,  count: 5 },
    { category: 'Internal Transfers',  month: '2024-04', bank: 'Chase', amount: -500,  count: 1 },
    // May
    { category: 'Income',              month: '2024-05', bank: 'Chase', amount: 5000,  count: 1 },
    { category: 'Housing & Utilities', month: '2024-05', bank: 'Chase', amount: -1800, count: 3 },
    { category: 'Food & Groceries',    month: '2024-05', bank: 'Chase', amount: -610,  count: 9 },
    { category: 'Transportation',      month: '2024-05', bank: 'Chase', amount: -280,  count: 5 },
    { category: 'Entertainment',       month: '2024-05', bank: 'Amex',  amount: -280,  count: 6 },
    { category: 'Health & Fitness',    month: '2024-05', bank: 'Chase', amount: -100,  count: 2 },
    { category: 'Shopping',            month: '2024-05', bank: 'Amex',  amount: -260,  count: 4 },
    { category: 'Internal Transfers',  month: '2024-05', bank: 'Chase', amount: -500,  count: 1 },
    // June
    { category: 'Income',              month: '2024-06', bank: 'Chase', amount: 5200,  count: 1 },
    { category: 'Housing & Utilities', month: '2024-06', bank: 'Chase', amount: -1800, count: 3 },
    { category: 'Food & Groceries',    month: '2024-06', bank: 'Chase', amount: -640,  count: 10 },
    { category: 'Transportation',      month: '2024-06', bank: 'Chase', amount: -350,  count: 7 },
    { category: 'Entertainment',       month: '2024-06', bank: 'Amex',  amount: -310,  count: 7 },
    { category: 'Health & Fitness',    month: '2024-06', bank: 'Chase', amount: -100,  count: 2 },
    { category: 'Shopping',            month: '2024-06', bank: 'Amex',  amount: -310,  count: 5 },
    { category: 'Internal Transfers',  month: '2024-06', bank: 'Chase', amount: -500,  count: 1 },
    // July
    { category: 'Income',              month: '2024-07', bank: 'Chase', amount: 5200,  count: 1 },
    { category: 'Housing & Utilities', month: '2024-07', bank: 'Chase', amount: -1850, count: 3 },
    { category: 'Food & Groceries',    month: '2024-07', bank: 'Chase', amount: -680,  count: 11 },
    { category: 'Transportation',      month: '2024-07', bank: 'Chase', amount: -380,  count: 8 },
    { category: 'Entertainment',       month: '2024-07', bank: 'Amex',  amount: -350,  count: 8 },
    { category: 'Health & Fitness',    month: '2024-07', bank: 'Chase', amount: -100,  count: 2 },
    { category: 'Shopping',            month: '2024-07', bank: 'Amex',  amount: -280,  count: 4 },
    { category: 'Internal Transfers',  month: '2024-07', bank: 'Chase', amount: -500,  count: 1 },
    // August
    { category: 'Income',              month: '2024-08', bank: 'Chase', amount: 5200,  count: 1 },
    { category: 'Housing & Utilities', month: '2024-08', bank: 'Chase', amount: -1850, count: 3 },
    { category: 'Food & Groceries',    month: '2024-08', bank: 'Chase', amount: -660,  count: 10 },
    { category: 'Transportation',      month: '2024-08', bank: 'Chase', amount: -340,  count: 7 },
    { category: 'Entertainment',       month: '2024-08', bank: 'Amex',  amount: -290,  count: 6 },
    { category: 'Health & Fitness',    month: '2024-08', bank: 'Chase', amount: -100,  count: 2 },
    { category: 'Shopping',            month: '2024-08', bank: 'Amex',  amount: -480,  count: 7 },
    { category: 'Internal Transfers',  month: '2024-08', bank: 'Chase', amount: -500,  count: 1 },
    // September
    { category: 'Income',              month: '2024-09', bank: 'Chase', amount: 5200,  count: 1 },
    { category: 'Housing & Utilities', month: '2024-09', bank: 'Chase', amount: -1850, count: 3 },
    { category: 'Food & Groceries',    month: '2024-09', bank: 'Chase', amount: -590,  count: 8 },
    { category: 'Transportation',      month: '2024-09', bank: 'Chase', amount: -295,  count: 5 },
    { category: 'Entertainment',       month: '2024-09', bank: 'Amex',  amount: -200,  count: 4 },
    { category: 'Health & Fitness',    month: '2024-09', bank: 'Chase', amount: -100,  count: 2 },
    { category: 'Shopping',            month: '2024-09', bank: 'Amex',  amount: -350,  count: 5 },
    { category: 'Internal Transfers',  month: '2024-09', bank: 'Chase', amount: -500,  count: 1 },
    // October
    { category: 'Income',              month: '2024-10', bank: 'Chase', amount: 5200,  count: 1 },
    { category: 'Housing & Utilities', month: '2024-10', bank: 'Chase', amount: -1850, count: 3 },
    { category: 'Food & Groceries',    month: '2024-10', bank: 'Chase', amount: -620,  count: 9 },
    { category: 'Transportation',      month: '2024-10', bank: 'Chase', amount: -310,  count: 6 },
    { category: 'Entertainment',       month: '2024-10', bank: 'Amex',  amount: -220,  count: 5 },
    { category: 'Health & Fitness',    month: '2024-10', bank: 'Chase', amount: -100,  count: 2 },
    { category: 'Shopping',            month: '2024-10', bank: 'Amex',  amount: -290,  count: 4 },
    { category: 'Internal Transfers',  month: '2024-10', bank: 'Chase', amount: -500,  count: 1 },
    // November
    { category: 'Income',              month: '2024-11', bank: 'Chase', amount: 5200,  count: 1 },
    { category: 'Housing & Utilities', month: '2024-11', bank: 'Chase', amount: -1850, count: 3 },
    { category: 'Food & Groceries',    month: '2024-11', bank: 'Chase', amount: -730,  count: 12 },
    { category: 'Transportation',      month: '2024-11', bank: 'Chase', amount: -280,  count: 5 },
    { category: 'Entertainment',       month: '2024-11', bank: 'Amex',  amount: -280,  count: 6 },
    { category: 'Health & Fitness',    month: '2024-11', bank: 'Chase', amount: -100,  count: 2 },
    { category: 'Shopping',            month: '2024-11', bank: 'Amex',  amount: -520,  count: 8 },
    { category: 'Internal Transfers',  month: '2024-11', bank: 'Chase', amount: -500,  count: 1 },
    // December
    { category: 'Income',              month: '2024-12', bank: 'Chase', amount: 5700,  count: 2 },
    { category: 'Housing & Utilities', month: '2024-12', bank: 'Chase', amount: -1850, count: 3 },
    { category: 'Food & Groceries',    month: '2024-12', bank: 'Chase', amount: -850,  count: 14 },
    { category: 'Transportation',      month: '2024-12', bank: 'Chase', amount: -320,  count: 6 },
    { category: 'Entertainment',       month: '2024-12', bank: 'Amex',  amount: -420,  count: 8 },
    { category: 'Health & Fitness',    month: '2024-12', bank: 'Chase', amount: -100,  count: 2 },
    { category: 'Shopping',            month: '2024-12', bank: 'Amex',  amount: -780,  count: 12 },
    { category: 'Internal Transfers',  month: '2024-12', bank: 'Chase', amount: -500,  count: 1 },
  ],

  summary_count: 96,
};

export function getMockDashboardData(): DashboardProps {
  return mockDashboardData;
}
