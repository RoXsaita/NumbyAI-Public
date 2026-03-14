# NumbyAI Frontend

React SPA for the NumbyAI dashboard. Built with esbuild, served by FastAPI as static files.

## Overview

The frontend renders the full NumbyAI dashboard:
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
│   │   └── dashboard.tsx    # Main dashboard (~9000 lines)
│   ├── components/
│   │   ├── SimpleUpload.tsx  # Upload wizard
│   │   └── ErrorBoundary.tsx
│   ├── lib/
│   │   ├── api-client.ts         # Backend REST API client
│   │   ├── chart-builders.ts     # Chart rendering utilities
│   │   ├── data-transformers.ts  # Data processing
│   │   └── validation.ts         # Schema validation
│   ├── shared/
│   │   ├── schemas.ts     # Zod schemas matching backend Pydantic schemas
│   │   └── logger.ts      # Client-side logging
│   ├── mocks/
│   │   └── dashboard-mock-data.ts  # Used when DATA_SOURCE=mock
│   └── __tests__/
│       ├── api-client.test.ts
│       ├── mutate-categories.test.ts
│       └── schema-compat.test.ts
├── scripts/
│   ├── build-app.mjs            # App bundler (esbuild)
│   └── validate-mock-data.mjs   # Mock data schema validator
└── package.json
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

# Build the app (production)
npm run build

# Build with mock data (no backend needed)
DATA_SOURCE=mock npm run build:dev

# Run tests
npm test
```

No separate dev server -- FastAPI serves `web/dist/` as static files. After changing frontend code, run `npm run build` and refresh.

## Testing

```bash
# Run all tests
npm test

# Validate mock data against Zod schemas
npm run validate:mock
```
