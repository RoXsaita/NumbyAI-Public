import { apiClient } from '../lib/api-client';

import { apiClient } from '../lib/api-client';

describe('ApiClient statement processing', () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    global.fetch = originalFetch;
    jest.restoreAllMocks();
  });

  test('sends bank_name and file in formData', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      body: {
        getReader: () => ({
          read: jest
            .fn()
            .mockResolvedValueOnce({
              done: false,
              value: new TextEncoder().encode('data: {"type":"complete","result":{"status":"success"}}
'),
            })
            .mockResolvedValueOnce({ done: true, value: undefined }),
        }),
      },
      json: async () => ({ status: 'success' }),
    });
    global.fetch = fetchMock as typeof fetch;

    await apiClient.processStatementStream(
      new File(['date,description,amount
'], 'statement.csv', { type: 'text/csv' }),
      'ProviderBank',
      undefined,
      undefined,
    );

    const [, requestInit] = fetchMock.mock.calls[0];
    const formData = requestInit.body as FormData;
    expect(formData.get('bank_name')).toBe('ProviderBank');
  });
});

describe('ApiClient parsing preference persistence', () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    global.fetch = originalFetch;
    jest.restoreAllMocks();
  });

  test('saveHeaderMapping sends inversion flags inside parsing instructions', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ status: 'saved' }),
    });
    global.fetch = fetchMock as typeof fetch;

    await apiClient.saveHeaderMapping('Santander', {
      column_mappings: {
        date: '0',
        description: ['1'],
        amount: ['2', '3'],
      },
      amount_column_inversions: { '3': true },
      invert_amount_sign: true,
      first_transaction_row: 4,
      date_format: 'DD/MM/YYYY',
      currency: 'PLN',
    });

    const [, requestInit] = fetchMock.mock.calls[0];
    const body = JSON.parse(requestInit.body as string);

    expect(body.preference_type).toBe('parsing');
    expect(body.preferences).toEqual([
      {
        name: 'parsing_Santander_csv',
        bank_name: 'Santander',
        instructions: {
          column_mappings: {
            date: '0',
            description: ['1'],
            amount: ['2', '3'],
          },
          amount_column_inversions: { '3': true },
          invert_amount_sign: true,
          date_format: 'DD/MM/YYYY',
          currency: 'PLN',
          has_headers: true,
          skip_rows: 0,
          first_transaction_row: 4,
          amount_positive_is: 'debit',
        },
      },
    ]);
  });
});

describe('ApiClient rule analysis actions', () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    global.fetch = originalFetch;
    jest.restoreAllMocks();
  });

  test('applyRuleAnalysisFinding forwards a chosen category override', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ status: 'applied' }),
    });
    global.fetch = fetchMock as typeof fetch;

    await apiClient.applyRuleAnalysisFinding('finding-123', {
      chosen_category: 'Travel',
    });

    const [, requestInit] = fetchMock.mock.calls[0];
    const body = JSON.parse(requestInit.body as string);

    expect(body).toEqual({ chosen_category: 'Travel' });
  });
});
