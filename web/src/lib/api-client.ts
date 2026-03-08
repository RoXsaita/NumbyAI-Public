/**
 * API Client - REST API client for NumbyAI backend
 */
import type { DashboardProps } from '../shared/schemas';
import { getEnvVar } from '../config';

const API_BASE_URL =
  getEnvVar('VITE_API_BASE_URL') ||
  getEnvVar('VITE_API_URL') ||
  getEnvVar('API_BASE_URL') ||
  'http://localhost:8000';

export interface Transaction {
  id: string;
  date: string;
  description: string;
  merchant: string | null;
  amount: number;
  currency: string;
  category: string;
  category_source?: 'rule' | 'ai' | 'manual' | null;
  bank_name: string;
  profile: string | null;
}

export interface TransactionFilters {
  bank_name?: string;
  category?: string;
  date_from?: string;
  date_to?: string;
}

export interface Budget {
  category: string;
  month_year: string | null;
  amount: number;
  currency: string;
}

export interface Preferences {
  preferences?: any[];
  settings?: any;
  summary?: any;
  categorization?: any[];
  parsing?: any[];
}


export interface ReviewTransaction {
  id: string;
  date: string;
  description: string;
  merchant: string | null;
  amount: number;
  currency: string;
  category: string;
  category_source?: 'rule' | 'ai' | 'manual' | null;
  bank_name: string;
  review_priority: 'manual_review' | 'ai_conflict' | 'high_amount' | 'recurring';
  is_recurring: boolean;
  review_status?: string | null;
  review_category?: string | null;
  review_reason?: string | null;
}

export interface ReviewQueueResponse {
  transactions: ReviewTransaction[];
  total_count: number;
  total_absolute_value: number;
  materiality_threshold: number;
  manual_review_count: number;
  conflict_count?: number;
}

export interface RuleAnalysisRun {
  id: string;
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
  scope_since: string | null;
  started_at: string | null;
  completed_at: string | null;
  summary: Record<string, number>;
  error_message: string | null;
  total_findings: number;
  open_findings: number;
  type_counts: Record<string, number>;
}

export interface RuleAnalysisFinding {
  id: string;
  run_id: string;
  finding_type: 'tx_conflict' | 'rule_suggestion' | 'rule_fix';
  status: 'open' | 'applied' | 'dismissed';
  confidence: number;
  bank_name: string | null;
  payload: Record<string, any>;
  created_at: string | null;
  resolved_at: string | null;
}

export type CategoryMutationOperation =
  | {
      type: 'edit';
      category: string;
      new_amount: number;
      note?: string;
    }
  | {
      type: 'transfer';
      from_category: string;
      to_category: string;
      transfer_amount: number;
      note?: string;
    };

