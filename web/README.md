# Web Widgets

React-based widget components for the Finance Budgeting App dashboard.

## Overview

This package contains the frontend widgets that display financial data from the MCP server. The primary widget is the Dashboard, which provides:
- Overview metrics (inflows, outflows, net cash)
- Cashflow P&L view
- Spending trends visualization
- Budget tracking
- Detailed transaction breakdowns
- Bank and month filtering

## Structure

```
web/
├── src/
│   ├── widgets/
│   │   └── dashboard.tsx    # Main dashboard widget (4500+ lines)
│   ├── components/
│   │   └── ErrorBoundary.tsx
│   ├── lib/
│   │   ├── chart-builders.ts      # Chart rendering utilities
│   │   ├── data-transformers.ts   # Data processing
│   │   └── validation.ts          # Schema validation
│   ├── shared/
│   │   ├── schemas.ts     # Zod schemas matching backend
│   │   └── logger.ts      # Client-side logging
│   ├── mocks/
│   │   └── dashboard-mock-data.ts
│   └── __tests__/
│       ├── mutate-categories.test.ts
│       └── schema-compat.test.ts
├── scripts/
│   ├── build-widgets.mjs   # Widget bundler
│   └── validate-mock-data.mjs
├── package.json
└── widgets.config.json     # Widget configuration
```

## Dashboard Tabs

| Tab | Description |
|-----|-------------|
| Overview | KPI cards, category distribution, month-over-month changes |
| Cashflow | Income vs expenses breakdown, P&L statement |
| Trends | Spending trends over time, category comparisons |
| Budget | Budget vs actual tracking, variance analysis |
| Details | Full transaction table with inline editing |

## Setup

```bash
# Install dependencies
npm install

# Build widgets
npm run build

# Run tests
npm test
```

## Usage

The dashboard widget receives data from the MCP server's `get_financial_data` tool and renders it using:
- `structuredContent` - AI-friendly data summary
- `_meta` - Full widget props including pivot table with budgets

## Testing

```bash
# Run all tests
npm test

# Validate mock data against schemas
npm run validate-mocks
```