class ApiClient {
  private baseUrl: string;
  private authToken: string | null = null;

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl.replace(/\/$/, ''); // Remove trailing slash
  }

  setAuthToken(token: string | null) {
    this.authToken = token;
  }

  private buildQueryParams(filters: Record<string, unknown>): string {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(filters)) {
      if (value === undefined || value === null) continue;
      if (Array.isArray(value)) {
        value.forEach(v => params.append(key, String(v)));
      } else {
        params.append(key, String(value));
      }
    }
    const query = params.toString();
    return query ? `?${query}` : '';
  }

  private async fetchWithFormData<T>(
    endpoint: string,
    file: File,
    fields: Record<string, string | undefined | null>,
    extraHeaders?: Record<string, string>
  ): Promise<Response> {
    const formData = new FormData();
    formData.append('file', file);
    for (const [key, value] of Object.entries(fields)) {
      if (value !== undefined && value !== null) {
        formData.append(key, value);
      }
    }

    const headers: Record<string, string> = {
      ...(this.authToken ? { Authorization: `Bearer ${this.authToken}` } : {}),
      ...extraHeaders,
    };

    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      method: 'POST',
      body: formData,
      headers,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: response.statusText }));
      throw new Error(error.error || `Request failed: ${response.statusText}`);
    }

    return response;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
      ...options.headers,
    };

    if (this.authToken) {
      headers['Authorization'] = `Bearer ${this.authToken}`;
    }

    const response = await fetch(url, {
      ...options,
      headers,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: response.statusText }));
      throw new Error(error.error || `HTTP ${response.status}: ${response.statusText}`);
    }

    return response.json();
  }

  // Financial data
  async getFinancialData(filters?: {
    bank_name?: string;
    month_year?: string;
    categories?: string[];
    profile?: string;
  }): Promise<DashboardProps> {
    const qs = this.buildQueryParams({
      bank_name: filters?.bank_name,
      month_year: filters?.month_year,
      categories: filters?.categories,
      profile: filters?.profile,
    });
    return this.request<DashboardProps>(`/api/financial-data${qs}`);
  }

  // Transactions
  async getTransactions(filters?: TransactionFilters): Promise<{
    transactions: Transaction[];
    count: number;
  }> {
    const qs = this.buildQueryParams({
      bank_name: filters?.bank_name,
      category: filters?.category,
      date_from: filters?.date_from,
      date_to: filters?.date_to,
    });
    return this.request<{ transactions: Transaction[]; count: number }>(
      `/api/transactions${qs}`
    );
  }

  async updateTransaction(
    id: string,
    updates: Partial<Transaction>
  ): Promise<Transaction> {
    return this.request<Transaction>('/api/transactions', {
      method: 'PATCH',
      body: JSON.stringify({ id, updates }),
    });
  }

  // Budgets
  async getBudgets(): Promise<{ budgets: Budget[] }> {
    return this.request<{ budgets: Budget[] }>('/api/budgets');
  }

  async saveBudget(budgets: Budget[]): Promise<void> {
    await this.request('/api/budgets', {
      method: 'POST',
      body: JSON.stringify({ budgets }),
    });
  }

  // Preferences
  async getPreferences(
    preferenceType?: 'categorization' | 'parsing' | 'settings' | 'list',
    bankName?: string
  ): Promise<Preferences> {
    const qs = this.buildQueryParams({
      preference_type: preferenceType,
      bank_name: bankName,
    });
    return this.request<Preferences>(`/api/preferences${qs}`);
  }

  async savePreferences(
    preferences: any[],
    preferenceType: 'categorization' | 'parsing' | 'settings' = 'categorization'
  ): Promise<void> {
    await this.request('/api/preferences', {
      method: 'POST',
      body: JSON.stringify({ preferences, preference_type: preferenceType }),
    });
  }

  async deletePreference(preferenceId: string): Promise<void> {
    await this.request(`/api/preferences/${preferenceId}`, {
      method: 'DELETE',
    });
  }

  async getManualReviewTransactions(params?: {
    bank_name?: string;
    limit?: number;
    offset?: number;
  }): Promise<{ transactions: Transaction[]; count: number; total: number }> {
    const qs = this.buildQueryParams({
      bank_name: params?.bank_name,
      limit: params?.limit,
      offset: params?.offset,
    });
    return this.request(`/api/transactions/manual-review${qs}`);
  }

  async categorizeManualReview(data: {
    id: string;
    category: string;
    create_rule?: boolean;
    rule_pattern?: string;
    pattern_type?: string;
  }): Promise<{ transaction_id: string; category: string; rule_created: boolean }> {
    return this.request('/api/transactions/manual-review/categorize', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async getReviewConflicts(params?: {
    bank_name?: string;
    limit?: number;
    offset?: number;
  }): Promise<{ transactions: ReviewTransaction[]; count: number; total: number }> {
    const qs = this.buildQueryParams({
      bank_name: params?.bank_name,
      limit: params?.limit,
      offset: params?.offset,
    });
    return this.request(`/api/transactions/review-conflicts${qs}`);
  }

  async resolveConflict(data: {
    id: string;
    chosen_category: string;
    create_rule?: boolean;
    rule_pattern?: string;
  }): Promise<{ transaction_id: string; category: string; review_status: string; rule_created: boolean }> {
    return this.request('/api/transactions/resolve-conflict', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async startRuleAnalysis(data?: { since?: string }): Promise<{
    run_id: string;
    status: string;
    scope_since: string;
  }> {
    return this.request('/api/rules/analyze', {
      method: 'POST',
      body: JSON.stringify(data || {}),
    });
  }

  async getLatestRuleAnalysisRun(): Promise<{ run: RuleAnalysisRun | null }> {
    return this.request('/api/rules/analyze/latest');
  }

  async getRuleAnalysisRun(runId: string): Promise<RuleAnalysisRun> {
    return this.request(`/api/rules/analyze/${runId}`);
  }

  async getRuleAnalysisFindings(
    runId: string,
    params?: {
      status?: 'open' | 'applied' | 'dismissed';
      type?: 'tx_conflict' | 'rule_suggestion' | 'rule_fix';
      limit?: number;
      offset?: number;
    }
  ): Promise<{ findings: RuleAnalysisFinding[]; count: number; total: number }> {
    const qs = this.buildQueryParams({
      status: params?.status,
      type: params?.type,
      limit: params?.limit,
      offset: params?.offset,
    });
    return this.request(`/api/rules/analyze/${runId}/findings${qs}`);
  }

  async applyRuleAnalysisFinding(findingId: string): Promise<{
    finding_id: string;
    status: string;
    result: Record<string, any>;
  }>;
  async applyRuleAnalysisFinding(
    findingId: string,
    data?: {
      chosen_category?: string;
    }
  ): Promise<{
    finding_id: string;
    status: string;
    result: Record<string, any>;
  }> {
    return this.request(`/api/rules/analyze/findings/${findingId}/apply`, {
      method: 'POST',
      body: JSON.stringify(data || {}),
    });
  }

  async dismissRuleAnalysisFinding(findingId: string): Promise<{
    finding_id: string;
    status: string;
  }> {
    return this.request(`/api/rules/analyze/findings/${findingId}/dismiss`, {
      method: 'POST',
      body: JSON.stringify({}),
    });
  }

  async cleanupRules(): Promise<{ deleted: number; status: string }> {
    return this.request('/api/preferences/cleanup-rules', { method: 'POST' });
  }

  async getCategories(): Promise<{ categories: string[] }> {
    return this.request('/api/categories');
  }

  async getTransactionReviewQueue(
    bankName: string,
    since: string
  ): Promise<ReviewQueueResponse> {
    const params = new URLSearchParams();
    params.append('bank_name', bankName);
    params.append('since', since);
    return this.request<ReviewQueueResponse>(
      `/api/transactions/review-queue?${params.toString()}`
    );
  }

  async getProfiles(): Promise<{ profiles: string[] }> {
    return this.request('/api/profiles');
  }

  // Data management
  async getDataManagementSummary(): Promise<{
    months: string[];
    banks: string[];
    banks_detail: { bank: string; months: string[]; tx_count: number }[];
    profiles_detail: { profile: string; tx_count: number }[];
    transaction_count: number;
    categorization_rules_count: number;
    parsing_rules_count: number;
    budget_count: number;
  }> {
    return this.request('/api/data-management/summary');
  }

  async deleteTransactions(filters: {
    month?: string;
    bank_name?: string;
  }): Promise<{ deleted: number; status: string }> {
    return this.request('/api/data-management/transactions', {
      method: 'DELETE',
      body: JSON.stringify(filters),
    });
  }

  async deletePreferencesBulk(
    preferenceType: 'categorization' | 'parsing'
  ): Promise<{ deleted: number; status: string }> {
    return this.request('/api/data-management/preferences', {
      method: 'DELETE',
      body: JSON.stringify({ preference_type: preferenceType }),
    });
  }

  async deleteBudgets(): Promise<{ deleted: number; status: string }> {
    return this.request('/api/data-management/budgets', {
      method: 'DELETE',
    });
  }

  async commitPreview(previewId: string): Promise<{
    status: string;
    transactions_processed: number;
    manual_review_count: number;
    dashboard: any;
  }> {
    return this.request('/api/statements/commit', {
      method: 'POST',
      body: JSON.stringify({ preview_id: previewId }),
    });
  }

  async mutateCategories(input: {
    operations: CategoryMutationOperation[];
    bank_name?: string;
    month_year?: string;
  }): Promise<{ updated_categories: Record<string, number>; change_summary: any[]; status: string }> {
    return this.request('/api/mutate-categories', {
      method: 'POST',
      body: JSON.stringify(input),
    });
  }

  // Statement upload
  async uploadStatement(
    file: File,
    netFlow?: number,
    bankName?: string
  ): Promise<{
    job_id: string;
    status: string;
    analysis?: any;
    transactions_count?: number;
    transactions?: any[];
    currency_detected?: string | null;
    currency_required?: boolean;
    parsing_preferences_exist?: boolean;
    detected_headers?: string[];
  }> {
    const response = await this.fetchWithFormData('/api/statements/upload', file, {
      net_flow: netFlow !== undefined ? netFlow.toString() : undefined,
      bank_name: bankName,
    });
    return response.json();
  }

  // Banks management
  async getBanks(): Promise<{ banks: string[] }> {
    const response = await this.request<any>('/api/preferences?preference_type=settings');
    // Response structure: { settings: { registered_banks: [...] } }
    const settings = response?.settings || {};
    return { banks: settings.registered_banks || [] };
  }

  async addBank(bankName: string): Promise<void> {
    const currentBanks = await this.getBanks();
    const updatedBanks = [...currentBanks.banks, bankName];
    await this.savePreferences(
      [{
        registered_banks: updatedBanks
      }],
      'settings'
    );
  }

  // Currency management
  async saveCurrency(currency: string): Promise<void> {
    await this.savePreferences(
      [{
        functional_currency: currency
      }],
      'settings'
    );
  }

  async getCurrency(): Promise<string | null> {
    const response = await this.request<any>('/api/preferences?preference_type=settings');
    // Response structure: { settings: { functional_currency: "USD" } }
    const settings = response?.settings || {};
    return settings.functional_currency || null;
  }

  // Header mapping
  async saveHeaderMapping(
    bankName: string,
    mapping: {
      column_mappings: any;  // New structure: field type -> column reference
      amount_column_inversions?: Record<string, boolean>;
      invert_amount_sign?: boolean;
      has_headers?: boolean;
      first_transaction_row?: number;
      date_format?: string;
      currency?: string;
    }
  ): Promise<void> {
    const schema = {
      column_mappings: mapping.column_mappings || {},
      amount_column_inversions: mapping.amount_column_inversions || {},
      invert_amount_sign: mapping.invert_amount_sign || false,
      date_format: mapping.date_format || 'DD/MM/YYYY',
      currency: mapping.currency || 'USD',
      has_headers: mapping.has_headers ?? true,
      skip_rows: 0,  // Will be calculated from first_transaction_row in parser
      first_transaction_row: mapping.first_transaction_row || 1,
      amount_positive_is: 'debit',
    };

    await this.savePreferences(
      [{
        name: `parsing_${bankName}_csv`,
        bank_name: bankName,
        instructions: schema,
      }],
      'parsing'
    );
  }

  // Process statement with all collected data
  async processStatement(
    file: File,
    bankName: string,
    netFlow?: number,
    headerMapping?: {
      column_mappings: any;
      amount_column_inversions?: Record<string, boolean>;
      invert_amount_sign?: boolean;
      has_headers?: boolean;
      first_transaction_row?: number;
      date_format?: string;
      currency?: string;
    },
    excludedTransactionRows?: number[],
    llmProvider?: StatementLlmProvider
  ): Promise<{
    status: string;
    transactions_processed?: number;
    categories?: number;
    dashboard?: any;
    message?: string;
  }> {
    const response = await this.fetchWithFormData('/api/statements/process', file, {
      bank_name: bankName,
      net_flow: netFlow !== undefined ? netFlow.toString() : undefined,
      header_mapping: headerMapping ? JSON.stringify(headerMapping) : undefined,
      excluded_transaction_rows: excludedTransactionRows ? JSON.stringify(excludedTransactionRows) : undefined,
      llm_provider: llmProvider,
    });
    return response.json();
  }

  async processStatementStream(
    file: File,
    bankName: string,
    headerMapping: {
      column_mappings: any;
      amount_column_inversions?: Record<string, boolean>;
      invert_amount_sign?: boolean;
      has_headers?: boolean;
      first_transaction_row?: number;
      date_format?: string;
      currency?: string;
    } | undefined,
    excludedTransactionRows?: number[],
    onEvent?: (event: any) => void,
    profile?: string,
    force?: boolean
  ): Promise<{
    status: string;
    transactions_processed?: number;
    categories?: number;
    dashboard?: any;
    message?: string;
  }> {
    const response = await this.fetchWithFormData(
      '/api/statements/process-stream',
      file,
      {
        bank_name: bankName,
        header_mapping: headerMapping ? JSON.stringify(headerMapping) : undefined,
        excluded_transaction_rows: excludedTransactionRows ? JSON.stringify(excludedTransactionRows) : undefined,
        profile: profile || undefined,
        force: force ? 'true' : undefined,
      },
      { Accept: 'text/event-stream' }
    );

    const reader = response.body?.getReader();
    const decoder = new TextDecoder();

    if (!reader) {
      throw new Error('Response body is not readable');
    }

    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed || !trimmed.startsWith('data:')) continue;

        const payload = trimmed.slice(5).trim();
        if (!payload) continue;

        try {
          const event = JSON.parse(payload);
          if (event.type === 'complete') {
            return event.result;
          }
          if (event.type === 'error') {
            throw new Error(event.error || 'Processing failed');
          }
          if (onEvent) onEvent(event);
        } catch (e) {
          // Ignore malformed JSON fragments
        }
      }
    }

    throw new Error('Processing stream ended without completion');
  }

  async previewStatementNetFlow(
    file: File,
    bankName: string | undefined,
    headerMapping: {
      column_mappings: any;
      amount_column_inversions?: Record<string, boolean>;
      invert_amount_sign?: boolean;
      has_headers?: boolean;
      first_transaction_row?: number;
      date_format?: string;
      currency?: string;
      excluded_transaction_rows?: number[];
    }
  ): Promise<{
    transaction_count: number;
    parsed_transaction_count: number;
    excluded_transaction_count: number;
    excluded_transaction_rows: number[];
    net_flow: number;
    inflow_total: number;
    outflow_total: number;
    currency: string;
    first_transaction_row: number;
    invert_amount_sign: boolean;
    suspicious_transaction_count: number;
    suspicious_transactions: Array<{
      source_row_number: number;
      description: string;
      amount: number;
      reasons: Array<{
        code: string;
        label: string;
      }>;
    }>;
  }> {
    const response = await this.fetchWithFormData('/api/statements/net-flow-preview', file, {
      bank_name: bankName,
      header_mapping: JSON.stringify(headerMapping),
    });
    return response.json();
  }

  async getLlmModel(): Promise<string | null> {
    try {
      const response = await fetch(`${API_BASE_URL}/health`);
      if (!response.ok) return null;
      const data = await response.json();
      return data?.llm?.model ?? null;
    } catch {
      return null;
    }
  }
}

// Export singleton instance
export const apiClient = new ApiClient();
