/**
 * Simple Upload Page - Multi-step Statement Processing Wizard
 * 
 * Step-by-step flow:
 * 1. Bank selection (required first — determines whether AI analysis is needed)
 * 2. File upload (bank with saved rules skips AI; new bank runs analysis)
 * 3. Currency selection (if needed)
 * 4. Header mapping (new banks only, pre-populated by auto-detection)
 * 5. Processing
 * 6. Dashboard
 */
import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { apiClient, type ReviewQueueResponse } from '../lib/api-client';
import { config } from '../config';
import type { DashboardProps } from '../shared/schemas';
import { getErrorMessage } from '../lib/utils';
import { DashboardWidget } from '../widgets/dashboard';

type UploadStep =
  | 'file_upload'
  | 'currency_selection'
  | 'bank_selection'
  | 'header_mapping'
  | 'processing'
  | 'review'
  | 'success';

const COMMON_CURRENCIES = [
  'USD', 'EUR', 'GBP', 'JPY', 'CHF', 'CAD', 'AUD', 'NZD', 'CNY', 'HKD',
  'SGD', 'SEK', 'NOK', 'DKK', 'PLN', 'CZK', 'HUF', 'RON', 'BGN', 'HRK',
  'RUB', 'TRY', 'ZAR', 'BRL', 'MXN', 'ARS', 'CLP', 'COP', 'PEN', 'INR',
  'IDR', 'MYR', 'PHP', 'THB', 'VND', 'KRW', 'TWD', 'ILS', 'AED', 'SAR',
  'QAR', 'KWD', 'BHD', 'OMR', 'JOD', 'EGP', 'NGN', 'KES', 'GHS', 'MAD',
];



// Helper function to convert column index to Excel-style letter (A, B, C... AA, AB, etc.)
const getColumnLetter = (index: number): string => {
  let result = '';
  index++; // Convert 0-indexed to 1-indexed
  while (index > 0) {
    index--;
    result = String.fromCharCode(65 + (index % 26)) + result;
    index = Math.floor(index / 26);
  }
  return result;
};

const hasDistinctReviewerCategory = (category?: string | null, reviewCategory?: string | null): boolean => {
  const current = (category || '').trim().toLowerCase();
  const suggestedRaw = (reviewCategory || '').trim();
  if (!suggestedRaw) return true;
  const suggested = suggestedRaw.toLowerCase();
  return suggested !== current;
};

const DEFAULT_BATCH_TELEMETRY: BatchTelemetry = {
  totalBatches: 0,
  completedBatches: 0,
  failedBatches: 0,
  activeBatches: 0,
  workers: 0,
  parallel: false,
  totalTransactions: 0,
  startedAt: null,
  avgBatchDurationMs: 0,
  etaMs: null,
};

interface BatchTelemetry {
  totalBatches: number;
  completedBatches: number;
  failedBatches: number;
  activeBatches: number;
  workers: number;
  parallel: boolean;
  totalTransactions: number;
  startedAt: number | null;
  avgBatchDurationMs: number;
  etaMs: number | null;
}

export const SimpleUpload: React.FC = () => {
  const [step, setStep] = useState<UploadStep>('file_upload');
  const [file, setFile] = useState<File | null>(null);
  const [uploadResult, setUploadResult] = useState<any>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<string>('');
  const [currency, setCurrency] = useState<string>('');
  const [userCurrency, setUserCurrency] = useState<string | null>(null);
  const [banks, setBanks] = useState<string[]>([]);
  const [bankName, setBankName] = useState<string>('');
  const [newBankName, setNewBankName] = useState<string>('');
  const [showNewBankInput, setShowNewBankInput] = useState(false);
  const [isLoadingBankPrefs, setIsLoadingBankPrefs] = useState(false);
  const [profiles, setProfiles] = useState<string[]>([]);
  const [selectedProfile, setSelectedProfile] = useState<string>('');
  const [newProfileName, setNewProfileName] = useState<string>('');
  const [showNewProfileInput, setShowNewProfileInput] = useState(false);
  // Column mappings: maps column index to field type
  const [columnMappings, setColumnMappings] = useState<{
    [columnIndex: number]: string;  // Maps column index to field type
  }>({});
  const [amountColumnInversions, setAmountColumnInversions] = useState<Record<number, boolean>>({});
  const [invertAmountSign, setInvertAmountSign] = useState(false);
  // Removed hasHeaders - we always use first_transaction_row instead
  const [firstTransactionRow, setFirstTransactionRow] = useState<number>(1);
  const [mappingNetFlowPreview, setMappingNetFlowPreview] = useState<{
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
      reasons: Array<{ code: string; label: string }>;
    }>;
    converted_net_flow?: number;
    converted_inflow_total?: number;
    converted_outflow_total?: number;
    functional_currency?: string;
  } | null>(null);
  const [excludedTransactionRows, setExcludedTransactionRows] = useState<number[]>([]);
  const [isCalculatingMappingNetFlow, setIsCalculatingMappingNetFlow] = useState(false);
  const [mappingNetFlowError, setMappingNetFlowError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [llmModel, setLlmModel] = useState<string | null>(null);
  const [processingProgress, setProcessingProgress] = useState<string>('');
  type StepStatus = 'pending' | 'active' | 'done' | 'error';
  interface PipelineStep {
    label: string;
    status: StepStatus;
    detail?: string;
    startedAt?: number;
    finishedAt?: number;
  }
  const [processingSteps, setProcessingSteps] = useState<PipelineStep[]>([]);
  const lastBankPrefsKey = useRef<string>('');
  const [dashboardOverride, setDashboardOverride] = useState<DashboardProps | null>(null);
  const [processingStartedAt, setProcessingStartedAt] = useState<string | null>(null);
  const [reviewData, setReviewData] = useState<ReviewQueueResponse | null>(null);
  const [pendingCategoryEdits, setPendingCategoryEdits] = useState<Record<string, string>>({});
  const [pendingRuleCreations, setPendingRuleCreations] = useState<Record<string, { enabled: boolean; pattern: string }>>({});
  const [availableCategories, setAvailableCategories] = useState<string[]>([]);
  const [isAutoDetected, setIsAutoDetected] = useState(false);
  const [detectionConfidence, setDetectionConfidence] = useState<Record<string, string>>({});
  const [isSavingReview, setIsSavingReview] = useState(false);

  // Observability state
  interface LogEntry {
    ts: number;
    elapsed_ms: number;
    level: 'info' | 'success' | 'warning' | 'error';
    message: string;
  }
  const [eventLog, setEventLog] = useState<LogEntry[]>([]);
  const [pipelineStats, setPipelineStats] = useState({
    parsed: 0,
    ruleMatched: 0,
    aiCategorized: 0,
    warnings: 0,
    errors: 0,
    categoryDistribution: {} as Record<string, number>,
    dateRange: null as { min: string; max: string; months: string[] } | null,
  });
  const [pipelineStartTime, setPipelineStartTime] = useState<number>(0);
  const [overallProgress, setOverallProgress] = useState(0);
  const logContainerRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const aiCategorizedTotalRef = useRef(0);
  const aiCategorizedCurrentPassRef = useRef(0);
  const aiTotalTransactionsRef = useRef(0);
  const aiLastProgressAtRef = useRef<number | null>(null);
  const serverStartedAtRef = useRef<string | null>(null);
  useEffect(() => {
    apiClient.getLlmModel().then(setLlmModel);
  }, []);

  const netFlowPreviewRequestRef = useRef(0);
  const prevStepRef = useRef<string | null>(null);
  const [duplicateWarning, setDuplicateWarning] = useState<{
    overlap_pct: number;
    existing_count: number;
    new_count: number;
    date_min: string;
    date_max: string;
  } | null>(null);

  const [batchTelemetry, setBatchTelemetry] = useState<BatchTelemetry>(DEFAULT_BATCH_TELEMETRY);

  const addLogEntry = useCallback((level: LogEntry['level'], message: string, elapsed_ms: number) => {
    setEventLog(prev => [...prev.slice(-79), { ts: Date.now(), elapsed_ms, level, message }]);
  }, []);

  useEffect(() => {
    if (autoScroll && logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [eventLog, autoScroll]);

  // Tick the elapsed timer during processing
  const [, setTick] = useState(0);
  useEffect(() => {
    if (step !== 'processing') return;
    const id = setInterval(() => setTick(t => t + 1), 250);
    return () => clearInterval(id);
  }, [step]);

  // Load user settings on mount
  useEffect(() => {
    loadUserSettings();
  }, []);

  const updateProcessingStep = (
    index: number,
    status: StepStatus,
    label?: string,
    detail?: string,
  ) => {
    setProcessingSteps((prev) => {
      if (!prev.length) return prev;
      const now = Date.now();
      return prev.map((s, idx) => {
        if (idx !== index) return s;
        return {
          ...s,
          status,
          label: label ?? s.label,
          detail: detail ?? s.detail,
          startedAt: status === 'active' && !s.startedAt ? now : s.startedAt,
          finishedAt: (status === 'done' || status === 'error') ? now : s.finishedAt,
        };
      });
    });
  };

  const initializeProcessingProgress = () => {
    const steps: PipelineStep[] = [
      { label: 'Validating file', status: 'active', startedAt: Date.now() },
      { label: 'Parsing transactions', status: 'pending' },
      { label: 'Applying rules', status: 'pending' },
      { label: 'AI categorization', status: 'pending' },
      { label: 'Reviewing categorizations', status: 'pending' },
      { label: 'Saving transactions', status: 'pending' },
      { label: 'Building dashboard', status: 'pending' },
    ];
    setProcessingSteps(steps);
    setProcessingProgress('Validating file...');
    setPipelineStartTime(Date.now());
    setEventLog([]);
    setPipelineStats({ parsed: 0, ruleMatched: 0, aiCategorized: 0, warnings: 0, errors: 0, categoryDistribution: {}, dateRange: null });
    aiCategorizedTotalRef.current = 0;
    aiCategorizedCurrentPassRef.current = 0;
    aiTotalTransactionsRef.current = 0;
    aiLastProgressAtRef.current = null;
    setOverallProgress(0);
    setAutoScroll(true);
    setBatchTelemetry(DEFAULT_BATCH_TELEMETRY);
  };

  const handleProcessingEvent = (event: any) => {
    if (!event) return;
    const elapsed = event.elapsed_ms ?? 0;

    if (event.type === 'stage') {
      if (event.name === 'file_saved') {
        if (event.server_started_at) {
          serverStartedAtRef.current = event.server_started_at;
          setProcessingStartedAt(event.server_started_at);
        }
        updateProcessingStep(0, 'done');
        updateProcessingStep(1, 'active');
        setProcessingProgress('Parsing transactions...');
        setOverallProgress(5);
        addLogEntry('success', 'File validated and saved', elapsed);
      } else if (event.name === 'parsed') {
        const txCount = event.transactions || 0;
        const dr = event.date_range;
        updateProcessingStep(1, 'done', undefined, `${txCount} transactions${dr ? `, ${dr.months.length} month(s)` : ''}`);
        updateProcessingStep(2, 'active');
        setProcessingProgress('Applying categorization rules...');
        setOverallProgress(15);
        setPipelineStats(prev => ({ ...prev, parsed: txCount, dateRange: dr || null }));
        const rangeInfo = dr ? ` (${dr.min} to ${dr.max}, ${dr.months.length} month(s))` : '';
        addLogEntry('success', `Parsed ${txCount} transactions${rangeInfo}`, elapsed);
      } else if (event.name === 'transactions_saved') {
        updateProcessingStep(5, 'done', undefined, `${event.transactions || 0} saved`);
        updateProcessingStep(6, 'active');
        setProcessingProgress('Building dashboard...');
        setOverallProgress(93);
        if (event.categories) {
          setPipelineStats(prev => ({ ...prev, categoryDistribution: event.categories }));
        }
        const reviewNote = event.manual_review_count ? ` (${event.manual_review_count} need manual review)` : '';
        const conflictNote = event.conflict_count ? ` (${event.conflict_count} conflicts)` : '';
        addLogEntry('success', `Saved ${event.transactions || 0} transactions to database${reviewNote}${conflictNote}`, elapsed);
      } else if (event.name === 'dashboard_ready') {
        updateProcessingStep(6, 'done');
        setProcessingProgress('Complete!');
        setOverallProgress(100);
        addLogEntry('success', 'Dashboard ready', elapsed);
      }
      return;
    }

    if (event.type === 'rule_match_summary') {
      const matched = event.rule_matched || 0;
      const unmatched = event.uncategorized || 0;
      updateProcessingStep(2, 'done', undefined, `${matched} matched, ${unmatched} to AI`);
      updateProcessingStep(3, 'active');
      setOverallProgress(20);
      setPipelineStats(prev => ({ ...prev, ruleMatched: matched }));
      addLogEntry('info', `Rules matched ${matched}/${event.total || 0} transactions (${event.rules_loaded || 0} rules loaded)`, elapsed);
      if (event.categories) {
        const cats = Object.entries(event.categories as Record<string, number>)
          .sort((a, b) => b[1] - a[1])
          .slice(0, 5)
          .map(([c, n]) => `${c}: ${n}`).join(', ');
        if (cats) addLogEntry('info', `Rule categories: ${cats}`, elapsed);
      }
      return;
    }

    if (event.type === 'categorization_start') {
      const total = event.total_batches || 0;
      const mode = event.parallel ? `parallel (${event.max_workers} workers)` : 'sequential';
      const aiTxTotal = event.total_transactions || 0;
      const label = aiTxTotal > 0
        ? `AI categorization 0/${aiTxTotal} tx`
        : 'AI categorization';
      aiCategorizedCurrentPassRef.current = 0;
      aiCategorizedTotalRef.current = 0;
      aiTotalTransactionsRef.current = aiTxTotal;
      aiLastProgressAtRef.current = Date.now();
      setBatchTelemetry({
        totalBatches: total,
        completedBatches: 0,
        failedBatches: 0,
        activeBatches: 0,
        workers: event.max_workers || 1,
        parallel: Boolean(event.parallel),
        totalTransactions: aiTxTotal,
        startedAt: Date.now(),
        avgBatchDurationMs: 0,
        etaMs: null,
      });
      updateProcessingStep(3, 'active', label, `${aiTxTotal} transactions, ${mode}`);
      setProcessingProgress(`AI is categorizing ${aiTxTotal} transactions...`);
      addLogEntry('info', `Starting AI categorization: ${aiTxTotal} transactions in ${total} batch(es), ${mode}`, elapsed);
      return;
    }

    if (event.type === 'categorization_batch_started') {
      setBatchTelemetry((prev) => ({
        ...prev,
        totalBatches: event.total_batches || prev.totalBatches,
        activeBatches: prev.activeBatches + 1,
      }));
      addLogEntry('info', `Batch ${event.batch_index}/${event.total_batches} started (${event.batch_size || '?'} transactions)`, elapsed);
      return;
    }

    if (event.type === 'categorization_progress') {
      const total = event.total_batches || 0;
      const completed = event.completed_batches || 0;
      const pct = total > 0 ? Math.round((completed / total) * 100) : 0;
      aiCategorizedCurrentPassRef.current += event.categorized || 0;
      aiCategorizedTotalRef.current = Math.max(aiCategorizedTotalRef.current, aiCategorizedCurrentPassRef.current);
      aiLastProgressAtRef.current = Date.now();

      const aiTxTotal = aiTotalTransactionsRef.current || batchTelemetry.totalTransactions || aiCategorizedTotalRef.current;
      const txLabel = aiTxTotal > 0
        ? `${aiCategorizedTotalRef.current}/${aiTxTotal} tx`
        : `${aiCategorizedTotalRef.current} tx`;
      const label = `AI categorization ${txLabel} (${completed}/${total} batches)`;
      updateProcessingStep(3, 'active', label);
      setOverallProgress(20 + Math.round(pct * 0.6));
      setProcessingProgress(`AI categorized ${txLabel}...`);

      if (event.categories) {
        setPipelineStats(prev => {
          const merged = { ...prev.categoryDistribution };
          for (const [cat, count] of Object.entries(event.categories as Record<string, number>)) {
            merged[cat] = (merged[cat] || 0) + count;
          }
          return { ...prev, aiCategorized: aiCategorizedTotalRef.current, categoryDistribution: merged };
        });
      } else {
        setPipelineStats(prev => ({ ...prev, aiCategorized: aiCategorizedTotalRef.current }));
      }

      setBatchTelemetry((prev) => {
        const failedBatches = prev.failedBatches + (event.error ? 1 : 0);
        const startedAt = prev.startedAt || Date.now();
        const elapsedSinceAiStart = Math.max(0, Date.now() - startedAt);
        const durationMs = typeof event.duration_ms === 'number' ? event.duration_ms : null;
        const avgBatchDurationMs = completed > 0
          ? (durationMs !== null
            ? ((prev.avgBatchDurationMs * Math.max(0, completed - 1)) + durationMs) / completed
            : elapsedSinceAiStart / completed)
          : prev.avgBatchDurationMs;
        const remaining = Math.max(0, total - completed);
        const concurrency = prev.parallel ? Math.max(1, prev.workers) : 1;
        const etaMs = remaining > 0 && avgBatchDurationMs > 0
          ? Math.round((remaining / concurrency) * avgBatchDurationMs)
          : 0;
        return {
          ...prev,
          totalBatches: total || prev.totalBatches,
          completedBatches: completed,
          failedBatches,
          activeBatches: Math.max(0, prev.activeBatches - 1),
          avgBatchDurationMs,
          etaMs,
        };
      });

      if (event.error) {
        setPipelineStats(prev => ({ ...prev, errors: prev.errors + 1 }));
        addLogEntry('error', `Batch ${event.batch_index} failed: ${event.error}`, elapsed);
      } else {
        const catInfo = event.categories
          ? ` — ${Object.entries(event.categories as Record<string, number>).map(([c, n]) => `${c}: ${n}`).join(', ')}`
          : '';
        addLogEntry('info', `Batch ${event.batch_index}/${total}: ${event.categorized || 0} categorized (${event.batch_size || '?'} txns)${catInfo}`, elapsed);
      }
      return;
    }

    if (event.type === 'categorization_complete') {
      const total = event.total_batches || 0;
      const aiTxTotal = aiTotalTransactionsRef.current || event.categorized || 0;
      const label = `AI categorization ${event.categorized || 0}/${aiTxTotal} tx (${total}/${total} batches)`;
      aiCategorizedCurrentPassRef.current = event.categorized || 0;
      aiCategorizedTotalRef.current = Math.max(aiCategorizedTotalRef.current, aiCategorizedCurrentPassRef.current);
      aiLastProgressAtRef.current = Date.now();
      updateProcessingStep(3, 'done', label, `${event.categorized || 0} categorized`);
      updateProcessingStep(4, 'active');
      setProcessingProgress('Reviewing categorizations...');
      setOverallProgress(70);
      if (event.categories) {
        setPipelineStats(prev => ({
          ...prev,
          aiCategorized: aiCategorizedTotalRef.current,
          categoryDistribution: { ...prev.categoryDistribution, ...event.categories },
        }));
      } else {
        setPipelineStats(prev => ({ ...prev, aiCategorized: aiCategorizedTotalRef.current }));
      }
      setBatchTelemetry((prev) => ({
        ...prev,
        completedBatches: total,
        totalBatches: total || prev.totalBatches,
        activeBatches: 0,
        etaMs: 0,
      }));
      const otherInfo = event.other_count ? ` (${event.other_count} marked "Other")` : '';
      addLogEntry('success', `AI categorization complete: ${event.categorized || 0} transactions across ${total} batches${otherInfo}`, elapsed);
      return;
    }

    if (event.type === 'categorization_warning') {
      const message = event.message || 'Categorization warning';
      setProcessingProgress(message);
      setPipelineStats(prev => ({ ...prev, warnings: prev.warnings + 1 }));
      addLogEntry('warning', message, elapsed);
      return;
    }

    if (event.type === 'review_start') {
      const totalTx = event.total_transactions || 0;
      const totalBatches = event.total_batches || 0;
      const mode = event.parallel ? `parallel (${event.max_workers} workers)` : 'sequential';
      updateProcessingStep(4, 'active', `Reviewing ${totalTx} transactions...`, `${totalBatches} batches, ${mode}`);
      setProcessingProgress(`Review agent checking ${totalTx} transactions...`);
      setOverallProgress(72);
      addLogEntry('info', `Starting review: ${totalTx} transactions in ${totalBatches} batch(es), ${mode}`, elapsed);
      return;
    }

    if (event.type === 'review_batch_started') {
      addLogEntry('info', `Review batch ${event.batch_index}/${event.total_batches} started (${event.batch_size || '?'} transactions)`, elapsed);
      return;
    }

    if (event.type === 'review_progress') {
      const total = event.total_batches || 0;
      const completed = event.completed_batches || 0;
      const pct = total > 0 ? Math.round((completed / total) * 100) : 0;
      const conflicts = event.conflicts || 0;
      const label = `Reviewing (${completed}/${total} batches, ${conflicts} conflict${conflicts !== 1 ? 's' : ''})`;
      updateProcessingStep(4, 'active', label);
      setOverallProgress(72 + Math.round(pct * 0.12));
      setProcessingProgress(`Review: ${completed}/${total} batches...`);
      const conflictInfo = conflicts > 0 ? ` — ${conflicts} conflict(s)` : '';
      addLogEntry('info', `Review batch ${event.batch_index}/${total}: ${event.reviewed || 0} reviewed${conflictInfo}`, elapsed);
      return;
    }

    if (event.type === 'review_complete') {
      const conflicts = event.conflicts || 0;
      const confirmed = event.confirmed || 0;
      const detail = conflicts > 0
        ? `${confirmed} confirmed, ${conflicts} conflict${conflicts !== 1 ? 's' : ''}`
        : `${confirmed} confirmed`;
      updateProcessingStep(4, 'done', undefined, detail);
      updateProcessingStep(5, 'active');
      setProcessingProgress('Saving transactions...');
      setOverallProgress(85);
      addLogEntry('success', `Review complete: ${event.reviewed || 0} reviewed — ${detail}`, elapsed);
      return;
    }

    if (event.type === 'review_skipped') {
      updateProcessingStep(4, 'done', undefined, 'Skipped (Ollama unavailable)');
      updateProcessingStep(5, 'active');
      setProcessingProgress('Saving transactions...');
      setOverallProgress(85);
      addLogEntry('warning', `Review skipped: ${event.reason || 'Ollama not available'}`, elapsed);
      return;
    }
  };

  const loadUserSettings = async () => {
    try {
      const [currencyResult, banksData, categoriesData, profilesData] = await Promise.all([
        apiClient.getCurrency(),
        apiClient.getBanks(),
        apiClient.getCategories(),
        apiClient.getProfiles().catch(() => ({ profiles: [] })),
      ]);
      setUserCurrency(currencyResult);
      setBanks(banksData.banks || []);
      setAvailableCategories(categoriesData.categories || []);
      setProfiles(profilesData.profiles || []);
    } catch (err) {
      console.error('Failed to load user settings:', err);
    }
  };

  const loadBankParsingPreferences = async (selectedBank: string) => {
    if (!selectedBank || !uploadResult) return;
    setIsLoadingBankPrefs(true);
    try {
      const prefsResponse = await apiClient.getPreferences('parsing', selectedBank);
      const preferences = (prefsResponse as any)?.preferences || [];
      const latestSchema = preferences[0]?.instructions ?? preferences[0]?.rule ?? null;

      setUploadResult((prev: any) => prev ? ({
        ...prev,
        parsing_preferences_exist: Boolean(latestSchema),
        saved_mappings: latestSchema,
      }) : prev);
    } catch (err) {
      console.error('Failed to load parsing preferences:', err);
      setUploadResult((prev: any) => prev ? ({
        ...prev,
        parsing_preferences_exist: false,
        saved_mappings: null,
      }) : prev);
    } finally {
      setIsLoadingBankPrefs(false);
    }
  };

  useEffect(() => {
    if (!uploadResult) return;

    const jobId = uploadResult?.job_id || '';
    const key = bankName ? `${bankName}:${jobId}` : '';

    if (!bankName) {
      if (lastBankPrefsKey.current) {
        lastBankPrefsKey.current = '';
        setUploadResult((prev: any) => prev ? ({
          ...prev,
          parsing_preferences_exist: false,
          saved_mappings: null,
        }) : prev);
      }
      return;
    }

    if (lastBankPrefsKey.current === key) return;
    if (uploadResult?.saved_mappings && !lastBankPrefsKey.current) {
      lastBankPrefsKey.current = key;
      return;
    }

    lastBankPrefsKey.current = key;
    setUploadResult((prev: any) => prev ? ({
      ...prev,
      parsing_preferences_exist: false,
      saved_mappings: null,
    }) : prev);
    void loadBankParsingPreferences(bankName);
  }, [bankName, uploadResult?.job_id]);

  useEffect(() => {
    setAmountColumnInversions((prev) => {
      const next: Record<number, boolean> = {};
      Object.entries(prev).forEach(([columnIdx, isInverted]) => {
        const idx = Number(columnIdx);
        if (columnMappings[idx] === 'amount' && isInverted) {
          next[idx] = true;
        }
      });
      return next;
    });
  }, [columnMappings]);

  useEffect(() => {
    setExcludedTransactionRows((prev) => {
      const maxRows = uploadResult?.total_rows || Number.MAX_SAFE_INTEGER;
      const filtered = prev.filter((row) => row >= firstTransactionRow && row <= maxRows);
      if (filtered.length === prev.length) {
        return prev;
      }
      return filtered;
    });
  }, [firstTransactionRow, uploadResult?.total_rows]);

  const handleFileSelect = async (selectedFile: File) => {
    if (!selectedFile) return;

    // Resolve bank name: if user typed a new bank name, register it first
    let resolvedBank = bankName;
    if (showNewBankInput && newBankName.trim()) {
      try {
        await apiClient.addBank(newBankName.trim());
        resolvedBank = newBankName.trim();
        setBanks(prev => [...prev, resolvedBank]);
        setBankName(resolvedBank);
        setShowNewBankInput(false);
        setNewBankName('');
      } catch (err) {
        setError(getErrorMessage(err, 'Failed to add bank'));
        return;
      }
    }

    if (!resolvedBank) {
      setError('Please select a bank first');
      return;
    }

    setFile(selectedFile);
    setError(null);
    setExcludedTransactionRows([]);
    setIsUploading(true);
    setUploadProgress('Uploading your statement...');

    try {
      setUploadProgress(
        'Checking saved rules...'
      );

      const result = await apiClient.uploadStatement(selectedFile, undefined, resolvedBank);
      setUploadProgress('');
      setUploadResult(result);
      setIsUploading(false);

      if (result.currency_detected) {
        setCurrency(result.currency_detected);
      }

      if (result.currency_required && !userCurrency) {
        setStep('currency_selection');
        return;
      }
    } catch (err) {
      console.error('Upload error:', err);
      setIsUploading(false);
      setUploadProgress('');
      setError(getErrorMessage(err, 'Failed to upload file'));
      setStep('file_upload');
    }
  };

  /** Validate bank selection or register a new bank. Returns the resolved name, or null on error. */
  const validateAndAddBank = async (): Promise<string | null> => {
    if (showNewBankInput) {
      if (!newBankName.trim()) {
        setError('Please enter a bank name');
        return null;
      }
      const name = newBankName.trim();
      try {
        await apiClient.addBank(name);
        if (!banks.includes(name)) setBanks([...banks, name]);
        setBankName(name);
        setShowNewBankInput(false);
      } catch (err) {
        setError(getErrorMessage(err, 'Failed to add bank'));
        return null;
      }
      return name;
    }
    if (!bankName) {
      setError('Please select a bank');
      return null;
    }
    return bankName;
  };

  const handleMainScreenContinue = async () => {
    if (!file || !uploadResult) {
      setError('Please upload a file first');
      return;
    }

    const isNewBank = showNewBankInput;
    const finalBankName = await validateAndAddBank();
    if (!finalBankName) return;

    // Move to next step based on whether parsing preferences exist
    // If bank has saved mappings, always show mapping step (user can review/edit)
    // Only auto-process if preferences exist but no saved_mappings (legacy behavior)
    if (!isNewBank && uploadResult?.parsing_preferences_exist && !uploadResult?.saved_mappings) {
      // Existing bank with preferences - go directly to processing
      await handleProcess();
    } else {
      // Need header mapping (new bank or bank with saved mappings to review/edit)
      // Initialize first_transaction_row from suggested_mappings or analysis
      if (uploadResult?.suggested_mappings?.first_transaction_row) {
        setFirstTransactionRow(uploadResult.suggested_mappings.first_transaction_row);
      } else if (uploadResult?.analysis?.skip_rows !== undefined) {
        setFirstTransactionRow((uploadResult.analysis.skip_rows || 0) + 1);
      }
      // Auto-load preferences if they exist, but never for new banks
      if (!isNewBank && uploadResult?.saved_mappings) {
        const saved = uploadResult.saved_mappings;
        const mappings: { [key: number]: string } = {};
        let hasInvalidMappings = false;

        // Helper to check if a value looks like data instead of a column reference
        const looksLikeData = (value: string): boolean => {
          if (!value || typeof value !== 'string') return false;
          
          // Numeric index check - must be ONLY digits and small
          const num = parseInt(value);
          if (!isNaN(num) && num >= 0 && num < 100 && value === num.toString()) {
            return false; // Valid index
          }
          
          // Everything else is suspicious (dates, amounts, long strings, etc.)
          return true;
        };

        const assignColumnRef = (fieldType: string, columnRef: string) => {
          // Check if it looks like data
          if (looksLikeData(columnRef)) {
            hasInvalidMappings = true;
            return;
          }
          // Try to parse as numeric index first (new format)
          const idx = parseInt(columnRef);
          if (!isNaN(idx) && idx >= 0) {
            mappings[idx] = fieldType;
            return;
          }
          // Fallback: try to find by header name (old format)
          const headerIdx = uploadResult.detected_headers?.indexOf(columnRef);
          if (headerIdx !== undefined && headerIdx >= 0) {
            mappings[headerIdx] = fieldType;
            return;
          }
          hasInvalidMappings = true;
        };

        // Convert saved mappings to column index -> field type
        Object.keys(saved.column_mappings || {}).forEach((fieldType) => {
          const columnRef = saved.column_mappings[fieldType];
          if (!columnRef) return;

          if (Array.isArray(columnRef)) {
            columnRef.forEach((col: string) => assignColumnRef(fieldType, col));
            return;
          }
          if (typeof columnRef === 'string') {
            assignColumnRef(fieldType, columnRef);
          }
        });

        if (hasInvalidMappings) {
          setError('Saved column mappings appear to be corrupted (contain data values instead of column indices). Please re-map your columns.');
          setColumnMappings({});
          setAmountColumnInversions({});
          setInvertAmountSign(false);
          setIsAutoDetected(false);
          setDetectionConfidence({});
        } else {
          setColumnMappings(mappings);
          setIsAutoDetected(false);
          setDetectionConfidence({});
          const savedInversions = saved.amount_column_inversions || {};
          const normalizedInversions: Record<number, boolean> = {};
          if (savedInversions && typeof savedInversions === 'object') {
            Object.entries(savedInversions).forEach(([columnRef, isInverted]) => {
              const idx = parseInt(columnRef, 10);
              if (!isNaN(idx) && Boolean(isInverted)) {
                normalizedInversions[idx] = true;
              }
            });
          }
          setAmountColumnInversions(normalizedInversions);
          setInvertAmountSign(Boolean(saved.invert_amount_sign));
        }
        setFirstTransactionRow(saved.first_transaction_row ?? 1);
      } else {
        // New bank or no saved mappings -- try auto-detection from suggested_mappings
        const suggested = uploadResult?.suggested_mappings;
        if (suggested?.column_mappings && Object.keys(suggested.column_mappings).length > 0) {
          const autoMappings: { [key: number]: string } = {};
          Object.entries(suggested.column_mappings as Record<string, string>).forEach(([colRef, fieldType]) => {
            const idx = parseInt(colRef, 10);
            if (!isNaN(idx) && idx >= 0 && fieldType) {
              autoMappings[idx] = fieldType;
            }
          });
          setColumnMappings(autoMappings);
          setIsAutoDetected(true);
          setDetectionConfidence(suggested.confidence || {});
          if (suggested.first_transaction_row) {
            setFirstTransactionRow(suggested.first_transaction_row);
          }
          if (suggested.currency) {
            setCurrency(suggested.currency);
          }
        } else {
          setColumnMappings({});
          setIsAutoDetected(false);
          setDetectionConfidence({});
        }
        setAmountColumnInversions({});
        setInvertAmountSign(false);
      }
      setExcludedTransactionRows([]);
      setStep('header_mapping');
    }
  };

  const handleCurrencySave = async () => {
    if (!currency) {
      setError('Please select a currency');
      return;
    }

    try {
      await apiClient.saveCurrency(currency);
      setUserCurrency(currency);

      // Return to main screen after saving currency
      setStep('file_upload');
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to save currency'));
    }
  };


  // Validation helper: Check if a value looks like data instead of a column index
  const validateColumnReference = (columnRef: string | string[]): boolean => {
    // Handle array (for description columns)
    if (Array.isArray(columnRef)) {
      return columnRef.every(ref => validateColumnReference(ref));
    }

    if (!columnRef || typeof columnRef !== 'string') return false;

    // Must be numeric string like "0", "1", "2"
    const idx = parseInt(columnRef);
    if (isNaN(idx) || idx < 0 || idx > 100) return false;

    // Must be EXACTLY the string representation of the number (no extra chars)
    if (columnRef !== idx.toString()) return false;

    // Reject if it looks like data
    if (/^\d{1,2}[-/]\d{1,2}[-/]\d{2,4}$/.test(columnRef)) return false; // Date pattern
    if (/^\d+[.,]\d+$/.test(columnRef)) return false; // Number with decimal
    if (columnRef.length > 3) return false; // Column index should be short

    return true;
  };

  const getSanitizedExcludedRows = (): number[] => (
    Array.from(new Set(excludedTransactionRows.filter((row) => row >= firstTransactionRow)))
      .sort((a, b) => a - b)
  );

  // Helper function to convert columnMappings to API format
  const convertMappingsToAPI = (options?: { includeExcludedTransactionRows?: boolean }) => {
    const result: any = {
      column_mappings: {},
      amount_column_inversions: {},
      invert_amount_sign: invertAmountSign,
      has_headers: false, // Always false - we use first_transaction_row instead
      first_transaction_row: firstTransactionRow,
      date_format: uploadResult?.suggested_mappings?.date_format || uploadResult?.analysis?.date_format || 'DD/MM/YYYY',
      currency: currency || uploadResult?.currency_detected || 'USD',
      number_format: uploadResult?.suggested_mappings?.number_format || 'auto',
      delimiter: uploadResult?.suggested_mappings?.delimiter || ',',
    };

    // Convert column index -> field type to field type -> column reference
    // Use column index (as string) instead of header name for reliability
    // The backend will resolve this to the actual column name
    const descriptionCols: string[] = [];
    const amountCols: string[] = [];
    Object.keys(columnMappings).forEach((colIdxStr) => {
      const colIdx = parseInt(colIdxStr);
      const fieldType = columnMappings[colIdx];

      if (!fieldType || fieldType === 'do_not_use') return;

      // Use column index as the reference (more reliable than header names)
      // Format: "0", "1", "2" etc. which works whether has_headers is true or false
      const columnRef = colIdxStr; // Use index as string

      if (fieldType === 'description') {
        descriptionCols.push(columnRef);
      } else if (fieldType === 'amount') {
        amountCols.push(columnRef);
      } else {
        result.column_mappings[fieldType] = columnRef;
      }
    });

    if (descriptionCols.length > 0) {
      result.column_mappings.description = descriptionCols;
    }
    if (amountCols.length > 0) {
      result.column_mappings.amount = amountCols;
    }

    amountCols.forEach((columnRef) => {
      const idx = parseInt(columnRef, 10);
      if (!isNaN(idx) && amountColumnInversions[idx]) {
        result.amount_column_inversions[columnRef] = true;
      }
    });
    if (Object.keys(result.amount_column_inversions).length === 0) {
      delete result.amount_column_inversions;
    }
    if (!result.invert_amount_sign) {
      delete result.invert_amount_sign;
    }
    if (options?.includeExcludedTransactionRows) {
      const excludedRows = getSanitizedExcludedRows();
      if (excludedRows.length > 0) {
        result.excluded_transaction_rows = excludedRows;
      }
    }

    // Validate all column references before returning
    const invalidRefs: string[] = [];
    Object.entries(result.column_mappings).forEach(([fieldType, columnRef]) => {
      if (!validateColumnReference(columnRef as string | string[])) {
        invalidRefs.push(`${fieldType}: ${JSON.stringify(columnRef)}`);
      }
    });

    if (invalidRefs.length > 0) {
      console.error('[VALIDATION ERROR] Invalid column references detected:', invalidRefs);
      throw new Error(
        `Invalid column mappings detected. The following fields contain data values instead of column indices: ${invalidRefs.join(', ')}. ` +
        'Column references must be numeric indices like "0", "1", "2".'
      );
    }

    if (config.debug) {
      console.log('[DEBUG] Column mappings validated successfully:', result.column_mappings);
    }
    return result;
  };

  useEffect(() => {
    if (step !== 'header_mapping' || !file) {
      setMappingNetFlowPreview(null);
      setMappingNetFlowError(null);
      setIsCalculatingMappingNetFlow(false);
      return;
    }

    const dateMapped = Object.values(columnMappings).includes('date');
    const descriptionMapped = Object.values(columnMappings).some(v => v === 'description');
    const amountLikeMapped = Object.values(columnMappings).some(
      v => v === 'amount' || v === 'inflow' || v === 'outflow'
    );
    if (!dateMapped || !descriptionMapped || !amountLikeMapped || !firstTransactionRow) {
      setMappingNetFlowPreview(null);
      setMappingNetFlowError(null);
      setIsCalculatingMappingNetFlow(false);
      return;
    }

    const requestId = ++netFlowPreviewRequestRef.current;
    const timeoutId = window.setTimeout(async () => {
      setIsCalculatingMappingNetFlow(true);
      setMappingNetFlowError(null);
      try {
        const mappingData = convertMappingsToAPI({ includeExcludedTransactionRows: true });
        const preview = await apiClient.previewStatementNetFlow(file, bankName || undefined, mappingData);
        if (netFlowPreviewRequestRef.current !== requestId) return;
        setMappingNetFlowPreview(preview);
      } catch (err) {
        if (netFlowPreviewRequestRef.current !== requestId) return;
        setMappingNetFlowPreview(null);
        setMappingNetFlowError(getErrorMessage(err, 'Failed to calculate net flow preview'));
      } finally {
        if (netFlowPreviewRequestRef.current === requestId) {
          setIsCalculatingMappingNetFlow(false);
        }
      }
    }, 300);

    return () => window.clearTimeout(timeoutId);
  }, [
    step,
    file,
    bankName,
    columnMappings,
    amountColumnInversions,
    invertAmountSign,
    firstTransactionRow,
    excludedTransactionRows,
    currency,
    userCurrency,
  ]);

  const handleHeaderMappingSave = async () => {
    // Validate required fields
    const dateMapped = Object.values(columnMappings).includes('date');
    const amountMapped = Object.values(columnMappings).includes('amount')
      || Object.values(columnMappings).includes('inflow')
      || Object.values(columnMappings).includes('outflow');
    const descriptionMapped = Object.values(columnMappings).filter(v => v === 'description').length > 0;

    if (config.debug) {
      console.log('[DEBUG] handleHeaderMappingSave - columnMappings state:', columnMappings);
      console.log('[DEBUG] Required fields check:', { dateMapped, amountMapped, descriptionMapped });
    }

    if (!dateMapped || !amountMapped || !descriptionMapped) {
      setError('Please map all required columns: Date, at least one Amount/Inflow/Outflow, and at least one Description column');
      return;
    }

    if (!firstTransactionRow || firstTransactionRow < 1) {
      setError('Please specify the row number of the first transaction');
      return;
    }

    if (!bankName) {
      setError('Bank name is required');
      return;
    }

    try {
      const mappingData = convertMappingsToAPI();
      if (config.debug) {
        console.log('[DEBUG] Converted mapping data to send to API:', mappingData);
      }
      await apiClient.saveHeaderMapping(bankName, mappingData);
      // Go directly to processing after saving mapping
      await handleProcess();
    } catch (err) {
      console.error('[ERROR] Failed to save header mapping:', err);
      setError(getErrorMessage(err, 'Failed to save header mapping'));
    }
  };

  const handleProcess = async (force: boolean = false) => {
    if (!file || !bankName) {
      setError('File and bank name are required');
      return;
    }

    prevStepRef.current = step;
    setStep('processing');
    setError(null);
    const clientFallback = new Date().toISOString();
    serverStartedAtRef.current = null;
    setProcessingStartedAt(clientFallback);
    initializeProcessingProgress();

    try {
      const mapping = uploadResult?.parsing_preferences_exist ? undefined : convertMappingsToAPI();
      const excludedRows = getSanitizedExcludedRows();

      const effectiveProfile = showNewProfileInput ? newProfileName.trim() : selectedProfile;
      const result = await apiClient.processStatementStream(
        file,
        bankName,
        mapping,
        excludedRows,
        handleProcessingEvent,
        effectiveProfile || undefined,
        force
      );

      if (result.status === 'duplicate_detected') {
        setDuplicateWarning((result as any).duplicate_warning);
        setStep((prevStepRef.current as any) || 'file_upload');
        setProcessingSteps([]);
        return;
      }

      if (result.status === 'success') {
        setDashboardOverride((result as any).dashboard || null);
        setProcessingSteps((prev) => prev.map((step) => ({ ...step, status: 'done' })));
        setProcessingProgress('Complete!');

        try {
          const since = serverStartedAtRef.current || clientFallback;
          const queue = await apiClient.getTransactionReviewQueue(bankName, since);
          if (queue.transactions.length > 0) {
            setReviewData(queue);
            setPendingCategoryEdits({});
            setStep('review');
          } else {
            setStep('success');
          }
        } catch {
          setStep('success');
        }
      } else {
        throw new Error((result as any).error || 'Processing failed');
      }
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to process statement'));
      setProcessingProgress('Processing failed.');
      setProcessingSteps([]);
      setBatchTelemetry(DEFAULT_BATCH_TELEMETRY);
      aiTotalTransactionsRef.current = 0;
      aiLastProgressAtRef.current = null;
      // Go back to appropriate step based on whether mapping was needed
      if (uploadResult?.parsing_preferences_exist && !uploadResult?.saved_mappings) {
        setStep('file_upload');
      } else {
        setStep('header_mapping');
      }
    }
  };

  const reset = () => {
    setStep('file_upload');
    setFile(null);
    setUploadResult(null);
    setDuplicateWarning(null);
    setCurrency('');
    setBankName('');
    setNewBankName('');
    setShowNewBankInput(false);
    setColumnMappings({});
    setAmountColumnInversions({});
    setInvertAmountSign(false);
    setFirstTransactionRow(1);
    setExcludedTransactionRows([]);
    setMappingNetFlowPreview(null);
    setIsCalculatingMappingNetFlow(false);
    setMappingNetFlowError(null);
    setError(null);
    setProcessingProgress('');
    setProcessingSteps([]);
    setBatchTelemetry(DEFAULT_BATCH_TELEMETRY);
    aiTotalTransactionsRef.current = 0;
    aiLastProgressAtRef.current = null;
    serverStartedAtRef.current = null;
    setDashboardOverride(null);
    setProcessingStartedAt(null);
    setReviewData(null);
    setPendingCategoryEdits({});
    setPendingRuleCreations({});
    setIsSavingReview(false);
  };

  const saveReviewEditsAndContinue = async () => {
    setIsSavingReview(true);
    try {
      const edits = Object.entries(pendingCategoryEdits);
      if (edits.length > 0) {
        const conflictTxIds = new Set(
          (reviewData?.transactions || [])
            .filter((t) => t.review_priority === 'ai_conflict' && hasDistinctReviewerCategory(t.category, t.review_category))
            .map((t) => t.id)
        );
        await Promise.all(
          edits.map(([id, category]) => {
            const ruleEntry = pendingRuleCreations[id];
            const rulePattern = ruleEntry?.pattern.trim();
            if (ruleEntry?.enabled && rulePattern) {
              return conflictTxIds.has(id)
                ? apiClient.resolveConflict({
                    id,
                    chosen_category: category,
                    create_rule: true,
                    rule_pattern: rulePattern,
                  })
                : apiClient.categorizeManualReview({
                    id,
                    category,
                    create_rule: true,
                    rule_pattern: rulePattern,
                    pattern_type: 'regex',
                  });
            }
            return conflictTxIds.has(id)
              ? apiClient.resolveConflict({ id, chosen_category: category })
              : apiClient.updateTransaction(id, { category } as any);
          })
        );
      }
      setStep('success');
    } catch (err) {
      console.error('Failed to save review edits:', err);
      setError(getErrorMessage(err, 'Failed to save category edits. Please try again.'));
    } finally {
      setIsSavingReview(false);
    }
  };

  const hasSavedMappings = Boolean(uploadResult?.saved_mappings);
  const hasParsingPreferences = Boolean(uploadResult?.parsing_preferences_exist);
  const excludedTransactionRowSet = new Set(excludedTransactionRows);
  const suspiciousRowsByNumber = new Map<number, string[]>();
  (mappingNetFlowPreview?.suspicious_transactions || []).forEach((tx) => {
    const labels = tx.reasons.map((reason) => reason.label);
    if (labels.length > 0) {
      suspiciousRowsByNumber.set(tx.source_row_number, labels);
    }
  });
  const totalPreviewColumns = uploadResult?.total_columns || uploadResult?.preview_data?.[0]?.length || 0;

  // Review step view
  if (step === 'review' && reviewData) {
    const manualCount = reviewData.manual_review_count;
    const conflictCount = reviewData.transactions.filter(
      (t) => t.review_priority === 'ai_conflict' && hasDistinctReviewerCategory(t.category, t.review_category)
    ).length;
    const highAmountCount = reviewData.transactions.filter(
      (t) => t.review_priority === 'high_amount'
    ).length;
    const recurringCount = reviewData.transactions.filter(
      (t) => t.review_priority === 'recurring'
    ).length;
    const fmtAmount = (n: number, cur: string) => {
      const abs = Math.abs(n);
      const formatted = abs.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
      return `${n < 0 ? '-' : '+'}${cur} ${formatted}`;
    };
    const priorityIcon: Record<string, string> = {
      manual_review: '\u26A0\uFE0F',
      ai_conflict: '\u2694\uFE0F',
      high_amount: '\uD83D\uDCB0',
      recurring: '\uD83D\uDD04',
    };
    const priorityLabel: Record<string, string> = {
      manual_review: 'Needs review',
      ai_conflict: 'AI conflict',
      high_amount: 'High amount',
      recurring: 'Recurring',
    };
    const sourceLabel: Record<string, string> = {
      rule: 'Rule',
      ai: 'AI',
      manual: 'Manual',
    };

    return (
      <div style={{
        minHeight: '100vh',
        background: 'linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%)',
        padding: '24px',
      }}>
        <div style={{
          maxWidth: '1200px',
          margin: '0 auto',
          backgroundColor: 'white',
          borderRadius: '16px',
          boxShadow: '0 20px 60px rgba(0,0,0,0.1)',
          overflow: 'hidden',
        }}>
          {/* Header */}
          <div style={{
            padding: '24px 32px',
            borderBottom: '1px solid #e2e8f0',
            background: 'linear-gradient(135deg, #1e293b 0%, #0f172a 100%)',
            color: 'white',
          }}>
            <h2 style={{ margin: '0 0 8px', fontSize: '22px', fontWeight: 700 }}>
              Review AI Categorization
            </h2>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '16px', fontSize: '14px', color: '#cbd5e1' }}>
              {manualCount > 0 && (
                <span>{'\u26A0\uFE0F'} {manualCount} flagged for manual review</span>
              )}
              {conflictCount > 0 && (
                <span>{'\u2694\uFE0F'} {conflictCount} AI conflict{conflictCount !== 1 ? 's' : ''}</span>
              )}
              {highAmountCount > 0 && (
                <span>{'\uD83D\uDCB0'} {highAmountCount} high-value item{highAmountCount !== 1 ? 's' : ''}</span>
              )}
              {recurringCount > 0 && (
                <span>{'\uD83D\uDD04'} {recurringCount} recurring</span>
              )}
            </div>
            <div style={{ marginTop: '8px', fontSize: '13px', color: '#94a3b8' }}>
              Statement total: {reviewData.total_absolute_value.toLocaleString(undefined, { minimumFractionDigits: 2 })}
              {' '}&middot;{' '}
              Materiality threshold: {reviewData.materiality_threshold.toLocaleString(undefined, { minimumFractionDigits: 2 })} (1.5%)
            </div>
          </div>

          {/* Action bar */}
          <div style={{
            padding: '16px 32px',
            borderBottom: '1px solid #e2e8f0',
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            flexWrap: 'wrap',
            backgroundColor: '#f8fafc',
          }}>
            <button
              onClick={saveReviewEditsAndContinue}
              disabled={isSavingReview}
              style={{
                padding: '10px 20px',
                backgroundColor: '#dc2626',
                color: 'white',
                border: 'none',
                borderRadius: '8px',
                fontSize: '14px',
                fontWeight: 600,
                cursor: isSavingReview ? 'not-allowed' : 'pointer',
                opacity: isSavingReview ? 0.7 : 1,
              }}
            >
              {isSavingReview ? 'Saving...' : `Approve & Continue${Object.keys(pendingCategoryEdits).length > 0 ? ` (${Object.keys(pendingCategoryEdits).length} edit${Object.keys(pendingCategoryEdits).length !== 1 ? 's' : ''})` : ''}`}
            </button>
            <button
              onClick={() => setStep('success')}
              disabled={isSavingReview}
              style={{
                padding: '10px 20px',
                backgroundColor: 'transparent',
                color: '#64748b',
                border: '1px solid #cbd5e1',
                borderRadius: '8px',
                fontSize: '13px',
                fontWeight: 500,
                cursor: isSavingReview ? 'not-allowed' : 'pointer',
              }}
            >
              Skip review
            </button>
            <span style={{ marginLeft: 'auto', fontSize: '13px', color: '#94a3b8' }}>
              {reviewData.total_count} transaction{reviewData.total_count !== 1 ? 's' : ''} to review
            </span>
          </div>

          {/* Table */}
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
              <thead>
                <tr style={{ backgroundColor: '#f1f5f9' }}>
                  <th style={{ padding: '12px 16px', textAlign: 'left', fontWeight: 600, color: '#475569', borderBottom: '2px solid #e2e8f0', whiteSpace: 'nowrap' }}>Date</th>
                  <th style={{ padding: '12px 16px', textAlign: 'left', fontWeight: 600, color: '#475569', borderBottom: '2px solid #e2e8f0', minWidth: '420px' }}>Description</th>
                  <th style={{ padding: '12px 16px', textAlign: 'right', fontWeight: 600, color: '#475569', borderBottom: '2px solid #e2e8f0', whiteSpace: 'nowrap' }}>Amount</th>
                  <th style={{ padding: '12px 12px', textAlign: 'center', fontWeight: 600, color: '#475569', borderBottom: '2px solid #e2e8f0', whiteSpace: 'nowrap' }}>Source</th>
                  <th style={{ padding: '12px 16px', textAlign: 'left', fontWeight: 600, color: '#475569', borderBottom: '2px solid #e2e8f0', minWidth: '180px' }}>Category</th>
                  <th style={{ padding: '12px 16px', textAlign: 'center', fontWeight: 600, color: '#475569', borderBottom: '2px solid #e2e8f0', whiteSpace: 'nowrap' }}>Why</th>
                </tr>
              </thead>
              <tbody>
                {reviewData.transactions.map((tx) => {
                  const isManualReview = tx.review_priority === 'manual_review';
                  const isConflict = tx.review_priority === 'ai_conflict' && hasDistinctReviewerCategory(tx.category, tx.review_category);
                  const currentCategory = pendingCategoryEdits[tx.id] ?? tx.category;
                  const isEdited = tx.id in pendingCategoryEdits;

                  const rowBg = isConflict ? '#ede9fe'
                    : isManualReview ? '#fef3c7'
                    : isEdited ? '#ecfdf5'
                    : 'white';

                  const borderColor = isConflict && !isEdited ? '#8b5cf6'
                    : isManualReview && !isEdited ? '#f59e0b'
                    : isEdited ? '#10b981'
                    : '#d1d5db';

                  return (
                    <tr
                      key={tx.id}
                      style={{
                        backgroundColor: rowBg,
                        borderBottom: '1px solid #f1f5f9',
                      }}
                    >
                      <td style={{ padding: '12px 16px', whiteSpace: 'nowrap', color: '#334155' }}>
                        {tx.date}
                      </td>
                      <td
                        style={{
                          padding: '12px 16px',
                          color: '#0f172a',
                          fontWeight: 500,
                          whiteSpace: 'normal',
                          overflowWrap: 'anywhere',
                          wordBreak: 'break-word',
                          lineHeight: 1.4,
                        }}
                      >
                        <div style={{ whiteSpace: 'normal', overflowWrap: 'anywhere', wordBreak: 'break-word' }}>
                          {tx.description}
                        </div>
                        {tx.merchant && tx.merchant !== tx.description && (
                          <div style={{ fontSize: '11px', color: '#94a3b8', fontWeight: 400, whiteSpace: 'normal', overflowWrap: 'anywhere', wordBreak: 'break-word' }}>{tx.merchant}</div>
                        )}
                        {isConflict && tx.review_reason && (
                          <div style={{ fontSize: '11px', color: '#7c3aed', fontWeight: 400, marginTop: '2px', fontStyle: 'italic', whiteSpace: 'normal', overflowWrap: 'anywhere', wordBreak: 'break-word' }}>
                            Reviewer: {tx.review_reason}
                          </div>
                        )}
                      </td>
                      <td style={{
                        padding: '12px 16px',
                        textAlign: 'right',
                        fontWeight: 600,
                        fontVariantNumeric: 'tabular-nums',
                        color: tx.amount < 0 ? '#dc2626' : '#16a34a',
                        whiteSpace: 'nowrap',
                      }}>
                        {fmtAmount(tx.amount, tx.currency)}
                      </td>
                      <td style={{ padding: '12px 12px', textAlign: 'center' }}>
                        <span
                          title={tx.category_source === 'rule' ? 'Assigned by rule' : tx.category_source === 'manual' ? 'Chosen manually' : 'Assigned by AI categorizer'}
                          style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            minWidth: '44px',
                            padding: '3px 8px',
                            borderRadius: '999px',
                            fontSize: '10px',
                            fontWeight: 700,
                            letterSpacing: '0.04em',
                            textTransform: 'uppercase',
                            color: tx.category_source === 'rule' ? '#1d4ed8' : tx.category_source === 'manual' ? '#065f46' : '#7c3aed',
                            backgroundColor: tx.category_source === 'rule' ? '#dbeafe' : tx.category_source === 'manual' ? '#d1fae5' : '#f3e8ff',
                          }}
                        >
                          {sourceLabel[tx.category_source || 'ai'] || 'AI'}
                        </span>
                      </td>
                      <td style={{ padding: '12px 16px' }}>
                        {isConflict && tx.review_category && !isEdited && (
                          <div style={{
                            display: 'flex',
                            gap: '4px',
                            marginBottom: '6px',
                            fontSize: '11px',
                          }}>
                            <button
                              onClick={() => setPendingCategoryEdits((prev) => ({ ...prev, [tx.id]: tx.category }))}
                              style={{
                                flex: 1,
                                padding: '4px 6px',
                                border: '1px solid #e2e8f0',
                                borderRadius: '4px',
                                backgroundColor: '#f8fafc',
                                cursor: 'pointer',
                                fontSize: '11px',
                                color: '#475569',
                              }}
                              title="Keep categorizer choice"
                            >
                              <div style={{ fontSize: '9px', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '1px', opacity: 0.75 }}>
                                Categorizer
                              </div>
                              {tx.category}
                            </button>
                            <button
                              onClick={() => setPendingCategoryEdits((prev) => ({ ...prev, [tx.id]: tx.review_category! }))}
                              style={{
                                flex: 1,
                                padding: '4px 6px',
                                border: '1px solid #8b5cf6',
                                borderRadius: '4px',
                                backgroundColor: '#f5f3ff',
                                cursor: 'pointer',
                                fontSize: '11px',
                                color: '#7c3aed',
                                fontWeight: 600,
                              }}
                              title="Use reviewer suggestion"
                            >
                              <div style={{ fontSize: '9px', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '1px', opacity: 0.75 }}>
                                Reviewer
                              </div>
                              {tx.review_category}
                            </button>
                          </div>
                        )}
                        <select
                          value={currentCategory === 'MANUAL_REVIEW' ? '' : currentCategory}
                          onChange={(e) => {
                            const newCat = e.target.value;
                            setPendingCategoryEdits((prev) => ({ ...prev, [tx.id]: newCat }));
                          }}
                          style={{
                            width: '100%',
                            padding: '6px 8px',
                            border: `1px solid ${borderColor}`,
                            borderRadius: '6px',
                            fontSize: '12px',
                            backgroundColor: isEdited ? '#ecfdf5' : 'white',
                            fontWeight: isEdited ? 600 : 400,
                          }}
                        >
                          {isManualReview && !isEdited && (
                            <option value="" disabled>Select category...</option>
                          )}
                          {availableCategories.map((cat) => (
                            <option key={cat} value={cat}>{cat}</option>
                          ))}
                        </select>
                        {isEdited && (
                          <div style={{ marginTop: '4px' }}>
                            <label style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '11px', color: '#64748b', cursor: 'pointer' }}>
                              <input
                                type="checkbox"
                                checked={pendingRuleCreations[tx.id]?.enabled ?? false}
                                onChange={(e) => {
                                  const enabled = e.target.checked;
                                  setPendingRuleCreations((prev) => ({
                                    ...prev,
                                    [tx.id]: {
                                      enabled,
                                      pattern: prev[tx.id]?.pattern ?? tx.description ?? '',
                                    },
                                  }));
                                }}
                              />
                              Create rule
                            </label>
                            {pendingRuleCreations[tx.id]?.enabled && (
                              <input
                                type="text"
                                value={pendingRuleCreations[tx.id]?.pattern ?? ''}
                                onChange={(e) => setPendingRuleCreations((prev) => ({
                                  ...prev,
                                  [tx.id]: { ...prev[tx.id], pattern: e.target.value },
                                }))}
                                placeholder="Pattern (regex)"
                                style={{
                                  marginTop: '3px',
                                  width: '100%',
                                  padding: '4px 6px',
                                  fontSize: '11px',
                                  border: '1px solid #cbd5e1',
                                  borderRadius: '4px',
                                  boxSizing: 'border-box',
                                }}
                              />
                            )}
                          </div>
                        )}
                      </td>
                      <td style={{ padding: '12px 16px', textAlign: 'center' }}>
                        <span
                          title={
                            isConflict && tx.review_reason
                              ? `AI conflict: ${tx.review_reason}`
                              : priorityLabel[tx.review_priority] || tx.review_priority
                          }
                          style={{ fontSize: '16px', cursor: 'default' }}
                        >
                          {priorityIcon[tx.review_priority] || ''}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    );
  }

  // Success view
  if (step === 'success') {
    return (
      <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>
        <div style={{ marginBottom: '24px', display: 'flex', alignItems: 'center', gap: '16px' }}>
          <button
            onClick={reset}
            style={{
              padding: '8px 16px',
              backgroundColor: '#dc2626',
              color: 'white',
              border: 'none',
              borderRadius: '8px',
              cursor: 'pointer',
              fontSize: '14px',
              fontWeight: 600,
            }}
          >
            ← Upload Another Statement
          </button>
          <h2 style={{ margin: 0, fontSize: '24px', fontWeight: 700, color: '#1a202c' }}>
            Your Financial Dashboard
          </h2>
        </div>
        {/* Rule Advisor nudge banner */}
        <div style={{
          marginBottom: '20px',
          padding: '16px 20px',
          background: 'linear-gradient(135deg, #eff6ff 0%, #f0f9ff 100%)',
          border: '1px solid #bfdbfe',
          borderRadius: '12px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: '16px',
          flexWrap: 'wrap',
        }}>
          <div>
            <div style={{ fontSize: '15px', fontWeight: 700, color: '#1e40af', marginBottom: '4px' }}>
              Optimize your categorization rules
            </div>
            <div style={{ fontSize: '13px', color: '#3b82f6', lineHeight: 1.5 }}>
              Run the Rule Advisor in the Review tab to detect conflicts, find uncovered transactions, and get new rule suggestions.
            </div>
          </div>
          <a
            href="/dashboard?tab=review"
            style={{
              padding: '10px 24px',
              fontSize: '14px',
              fontWeight: 600,
              background: '#2563eb',
              color: 'white',
              border: 'none',
              borderRadius: '8px',
              textDecoration: 'none',
              whiteSpace: 'nowrap',
            }}
          >
            Open Rule Advisor
          </a>
        </div>
        <DashboardWidget initialData={dashboardOverride} />
      </div>
    );
  }

  // Processing view — polished live observability
  if (step === 'processing') {
    const formatElapsed = (ms: number) => {
      const s = Math.floor(ms / 1000);
      const m = Math.floor(s / 60);
      const sec = s % 60;
      return m > 0 ? `${m}m ${sec}s` : `${sec}s`;
    };
    const formatStepDuration = (s: PipelineStep) => {
      if (!s.startedAt) return '';
      const end = s.finishedAt || Date.now();
      return formatElapsed(end - s.startedAt);
    };
    const elapsed = pipelineStartTime ? Date.now() - pipelineStartTime : 0;
    const sortedCats = Object.entries(pipelineStats.categoryDistribution)
      .sort((a, b) => b[1] - a[1]);
    const totalCategorized = sortedCats.reduce((sum, [, n]) => sum + n, 0);
    const activeStep = processingSteps.find((s) => s.status === 'active');
    const completedStepCount = processingSteps.filter((s) => s.status === 'done').length;
    const pipelineCompletionPct = processingSteps.length > 0
      ? Math.round((completedStepCount / processingSteps.length) * 100)
      : 0;
    const batchCompletionPct = batchTelemetry.totalBatches > 0
      ? Math.round((batchTelemetry.completedBatches / batchTelemetry.totalBatches) * 100)
      : 0;
    const aiRuntimeMs = batchTelemetry.startedAt ? Date.now() - batchTelemetry.startedAt : 0;
    const aiThroughput = aiRuntimeMs > 0 ? pipelineStats.aiCategorized / (aiRuntimeMs / 1000) : 0;
    const batchSuccessRate = batchTelemetry.completedBatches > 0
      ? Math.round(((batchTelemetry.completedBatches - batchTelemetry.failedBatches) / batchTelemetry.completedBatches) * 100)
      : 100;
    const aiTotalTransactions = batchTelemetry.totalTransactions || aiTotalTransactionsRef.current || 0;
    const aiConfirmedTransactions = Math.min(aiTotalTransactions || pipelineStats.aiCategorized, pipelineStats.aiCategorized);
    const avgBatchSize = batchTelemetry.totalBatches > 0
      ? aiTotalTransactions / batchTelemetry.totalBatches
      : 0;
    const inferredInFlightBatches = batchTelemetry.activeBatches > 0
      ? batchTelemetry.activeBatches
      : ((batchTelemetry.totalBatches - batchTelemetry.completedBatches) > 0
        ? (batchTelemetry.parallel ? Math.max(1, batchTelemetry.workers) : 1)
        : 0);
    const inFlightCapacity = inferredInFlightBatches * avgBatchSize;
    const sinceLastAiProgressMs = aiLastProgressAtRef.current
      ? Math.max(0, Date.now() - aiLastProgressAtRef.current)
      : 0;
    const inFlightInterpolation = batchTelemetry.avgBatchDurationMs > 0
      ? Math.min(0.92, sinceLastAiProgressMs / batchTelemetry.avgBatchDurationMs)
      : 0;
    const estimatedInFlightTransactions = Math.min(
      Math.max(0, aiTotalTransactions - aiConfirmedTransactions),
      Math.round(inFlightCapacity * inFlightInterpolation),
    );
    const aiDisplayedTransactions = Math.min(
      aiTotalTransactions || aiConfirmedTransactions,
      aiConfirmedTransactions + estimatedInFlightTransactions,
    );
    const aiConfirmedPct = aiTotalTransactions > 0
      ? Math.round((aiConfirmedTransactions / aiTotalTransactions) * 100)
      : 0;
    const aiDisplayedPct = aiTotalTransactions > 0
      ? Math.round((aiDisplayedTransactions / aiTotalTransactions) * 100)
      : aiConfirmedPct;

    const LEVEL_STYLES: Record<string, { bg: string; text: string; dot: string; label: string }> = {
      info: { bg: '#eff6ff', text: '#1d4ed8', dot: '#3b82f6', label: 'Info' },
      success: { bg: '#ecfdf3', text: '#047857', dot: '#10b981', label: 'Success' },
      warning: { bg: '#fffbeb', text: '#b45309', dot: '#f59e0b', label: 'Warning' },
      error: { bg: '#fef2f2', text: '#b91c1c', dot: '#ef4444', label: 'Error' },
    };

    return (
      <div style={{
        minHeight: '100vh',
        background: 'radial-gradient(circle at 10% 10%, #eef2ff 0%, #f8fafc 38%, #eef6ff 100%)',
        padding: '24px 24px 48px',
      }}>
        <style>{`
          @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
          @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
          @keyframes fadeInUp { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }

          .processing-shell {
            max-width: 1200px;
            margin: 0 auto;
          }
          .processing-kpis {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 12px;
            margin-bottom: 16px;
          }
          .processing-grid {
            display: grid;
            grid-template-columns: minmax(0, 360px) minmax(0, 1fr);
            gap: 16px;
            align-items: start;
          }
          .processing-col {
            display: flex;
            flex-direction: column;
            gap: 16px;
          }
          .processing-card {
            background: rgba(255, 255, 255, 0.85);
            border: 1px solid rgba(226, 232, 240, 0.9);
            border-radius: 16px;
            box-shadow: 0 12px 30px rgba(15, 23, 42, 0.06);
            backdrop-filter: blur(4px);
          }
          @media (max-width: 1024px) {
            .processing-grid {
              grid-template-columns: minmax(0, 1fr);
            }
          }
          @media (max-width: 720px) {
            .processing-kpis {
              grid-template-columns: repeat(2, minmax(0, 1fr));
            }
          }
        `}</style>
        <div className="processing-shell">
          <div
            className="processing-card"
            style={{
              padding: '20px',
              marginBottom: '16px',
              background: 'linear-gradient(135deg, rgba(15,23,42,0.96) 0%, rgba(30,41,59,0.96) 58%, rgba(17,94,89,0.92) 100%)',
              color: '#e2e8f0',
              border: '1px solid rgba(71, 85, 105, 0.6)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '16px', flexWrap: 'wrap' }}>
              <div style={{
                width: '36px',
                height: '36px',
                border: '3px solid rgba(148,163,184,0.25)',
                borderTop: '3px solid #22d3ee',
                borderRadius: '50%',
                animation: 'spin 1s linear infinite',
                flexShrink: 0,
              }} />
              <div style={{ flex: 1, minWidth: '240px' }}>
                <h2 style={{ margin: 0, fontSize: '23px', fontWeight: 700, letterSpacing: '-0.2px' }}>
                  Processing your statement
                </h2>
                <p style={{ margin: '6px 0 0', fontSize: '14px', color: '#cbd5e1' }}>
                  {processingProgress || activeStep?.label || 'Initializing pipeline'}
                </p>
              </div>
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                padding: '8px 12px',
                borderRadius: '999px',
                backgroundColor: 'rgba(148, 163, 184, 0.16)',
                border: '1px solid rgba(148,163,184,0.32)',
                fontSize: '12px',
                fontWeight: 600,
                textTransform: 'uppercase',
                letterSpacing: '0.5px',
              }}>
                Runtime {formatElapsed(elapsed)}
              </div>
            </div>
            <div style={{ marginTop: '14px', height: '8px', borderRadius: '999px', backgroundColor: 'rgba(148,163,184,0.25)', overflow: 'hidden' }}>
              <div style={{
                height: '100%',
                width: `${overallProgress}%`,
                borderRadius: '999px',
                background: 'linear-gradient(90deg, #22d3ee 0%, #38bdf8 45%, #34d399 100%)',
                transition: 'width 0.4s ease',
              }} />
            </div>
            <div style={{ marginTop: '8px', fontSize: '12px', color: '#94a3b8' }}>
              Pipeline completion {pipelineCompletionPct}% ({completedStepCount}/{processingSteps.length || 0} stages)
            </div>
          </div>

          <div className="processing-kpis">
            {[
              { label: 'Parsed', value: pipelineStats.parsed.toLocaleString(), tone: '#2563eb' },
              { label: 'Rule matched', value: pipelineStats.ruleMatched.toLocaleString(), tone: '#7c3aed' },
              { label: 'AI throughput', value: aiThroughput > 0 ? `${aiThroughput.toFixed(1)} tx/s` : 'Waiting', tone: '#0f766e' },
              {
                label: 'AI progress',
                value: aiTotalTransactions > 0 ? `${aiDisplayedPct}%` : 'Queued',
                tone: aiDisplayedPct >= 100 ? '#047857' : '#0ea5e9',
              },
            ].map((item) => (
              <div key={item.label} className="processing-card" style={{ padding: '14px 16px' }}>
                <div style={{ fontSize: '12px', fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                  {item.label}
                </div>
                <div style={{ marginTop: '6px', fontSize: '22px', fontWeight: 700, color: item.tone }}>
                  {item.value}
                </div>
              </div>
            ))}
          </div>

          <div className="processing-grid">
            <div className="processing-col">
              <div className="processing-card" style={{ padding: '18px' }}>
                <h3 style={{ margin: '0 0 14px', fontSize: '14px', fontWeight: 700, color: '#334155', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                  Pipeline Stages
                </h3>
                {processingSteps.map((s, idx) => {
                  const isActive = s.status === 'active';
                  const isDone = s.status === 'done';
                  const isErr = s.status === 'error';
                  let dotColor = '#cbd5e1';
                  if (isDone) dotColor = '#10b981';
                  else if (isErr) dotColor = '#ef4444';
                  else if (isActive) dotColor = '#38bdf8';
                  const isLast = idx === processingSteps.length - 1;
                  return (
                    <div key={idx} style={{ display: 'flex', gap: '12px', position: 'relative', paddingBottom: isLast ? 0 : '15px' }}>
                      {!isLast && (
                        <div style={{
                          position: 'absolute',
                          left: '6px',
                          top: '14px',
                          width: '2px',
                          height: 'calc(100% - 8px)',
                          backgroundColor: isDone ? '#a7f3d0' : '#e2e8f0',
                        }} />
                      )}
                      <div style={{
                        width: '14px',
                        height: '14px',
                        borderRadius: '50%',
                        backgroundColor: dotColor,
                        marginTop: '2px',
                        flexShrink: 0,
                        boxShadow: isActive ? '0 0 0 4px rgba(56,189,248,0.2)' : undefined,
                        animation: isActive ? 'pulse 1.4s ease-in-out infinite' : undefined,
                      }} />
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <span style={{ fontSize: '13px', fontWeight: (isDone || isActive) ? 700 : 500, color: isErr ? '#b91c1c' : '#1e293b' }}>
                            {s.label}
                          </span>
                          {(isDone || isActive) && (
                            <span style={{ marginLeft: 'auto', fontSize: '11px', color: '#64748b', fontWeight: 600 }}>
                              {formatStepDuration(s)}
                            </span>
                          )}
                        </div>
                        {s.detail && (
                          <p style={{ margin: '3px 0 0', fontSize: '11px', color: '#64748b', lineHeight: 1.4 }}>
                            {s.detail}
                          </p>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>

              <div className="processing-card" style={{ padding: '18px' }}>
                <h3 style={{ margin: '0 0 12px', fontSize: '14px', fontWeight: 700, color: '#334155', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                  AI Batch Engine
                </h3>
                <div style={{ marginBottom: '12px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                    <span style={{ fontSize: '13px', color: '#0f172a', fontWeight: 700 }}>
                      Transactions processed
                    </span>
                    <span style={{ fontSize: '12px', color: '#334155', fontWeight: 600 }}>
                      {aiConfirmedTransactions}/{aiTotalTransactions || 0}
                    </span>
                  </div>
                  <div style={{ height: '8px', borderRadius: '999px', backgroundColor: '#e2e8f0', overflow: 'hidden', position: 'relative' }}>
                    <div style={{
                      width: `${aiDisplayedPct}%`,
                      height: '100%',
                      borderRadius: '999px',
                      background: 'linear-gradient(90deg, #67e8f9 0%, #38bdf8 100%)',
                      opacity: 0.75,
                      transition: 'width 0.25s linear',
                    }} />
                    <div style={{
                      position: 'absolute',
                      left: 0,
                      top: 0,
                      width: `${aiConfirmedPct}%`,
                      height: '100%',
                      borderRadius: '999px',
                      background: 'linear-gradient(90deg, #0284c7 0%, #0369a1 100%)',
                      transition: 'width 0.25s ease-out',
                    }} />
                  </div>
                  <div style={{ marginTop: '6px', fontSize: '11px', color: '#64748b' }}>
                    Confirmed {aiConfirmedPct}%{estimatedInFlightTransactions > 0 ? ` · In-flight estimate +${estimatedInFlightTransactions}` : ''}
                  </div>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                  <span style={{ fontSize: '13px', color: '#334155', fontWeight: 600 }}>
                    {batchTelemetry.completedBatches}/{batchTelemetry.totalBatches || 0} batches complete
                  </span>
                  <span style={{ fontSize: '12px', color: '#64748b' }}>
                    {batchCompletionPct}%
                  </span>
                </div>
                <div style={{ height: '7px', borderRadius: '999px', backgroundColor: '#e2e8f0', overflow: 'hidden', marginBottom: '12px' }}>
                  <div style={{
                    width: `${batchCompletionPct}%`,
                    height: '100%',
                    borderRadius: '999px',
                    background: 'linear-gradient(90deg, #0ea5e9 0%, #22c55e 100%)',
                    transition: 'width 0.35s ease',
                  }} />
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                  <div style={{ padding: '10px', borderRadius: '10px', backgroundColor: '#f8fafc', border: '1px solid #e2e8f0' }}>
                    <div style={{ fontSize: '11px', color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Mode</div>
                    <div style={{ marginTop: '4px', fontSize: '13px', fontWeight: 700, color: '#0f172a' }}>
                      {batchTelemetry.parallel ? 'Parallel' : 'Sequential'}
                    </div>
                  </div>
                  <div style={{ padding: '10px', borderRadius: '10px', backgroundColor: '#f8fafc', border: '1px solid #e2e8f0' }}>
                    <div style={{ fontSize: '11px', color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Workers</div>
                    <div style={{ marginTop: '4px', fontSize: '13px', fontWeight: 700, color: '#0f172a' }}>
                      {batchTelemetry.workers || '-'}
                    </div>
                  </div>
                  <div style={{ padding: '10px', borderRadius: '10px', backgroundColor: '#f8fafc', border: '1px solid #e2e8f0' }}>
                    <div style={{ fontSize: '11px', color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.5px' }}>In-flight</div>
                    <div style={{ marginTop: '4px', fontSize: '13px', fontWeight: 700, color: '#0f172a' }}>
                      {batchTelemetry.activeBatches}
                    </div>
                  </div>
                  <div style={{ padding: '10px', borderRadius: '10px', backgroundColor: '#f8fafc', border: '1px solid #e2e8f0' }}>
                    <div style={{ fontSize: '11px', color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Avg batch</div>
                    <div style={{ marginTop: '4px', fontSize: '13px', fontWeight: 700, color: '#0f172a' }}>
                      {batchTelemetry.avgBatchDurationMs > 0 ? formatElapsed(batchTelemetry.avgBatchDurationMs) : '-'}
                    </div>
                  </div>
                  <div style={{ padding: '10px', borderRadius: '10px', backgroundColor: '#f8fafc', border: '1px solid #e2e8f0' }}>
                    <div style={{ fontSize: '11px', color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.5px' }}>ETA</div>
                    <div style={{ marginTop: '4px', fontSize: '13px', fontWeight: 700, color: '#0f172a' }}>
                      {batchTelemetry.etaMs && batchTelemetry.etaMs > 0 ? formatElapsed(batchTelemetry.etaMs) : 'Finishing'}
                    </div>
                  </div>
                  <div style={{ padding: '10px', borderRadius: '10px', backgroundColor: '#f8fafc', border: '1px solid #e2e8f0' }}>
                    <div style={{ fontSize: '11px', color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Batch health</div>
                    <div style={{ marginTop: '4px', fontSize: '13px', fontWeight: 700, color: batchSuccessRate < 100 ? '#b45309' : '#0f172a' }}>
                      {batchSuccessRate}%
                    </div>
                  </div>
                </div>
                {(pipelineStats.warnings > 0 || pipelineStats.errors > 0) && (
                  <div style={{ marginTop: '12px', padding: '10px 12px', borderRadius: '10px', backgroundColor: '#fff7ed', border: '1px solid #fdba74' }}>
                    <span style={{ fontSize: '12px', color: '#9a3412', fontWeight: 600 }}>
                      {pipelineStats.warnings > 0 ? `${pipelineStats.warnings} warning(s)` : ''}
                      {pipelineStats.warnings > 0 && pipelineStats.errors > 0 ? ' · ' : ''}
                      {pipelineStats.errors > 0 ? `${pipelineStats.errors} error(s)` : ''}
                    </span>
                  </div>
                )}
              </div>

              {sortedCats.length > 0 && (
                <div className="processing-card" style={{ padding: '18px' }}>
                  <h3 style={{ margin: '0 0 12px', fontSize: '14px', fontWeight: 700, color: '#334155', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                    Category Distribution
                  </h3>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {sortedCats.slice(0, 8).map(([cat, count]) => {
                      const pct = totalCategorized > 0 ? Math.round((count / totalCategorized) * 100) : 0;
                      return (
                        <div key={cat}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '3px' }}>
                            <span style={{ fontSize: '12px', color: '#334155', fontWeight: 600 }}>{cat}</span>
                            <span style={{ fontSize: '11px', color: '#64748b' }}>{count} ({pct}%)</span>
                          </div>
                          <div style={{ height: '5px', borderRadius: '999px', backgroundColor: '#e2e8f0', overflow: 'hidden' }}>
                            <div style={{
                              width: `${pct}%`,
                              height: '100%',
                              borderRadius: '999px',
                              backgroundColor: cat === 'Other' ? '#f59e0b' : '#3b82f6',
                              transition: 'width 0.3s ease',
                            }} />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>

            <div className="processing-card" style={{ display: 'flex', flexDirection: 'column', minHeight: '620px', maxHeight: 'calc(100vh - 170px)' }}>
              <div style={{ padding: '16px 18px', borderBottom: '1px solid #e2e8f0', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '10px' }}>
                <div>
                  <h3 style={{ margin: 0, fontSize: '15px', color: '#0f172a', fontWeight: 700 }}>
                    Live Activity
                  </h3>
                  <p style={{ margin: '4px 0 0', fontSize: '12px', color: '#64748b' }}>
                    {eventLog.length} updates · {pipelineStats.dateRange ? `${pipelineStats.dateRange.months.length} month span` : 'Detecting date range'}
                  </p>
                </div>
                {!autoScroll && (
                  <button
                    onClick={() => {
                      setAutoScroll(true);
                      if (logContainerRef.current) logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
                    }}
                    style={{
                      border: '1px solid #cbd5e1',
                      backgroundColor: '#f8fafc',
                      color: '#334155',
                      borderRadius: '8px',
                      padding: '6px 10px',
                      fontSize: '12px',
                      fontWeight: 600,
                      cursor: 'pointer',
                    }}
                  >
                    Jump to latest
                  </button>
                )}
              </div>
              <div
                ref={logContainerRef}
                onScroll={(e) => {
                  const el = e.currentTarget;
                  const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 32;
                  setAutoScroll(atBottom);
                }}
                style={{ flex: 1, overflow: 'auto', padding: '12px', display: 'flex', flexDirection: 'column', gap: '8px' }}
              >
                {eventLog.length === 0 && (
                  <div style={{
                    borderRadius: '12px',
                    border: '1px dashed #cbd5e1',
                    backgroundColor: '#f8fafc',
                    padding: '16px',
                    textAlign: 'center',
                    color: '#64748b',
                    fontSize: '13px',
                  }}>
                    Waiting for first processing event...
                  </div>
                )}
                {eventLog.map((entry, idx) => {
                  const style = LEVEL_STYLES[entry.level] || LEVEL_STYLES.info;
                  return (
                    <div
                      key={idx}
                      style={{
                        display: 'flex',
                        gap: '10px',
                        alignItems: 'flex-start',
                        borderRadius: '12px',
                        border: '1px solid #e2e8f0',
                        backgroundColor: '#ffffff',
                        padding: '10px 12px',
                        animation: 'fadeInUp 0.2s ease-out',
                      }}
                    >
                      <span style={{
                        marginTop: '2px',
                        width: '10px',
                        height: '10px',
                        borderRadius: '50%',
                        backgroundColor: style.dot,
                        flexShrink: 0,
                      }} />
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '2px', flexWrap: 'wrap' }}>
                          <span style={{
                            padding: '2px 8px',
                            borderRadius: '999px',
                            backgroundColor: style.bg,
                            color: style.text,
                            fontSize: '11px',
                            fontWeight: 700,
                            textTransform: 'uppercase',
                            letterSpacing: '0.4px',
                          }}>
                            {style.label}
                          </span>
                          <span style={{ fontSize: '11px', color: '#64748b' }}>
                            {(entry.elapsed_ms / 1000).toFixed(1)}s
                          </span>
                        </div>
                        <p style={{ margin: 0, fontSize: '13px', color: '#334155', lineHeight: 1.45, wordBreak: 'break-word' }}>
                          {entry.message}
                        </p>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Main wizard form
  return (
    <>
      <style>{`
        @keyframes spin {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }
        @keyframes slideIn {
          from {
            opacity: 0;
            transform: translateY(-10px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
        .progress-step {
          animation: slideIn 0.3s ease-out;
        }
      `}</style>
      <div style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%)',
        padding: '24px',
      }}>
        <div style={{
          backgroundColor: 'white',
          borderRadius: '16px',
          padding: '48px',
          boxShadow: '0 20px 60px rgba(0,0,0,0.1)',
          maxWidth: '1400px',
          width: '100%',
        }}>
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '12px' }}>
            <Link
              to="/dashboard"
              style={{
                padding: '8px 12px',
                backgroundColor: '#111827',
                color: 'white',
                borderRadius: '8px',
                textDecoration: 'none',
                fontSize: '13px',
                fontWeight: 600,
              }}
            >
              View Dashboard
            </Link>
          </div>
          {/* Progress indicator */}
          <div style={{ marginBottom: '32px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
              {['file_upload', 'currency_selection', 'header_mapping'].map((s, idx) => {
                const stepIndex = ['file_upload', 'currency_selection', 'header_mapping'].indexOf(step);
                const isActive = idx <= stepIndex;
                return (
                  <div
                    key={s}
                    style={{
                      width: '30px',
                      height: '30px',
                      borderRadius: '50%',
                      backgroundColor: isActive ? '#dc2626' : '#e5e7eb',
                      color: isActive ? 'white' : '#9ca3af',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: '12px',
                      fontWeight: 600,
                    }}
                  >
                    {idx + 1}
                  </div>
                );
              })}
            </div>
          </div>

          <div style={{ textAlign: 'center', marginBottom: '32px' }}>
            <h1 style={{
              fontSize: '32px',
              fontWeight: 700,
              color: '#dc2626',
              margin: '0 0 8px 0',
              letterSpacing: '-0.5px',
            }}>
              NumbyAI
            </h1>
            <p style={{
              fontSize: '16px',
              color: '#6b7280',
              margin: 0,
            }}>
              {step === 'file_upload' && (isUploading ? 'Analyzing your statement...' : (!bankName && !showNewBankInput) ? 'Select your bank to get started' : 'Upload your bank statement')}
              {step === 'currency_selection' && 'Select your currency'}
              {step === 'header_mapping' && (isAutoDetected ? 'Review detected columns' : 'Map statement columns')}
            </p>
          </div>

          {error && (
            <div style={{
              padding: '12px',
              backgroundColor: '#fee2e2',
              border: '1px solid #fecaca',
              borderRadius: '8px',
              marginBottom: '24px',
              color: '#991b1b',
              fontSize: '14px',
            }}>
              {error}
            </div>
          )}

          {duplicateWarning && (
            <div style={{
              padding: '16px',
              backgroundColor: '#fffbeb',
              border: '1px solid #f59e0b',
              borderRadius: '8px',
              marginBottom: '24px',
            }}>
              <p style={{ margin: '0 0 4px', fontWeight: 600, color: '#92400e', fontSize: '14px' }}>
                ⚠️ Possible duplicate statement
              </p>
              <p style={{ margin: '0 0 12px', color: '#78350f', fontSize: '13px' }}>
                {duplicateWarning.overlap_pct}% overlap with existing data for this bank
                ({duplicateWarning.existing_count} existing vs {duplicateWarning.new_count} new transactions,
                {' '}{duplicateWarning.date_min} → {duplicateWarning.date_max}).
                You may be importing a statement you already uploaded.
              </p>
              <div style={{ display: 'flex', gap: '8px' }}>
                <button
                  onClick={() => { setDuplicateWarning(null); void handleProcess(true); }}
                  style={{
                    padding: '8px 16px',
                    backgroundColor: '#d97706',
                    color: 'white',
                    border: 'none',
                    borderRadius: '6px',
                    fontSize: '13px',
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  Import anyway
                </button>
                <button
                  onClick={() => setDuplicateWarning(null)}
                  style={{
                    padding: '8px 16px',
                    backgroundColor: 'white',
                    color: '#374151',
                    border: '1px solid #d1d5db',
                    borderRadius: '6px',
                    fontSize: '13px',
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          {/* Step 1: Main Screen - File Upload, Bank Selection, Net Flow */}
          {step === 'file_upload' && (
            <div>
              {/* Bank Selection Section — must be selected before uploading */}
              <div style={{ marginBottom: '24px' }}>
                <label style={{
                  display: 'block',
                  fontSize: '14px',
                  fontWeight: 600,
                  color: '#374151',
                  marginBottom: '8px',
                }}>
                  Bank Name *
                </label>
                {!showNewBankInput ? (
                  <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                    <select
                      value={bankName}
                      onChange={(e) => setBankName(e.target.value)}
                      disabled={isUploading}
                      style={{
                        flex: 1,
                        padding: '12px',
                        border: '1px solid #d1d5db',
                        borderRadius: '8px',
                        fontSize: '14px',
                        opacity: isUploading ? 0.6 : 1,
                        cursor: isUploading ? 'not-allowed' : 'pointer',
                      }}
                    >
                      <option value="">Select bank...</option>
                      {banks.map(bank => (
                        <option key={bank} value={bank}>{bank}</option>
                      ))}
                    </select>
                    <button
                      onClick={() => setShowNewBankInput(true)}
                      disabled={isUploading}
                      title="Add new bank"
                      style={{
                        flexShrink: 0,
                        width: '44px',
                        height: '44px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        backgroundColor: '#f3f4f6',
                        border: '1px solid #d1d5db',
                        borderRadius: '8px',
                        fontSize: '20px',
                        color: '#374151',
                        cursor: isUploading ? 'not-allowed' : 'pointer',
                        opacity: isUploading ? 0.6 : 1,
                        lineHeight: 1,
                      }}
                    >
                      +
                    </button>
                  </div>
                ) : (
                  <div>
                    <div style={{ display: 'flex', gap: '8px', alignItems: 'center', marginBottom: '8px' }}>
                      <input
                        type="text"
                        value={newBankName}
                        onChange={(e) => setNewBankName(e.target.value)}
                        placeholder="Enter bank name..."
                        disabled={isUploading}
                        autoFocus
                        onKeyDown={(e) => {
                          if (e.key === 'Escape') { setShowNewBankInput(false); setNewBankName(''); }
                        }}
                        style={{
                          flex: 1,
                          padding: '12px',
                          border: '1px solid #6366f1',
                          borderRadius: '8px',
                          fontSize: '14px',
                          opacity: isUploading ? 0.6 : 1,
                          outline: 'none',
                        }}
                      />
                      <button
                        onClick={() => { setShowNewBankInput(false); setNewBankName(''); }}
                        disabled={isUploading}
                        style={{
                          flexShrink: 0,
                          padding: '8px 14px',
                          backgroundColor: '#e5e7eb',
                          color: '#374151',
                          border: '1px solid #d1d5db',
                          borderRadius: '8px',
                          fontSize: '13px',
                          cursor: isUploading ? 'not-allowed' : 'pointer',
                          opacity: isUploading ? 0.6 : 1,
                          whiteSpace: 'nowrap',
                        }}
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
              </div>

              {/* Profile selector */}
              <div style={{ marginBottom: '24px' }}>
                <label style={{
                  display: 'block',
                  fontSize: '14px',
                  fontWeight: 600,
                  color: '#374151',
                  marginBottom: '4px',
                }}>
                  Person / Profile
                </label>
                <div style={{ fontSize: '12px', color: '#6b7280', marginBottom: '8px' }}>
                  Tag transactions to a person (e.g. "Me", "Partner", "Joint"). Optional.
                </div>
                {!showNewProfileInput ? (
                  <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                    <select
                      value={selectedProfile}
                      onChange={(e) => setSelectedProfile(e.target.value)}
                      disabled={isUploading}
                      style={{
                        flex: 1,
                        padding: '12px',
                        border: '1px solid #d1d5db',
                        borderRadius: '8px',
                        fontSize: '14px',
                        opacity: isUploading ? 0.6 : 1,
                        cursor: isUploading ? 'not-allowed' : 'pointer',
                      }}
                    >
                      <option value="">No profile (skip)</option>
                      {profiles.map(p => (
                        <option key={p} value={p}>{p}</option>
                      ))}
                    </select>
                    <button
                      onClick={() => { setShowNewProfileInput(true); setSelectedProfile(''); }}
                      disabled={isUploading}
                      title="Add new profile"
                      style={{
                        flexShrink: 0,
                        width: '44px',
                        height: '44px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        backgroundColor: '#f3f4f6',
                        border: '1px solid #d1d5db',
                        borderRadius: '8px',
                        fontSize: '20px',
                        color: '#374151',
                        cursor: isUploading ? 'not-allowed' : 'pointer',
                        opacity: isUploading ? 0.6 : 1,
                        lineHeight: 1,
                      }}
                    >
                      +
                    </button>
                  </div>
                ) : (
                  <div>
                    <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                      <input
                        type="text"
                        value={newProfileName}
                        onChange={(e) => setNewProfileName(e.target.value)}
                        placeholder="e.g. Me, Partner, Joint..."
                        disabled={isUploading}
                        autoFocus
                        onKeyDown={(e) => {
                          if (e.key === 'Escape') { setShowNewProfileInput(false); setNewProfileName(''); }
                        }}
                        style={{
                          flex: 1,
                          padding: '12px',
                          border: '1px solid #6366f1',
                          borderRadius: '8px',
                          fontSize: '14px',
                          opacity: isUploading ? 0.6 : 1,
                          outline: 'none',
                        }}
                      />
                      <button
                        onClick={() => { setShowNewProfileInput(false); setNewProfileName(''); }}
                        disabled={isUploading}
                        style={{
                          flexShrink: 0,
                          padding: '8px 14px',
                          backgroundColor: '#e5e7eb',
                          color: '#374151',
                          border: '1px solid #d1d5db',
                          borderRadius: '8px',
                          fontSize: '13px',
                          cursor: isUploading ? 'not-allowed' : 'pointer',
                          opacity: isUploading ? 0.6 : 1,
                          whiteSpace: 'nowrap',
                        }}
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
              </div>

              {/* File Upload Section — enabled only after bank is selected */}
              <div style={{ marginBottom: '24px' }}>
                <label style={{
                  display: 'block',
                  fontSize: '14px',
                  fontWeight: 600,
                  color: '#374151',
                  marginBottom: '8px',
                }}>
                  Bank Statement (CSV/Excel)
                </label>
                {!bankName && !showNewBankInput && (
                  <div style={{
                    fontSize: '12px',
                    color: '#9ca3af',
                    marginBottom: '8px',
                    fontStyle: 'italic',
                  }}>
                    Select a bank above to enable file upload
                  </div>
                )}
                <input
                  type="file"
                  accept=".csv,.xlsx,.xls"
                  onChange={(e) => {
                    const selectedFile = e.target.files?.[0];
                    if (selectedFile) handleFileSelect(selectedFile);
                  }}
                  disabled={isUploading || (!bankName && !showNewBankInput)}
                  style={{
                    width: '100%',
                    padding: '12px',
                    border: '2px dashed #d1d5db',
                    borderRadius: '8px',
                    fontSize: '14px',
                    cursor: (isUploading || (!bankName && !showNewBankInput)) ? 'not-allowed' : 'pointer',
                    opacity: (isUploading || (!bankName && !showNewBankInput)) ? 0.5 : 1,
                  }}
                />
                {file && (
                  <div style={{ marginTop: '12px' }}>
                    <div style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px',
                      marginBottom: isUploading ? '12px' : '0',
                    }}>
                      <span style={{ fontSize: '14px', color: '#6b7280' }}>
                        Selected: <strong>{file.name}</strong>
                      </span>
                      {isUploading && (
                        <div style={{
                          width: '16px',
                          height: '16px',
                          border: '2px solid #f3f4f6',
                          borderTop: '2px solid #dc2626',
                          borderRadius: '50%',
                          animation: 'spin 0.8s linear infinite',
                        }} />
                      )}
                    </div>

                    {isUploading && uploadProgress && (
                      <div style={{
                        marginTop: '12px',
                        padding: '12px',
                        backgroundColor: '#f9fafb',
                        borderRadius: '8px',
                        border: '1px solid #e5e7eb',
                      }}>
                        <div style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '12px',
                          marginBottom: '8px',
                        }}>
                          <div style={{
                            width: '20px',
                            height: '20px',
                            border: '3px solid #f3f4f6',
                            borderTop: '3px solid #dc2626',
                            borderRadius: '50%',
                            animation: 'spin 0.8s linear infinite',
                          }} />
                          <span style={{
                            fontSize: '14px',
                            fontWeight: 600,
                            color: '#374151',
                          }}>
                            {uploadProgress}
                          </span>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>

              <div style={{ marginBottom: '24px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontSize: '13px', fontWeight: 600, color: '#6b7280' }}>Processing model:</span>
                <span style={{
                  fontSize: '12px',
                  fontWeight: 700,
                  color: '#374151',
                  backgroundColor: '#f3f4f6',
                  border: '1px solid #e5e7eb',
                  borderRadius: '6px',
                  padding: '3px 10px',
                  letterSpacing: '0.02em',
                }}>
                  {llmModel ? `Ollama · ${llmModel}` : 'Ollama · Local'}
                </span>
              </div>

              {/* Continue Button */}
              <button
                onClick={handleMainScreenContinue}
                disabled={isUploading || isLoadingBankPrefs || (!file && !uploadResult) || (!bankName && !showNewBankInput)}
                style={{
                  width: '100%',
                  padding: '14px',
                  backgroundColor: (!isUploading && !isLoadingBankPrefs && (file || uploadResult) && (bankName || showNewBankInput)) ? '#dc2626' : '#9ca3af',
                  color: 'white',
                  border: 'none',
                  borderRadius: '8px',
                  fontSize: '16px',
                  fontWeight: 600,
                  cursor: (!isUploading && !isLoadingBankPrefs && (file || uploadResult) && (bankName || showNewBankInput)) ? 'pointer' : 'not-allowed',
                }}
              >
                {isUploading ? 'Uploading...' :
                  isLoadingBankPrefs ? 'Loading saved settings...' :
                    (!bankName && !showNewBankInput) ? 'Select a bank first' :
                      !file && !uploadResult ? 'Upload a file' :
                        hasSavedMappings ? 'Review Mapping' :
                          hasParsingPreferences ? 'Process Statement' :
                            'Continue to Mapping'}
              </button>
            </div>
          )}

          {/* Step 2: Currency Selection */}
          {step === 'currency_selection' && (
            <div>
              <label style={{
                display: 'block',
                fontSize: '14px',
                fontWeight: 600,
                color: '#374151',
                marginBottom: '8px',
              }}>
                Functional Currency {uploadResult?.currency_detected && `(Detected: ${uploadResult.currency_detected})`}
              </label>
              <div style={{
                backgroundColor: '#f0f9ff',
                border: '1px solid #bae6fd',
                borderRadius: '8px',
                padding: '12px 14px',
                marginBottom: '16px',
                fontSize: '13px',
                color: '#0c4a6e',
                lineHeight: '1.5',
              }}>
                <strong>Your functional currency</strong> is the main currency you transact in — the one the dashboard displays everything in.
                {' '}NumbyAI supports statements in any currency, but all amounts are converted to your functional currency (at that month's average exchange rate) so your dashboard totals stay consistent.
              </div>
              <select
                value={currency}
                onChange={(e) => setCurrency(e.target.value)}
                style={{
                  width: '100%',
                  padding: '12px',
                  border: '1px solid #d1d5db',
                  borderRadius: '8px',
                  fontSize: '14px',
                  marginBottom: '16px',
                }}
              >
                <option value="">Select currency...</option>
                {COMMON_CURRENCIES.map(curr => (
                  <option key={curr} value={curr}>{curr}</option>
                ))}
              </select>
              <button
                onClick={handleCurrencySave}
                disabled={!currency}
                style={{
                  width: '100%',
                  padding: '14px',
                  backgroundColor: currency ? '#dc2626' : '#9ca3af',
                  color: 'white',
                  border: 'none',
                  borderRadius: '8px',
                  fontSize: '16px',
                  fontWeight: 600,
                  cursor: currency ? 'pointer' : 'not-allowed',
                }}
              >
                Continue
              </button>
            </div>
          )}


          {/* Step 4: Header Mapping - Lunch Money Style */}
          {step === 'header_mapping' && uploadResult?.detected_headers && (
            <div>
              {/* Instruction Box */}
              <div style={{
                backgroundColor: isAutoDetected ? '#065f46' : '#1e40af',
                color: 'white',
                padding: '16px',
                borderRadius: '8px',
                marginBottom: '24px',
              }}>
                {isAutoDetected ? (
                  <>
                    <p style={{ margin: '0 0 8px 0', fontSize: '14px', fontWeight: 500 }}>
                      We detected your column layout automatically. Please review and adjust if needed.
                    </p>
                    <p style={{ margin: '0', fontSize: '13px', fontWeight: 400, opacity: 0.9 }}>
                      Columns marked with a green dot were detected with high confidence. Orange dots indicate medium confidence -- double-check those.
                    </p>
                  </>
                ) : (
                  <>
                    <p style={{ margin: '0 0 8px 0', fontSize: '14px', fontWeight: 500 }}>
                      Match columns. Use the dropdowns to correspond columns from your file to the appropriate fields.
                    </p>
                    <p style={{ margin: '0', fontSize: '13px', fontWeight: 400, opacity: 0.9 }}>
                      You can select <strong>multiple columns as Description</strong> and <strong>multiple columns as Amount</strong>. Amount columns can be inverted independently.
                    </p>
                  </>
                )}
              </div>

              {/* Combined Scrollable Container for Dropdowns and Table */}
              {uploadResult.preview_data && uploadResult.preview_data.length > 0 && (
                <div style={{ marginBottom: '24px' }}>
                  <div style={{
                    border: '1px solid #d1d5db',
                    borderRadius: '8px',
                    overflow: 'auto',
                    maxHeight: '600px',
                    width: '100%',
                  }}>
                    {/* Horizontal Dropdowns Row - Fixed at top */}
                    <div style={{
                      display: 'flex',
                      gap: '0',
                      padding: '0',
                      backgroundColor: '#f9fafb',
                      borderBottom: '2px solid #d1d5db',
                      position: 'sticky',
                      top: 0,
                      zIndex: 20,
                    }}>
                      {/* Row number column header - matches table row number column */}
                      <div style={{
                        minWidth: '50px',
                        maxWidth: '50px',
                        width: '50px',
                        flexShrink: 0,
                        padding: '8px',
                        boxSizing: 'border-box',
                      }}></div>
                      <div style={{
                        minWidth: '130px',
                        maxWidth: '130px',
                        width: '130px',
                        flexShrink: 0,
                        padding: '8px',
                        boxSizing: 'border-box',
                        fontSize: '12px',
                        fontWeight: 600,
                        color: '#374151',
                      }}>
                        Include in Net Flow
                      </div>
                      {Array.from({ length: totalPreviewColumns }, (_, i) => {
                        const fieldOptions = [
                          { value: 'do_not_use', label: 'Do not use' },
                          { value: 'date', label: 'Date *' },
                          { value: 'vendor_payee', label: 'Vendor/Payee' },
                          { value: 'description', label: 'Description *' },
                          { value: 'category', label: 'Category' },
                          { value: 'balance', label: 'Balance' },
                          { value: 'amount', label: 'Amount * (multi)' },
                          { value: 'inflow', label: 'Inflow' },
                          { value: 'outflow', label: 'Outflow' },
                          { value: 'currency', label: 'Currency' },
                        ];

                        const currentFieldType = columnMappings[i];
                        const fieldConfidence = currentFieldType && currentFieldType !== 'do_not_use'
                          ? detectionConfidence[currentFieldType] || null
                          : null;
                        const isDetected = isAutoDetected && currentFieldType && currentFieldType !== 'do_not_use';
                        const confidenceColor = fieldConfidence === 'high' ? '#10b981'
                          : fieldConfidence === 'medium' ? '#f59e0b'
                          : fieldConfidence === 'low' ? '#ef4444' : null;

                        return (
                          <div key={i} style={{
                            minWidth: '180px',
                            maxWidth: '180px',
                            width: '180px',
                            flexShrink: 0,
                            padding: '8px',
                            boxSizing: 'border-box',
                          }}>
                            <label style={{
                              display: 'flex',
                              alignItems: 'center',
                              gap: '5px',
                              fontSize: '12px',
                              fontWeight: 600,
                              color: '#374151',
                              marginBottom: '4px',
                            }}>
                              {getColumnLetter(i)}
                              {isDetected && confidenceColor && (
                                <span
                                  title={`${fieldConfidence} confidence`}
                                  style={{
                                    display: 'inline-block',
                                    width: '7px',
                                    height: '7px',
                                    borderRadius: '50%',
                                    backgroundColor: confidenceColor,
                                    flexShrink: 0,
                                  }}
                                />
                              )}
                            </label>
                            <select
                              value={columnMappings[i] || 'do_not_use'}
                              onChange={(e) => {
                                const newMappings = { ...columnMappings };
                                const nextFieldType = e.target.value;
                                if (e.target.value === 'do_not_use') {
                                  delete newMappings[i];
                                } else {
                                  newMappings[i] = nextFieldType;
                                }
                                setColumnMappings(newMappings);
                                if (nextFieldType !== 'amount') {
                                  setAmountColumnInversions((prev) => {
                                    const next = { ...prev };
                                    delete next[i];
                                    return next;
                                  });
                                }
                              }}
                              style={{
                                width: '100%',
                                padding: '8px',
                                border: isDetected && confidenceColor
                                  ? `2px solid ${confidenceColor}`
                                  : '1px solid #d1d5db',
                                borderRadius: '6px',
                                fontSize: '13px',
                                backgroundColor: 'white',
                                boxSizing: 'border-box',
                              }}
                            >
                              {fieldOptions.map(opt => (
                                <option key={opt.value} value={opt.value}>{opt.label}</option>
                              ))}
                            </select>
                            {columnMappings[i] === 'amount' && (
                              <label
                                style={{
                                  display: 'flex',
                                  alignItems: 'center',
                                  gap: '6px',
                                  marginTop: '6px',
                                  fontSize: '11px',
                                  color: '#374151',
                                }}
                              >
                                <input
                                  type="checkbox"
                                  checked={Boolean(amountColumnInversions[i])}
                                  onChange={(e) => {
                                    const isChecked = e.target.checked;
                                    setAmountColumnInversions((prev) => {
                                      const next = { ...prev };
                                      if (isChecked) {
                                        next[i] = true;
                                      } else {
                                        delete next[i];
                                      }
                                      return next;
                                    });
                                  }}
                                />
                                Invert this amount column
                              </label>
                            )}
                          </div>
                        );
                      })}
                    </div>

                    {/* Preview Table - Scrolls with dropdowns */}
                    <table style={{
                      width: 'auto',
                      tableLayout: 'fixed',
                      borderCollapse: 'collapse',
                      fontSize: '12px',
                      fontFamily: 'monospace',
                    }}>
                      <thead>
                        <tr>
                          <th style={{
                            padding: '8px',
                            backgroundColor: '#f3f4f6',
                            border: '1px solid #d1d5db',
                            textAlign: 'center',
                            fontWeight: 600,
                            position: 'sticky',
                            left: 0,
                            zIndex: 10,
                            minWidth: '50px',
                            maxWidth: '50px',
                            width: '50px',
                            boxSizing: 'border-box',
                          }}></th>
                          <th style={{
                            padding: '8px',
                            backgroundColor: '#f3f4f6',
                            border: '1px solid #d1d5db',
                            textAlign: 'center',
                            fontWeight: 600,
                            minWidth: '130px',
                            maxWidth: '130px',
                            width: '130px',
                            boxSizing: 'border-box',
                          }}>
                            Include
                          </th>
                          {Array.from({ length: totalPreviewColumns }, (_, i) => {
                            const mappedField = columnMappings[i];
                            return (
                              <th key={i} style={{
                                padding: '8px',
                                backgroundColor: mappedField && mappedField !== 'do_not_use' ? '#dbeafe' : '#f3f4f6',
                                border: '1px solid #d1d5db',
                                textAlign: 'center',
                                fontWeight: 600,
                                minWidth: '180px',
                                maxWidth: '180px',
                                width: '180px',
                                boxSizing: 'border-box',
                              }}>
                                {getColumnLetter(i)}
                                {mappedField && mappedField !== 'do_not_use' && (
                                  <div style={{ fontSize: '10px', color: '#3b82f6', marginTop: '2px' }}>
                                    → {mappedField.replace('_', '/')}
                                  </div>
                                )}
                              </th>
                            );
                          })}
                        </tr>
                      </thead>
                      <tbody>
                        {uploadResult.preview_data.map((row: any[], rowIndex: number) => {
                          // Since preview_data now shows raw file (header=None), rowIndex maps directly to file rows
                          // rowIndex 0 = file row 1, rowIndex 1 = file row 2, etc.
                          const fileRowNumber = rowIndex + 1;
                          const isFirstTransactionRow = fileRowNumber === firstTransactionRow;
                          const isTransactionCandidate = fileRowNumber >= firstTransactionRow;
                          const isIncluded = !excludedTransactionRowSet.has(fileRowNumber);
                          const suspiciousReasons = suspiciousRowsByNumber.get(fileRowNumber) || [];
                          const isSuspicious = suspiciousReasons.length > 0;
                          return (
                            <tr key={rowIndex} style={{
                              backgroundColor: isFirstTransactionRow
                                ? '#fef3c7' // Highlight with yellow background
                                : isSuspicious
                                  ? '#fff7ed'
                                : (rowIndex % 2 === 0 ? '#ffffff' : '#f9fafb'),
                              border: isFirstTransactionRow
                                ? '2px solid #f59e0b'
                                : isSuspicious
                                  ? '1px solid #fdba74'
                                  : undefined,
                              boxShadow: isFirstTransactionRow ? '0 0 0 1px #f59e0b' : undefined,
                            }}>
                              <td style={{
                                padding: '8px',
                                backgroundColor: isFirstTransactionRow ? '#fef3c7' : '#f3f4f6',
                                border: isFirstTransactionRow ? '2px solid #f59e0b' : '1px solid #d1d5db',
                                textAlign: 'center',
                                fontWeight: 600,
                                position: 'sticky',
                                left: 0,
                                zIndex: 5,
                                minWidth: '50px',
                                maxWidth: '50px',
                                width: '50px',
                                boxSizing: 'border-box',
                              }}>
                                {fileRowNumber}
                              </td>
                              <td style={{
                                padding: '6px 8px',
                                border: '1px solid #d1d5db',
                                minWidth: '130px',
                                maxWidth: '130px',
                                width: '130px',
                                boxSizing: 'border-box',
                                verticalAlign: 'top',
                              }}>
                                {isTransactionCandidate ? (
                                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                                    <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px' }}>
                                      <input
                                        type="checkbox"
                                        checked={isIncluded}
                                        onChange={(e) => {
                                          const checked = e.target.checked;
                                          setExcludedTransactionRows((prev) => {
                                            if (checked) {
                                              return prev.filter((rowNum) => rowNum !== fileRowNumber);
                                            }
                                            if (prev.includes(fileRowNumber)) {
                                              return prev;
                                            }
                                            return [...prev, fileRowNumber].sort((a, b) => a - b);
                                          });
                                        }}
                                      />
                                      {isIncluded ? 'Included' : 'Excluded'}
                                    </label>
                                    {isSuspicious && (
                                      <div style={{ fontSize: '11px', color: '#9a3412', lineHeight: 1.3 }}>
                                        Flag: {suspiciousReasons.join(' ')}
                                      </div>
                                    )}
                                  </div>
                                ) : (
                                  <span style={{ color: '#9ca3af', fontSize: '12px' }}>N/A</span>
                                )}
                              </td>
                              {Array.from({ length: totalPreviewColumns }, (_, colIndex) => (
                                <td key={colIndex} style={{
                                  padding: '8px',
                                  border: '1px solid #d1d5db',
                                  whiteSpace: 'nowrap',
                                  overflow: 'hidden',
                                  textOverflow: 'ellipsis',
                                  minWidth: '180px',
                                  maxWidth: '180px',
                                  width: '180px',
                                  boxSizing: 'border-box',
                                }}>
                                  {row[colIndex] ?? ''}
                                </td>
                              ))}
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* First Transaction Row Input */}
              <div style={{ marginBottom: '24px' }}>
                <label style={{
                  display: 'block',
                  fontSize: '14px',
                  fontWeight: 600,
                  color: '#374151',
                  marginBottom: '8px',
                }}>
                  Row number of first transaction *
                </label>
                <input
                  type="number"
                  min="1"
                  max={uploadResult.total_rows || 100}
                  value={firstTransactionRow}
                  onChange={(e) => setFirstTransactionRow(parseInt(e.target.value) || 1)}
                  placeholder="e.g., 5 if transactions start at row 5"
                  style={{
                    width: '100%',
                    padding: '12px',
                    border: '1px solid #d1d5db',
                    borderRadius: '8px',
                    fontSize: '14px',
                  }}
                />
                <p style={{ marginTop: '4px', fontSize: '12px', color: '#9ca3af' }}>
                  Specify which row contains the first transaction (some statements have headers or summary rows at the top)
                </p>
                <label
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    marginTop: '12px',
                    fontSize: '13px',
                    color: '#374151',
                    fontWeight: 500,
                  }}
                >
                  <input
                    type="checkbox"
                    checked={invertAmountSign}
                    onChange={(e) => setInvertAmountSign(e.target.checked)}
                  />
                  Invert net flow formula (multiply final total by -1)
                </label>
              </div>

              <div
                style={{
                  marginBottom: '24px',
                  padding: '16px',
                  borderRadius: '8px',
                  border: '1px solid #d1d5db',
                  backgroundColor: '#f9fafb',
                }}
              >
                <div style={{ fontSize: '13px', fontWeight: 700, color: '#374151', marginBottom: '8px' }}>
                  Amount Verification
                </div>
                {isCalculatingMappingNetFlow && (
                  <div style={{ fontSize: '13px', color: '#6b7280' }}>
                    Verifying amounts...
                  </div>
                )}
                {!isCalculatingMappingNetFlow && mappingNetFlowError && (
                  <div style={{
                    padding: '10px',
                    backgroundColor: '#fee2e2',
                    border: '1px solid #fecaca',
                    borderRadius: '6px',
                    fontSize: '13px',
                    color: '#b91c1c',
                  }}>
                    {mappingNetFlowError}
                  </div>
                )}
                {!isCalculatingMappingNetFlow && !mappingNetFlowError && mappingNetFlowPreview && (
                  <div style={{
                    padding: '12px',
                    backgroundColor: '#f0fdf4',
                    border: '1px solid #bbf7d0',
                    borderRadius: '8px',
                  }}>
                    <div style={{ fontSize: '20px', fontWeight: 700, color: mappingNetFlowPreview.net_flow < 0 ? '#dc2626' : '#16a34a', marginBottom: '8px' }}>
                      Net: {mappingNetFlowPreview.net_flow.toFixed(2)} {mappingNetFlowPreview.currency}
                    </div>
                    {mappingNetFlowPreview.functional_currency && mappingNetFlowPreview.converted_net_flow != null && (
                      <div style={{
                        fontSize: '14px',
                        fontWeight: 600,
                        color: mappingNetFlowPreview.converted_net_flow < 0 ? '#dc2626' : '#16a34a',
                        marginBottom: '8px',
                        padding: '4px 8px',
                        backgroundColor: '#eff6ff',
                        borderRadius: '4px',
                        border: '1px solid #bfdbfe',
                      }}>
                        Converted: {mappingNetFlowPreview.converted_net_flow.toFixed(2)} {mappingNetFlowPreview.functional_currency}
                      </div>
                    )}
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px 16px', fontSize: '12px', color: '#374151' }}>
                      <div>Inflows: <strong>{mappingNetFlowPreview.inflow_total.toFixed(2)}</strong>{mappingNetFlowPreview.converted_inflow_total != null && mappingNetFlowPreview.functional_currency ? <span style={{ color: '#6b7280' }}>{' '}({mappingNetFlowPreview.converted_inflow_total.toFixed(2)} {mappingNetFlowPreview.functional_currency})</span> : null}</div>
                      <div>Outflows: <strong>{mappingNetFlowPreview.outflow_total.toFixed(2)}</strong>{mappingNetFlowPreview.converted_outflow_total != null && mappingNetFlowPreview.functional_currency ? <span style={{ color: '#6b7280' }}>{' '}({mappingNetFlowPreview.converted_outflow_total.toFixed(2)} {mappingNetFlowPreview.functional_currency})</span> : null}</div>
                      <div>Transactions: <strong>{mappingNetFlowPreview.transaction_count}</strong></div>
                      <div>Excluded: <strong>{mappingNetFlowPreview.excluded_transaction_count}</strong></div>
                    </div>
                    {mappingNetFlowPreview.parsed_transaction_count > mappingNetFlowPreview.transaction_count + mappingNetFlowPreview.excluded_transaction_count && (
                      <div style={{
                        marginTop: '8px',
                        padding: '6px 8px',
                        backgroundColor: '#fef3c7',
                        border: '1px solid #fde68a',
                        borderRadius: '4px',
                        fontSize: '11px',
                        color: '#92400e',
                      }}>
                        {mappingNetFlowPreview.parsed_transaction_count - mappingNetFlowPreview.transaction_count - mappingNetFlowPreview.excluded_transaction_count} row(s) failed to parse. Check your column mappings if totals look wrong.
                      </div>
                    )}
                    {mappingNetFlowPreview.suspicious_transaction_count > 0 && (
                      <div style={{ marginTop: '6px', fontSize: '11px', color: '#9a3412' }}>
                        {mappingNetFlowPreview.suspicious_transaction_count} suspicious transaction(s) flagged
                      </div>
                    )}
                    {!uploadResult?.parsing_preferences_exist && (
                      <div style={{
                        marginTop: '10px',
                        padding: '8px 10px',
                        backgroundColor: '#fffbeb',
                        border: '1px solid #fde68a',
                        borderRadius: '6px',
                        fontSize: '11px',
                        color: '#92400e',
                        lineHeight: 1.4,
                      }}>
                        First time with this bank? We recommend cross-checking these totals against your bank&apos;s PDF statement or online portal to confirm everything imported correctly.
                      </div>
                    )}
                  </div>
                )}
                {!isCalculatingMappingNetFlow && !mappingNetFlowError && !mappingNetFlowPreview && (
                  <div style={{ fontSize: '12px', color: '#9ca3af' }}>
                    Map Date, Description, and Amount/Inflow/Outflow to verify totals.
                  </div>
                )}
              </div>

              <div style={{ display: 'flex', gap: '12px' }}>
                <button
                  onClick={() => setStep('file_upload')}
                  style={{
                    flex: '0 0 auto',
                    padding: '14px 20px',
                    backgroundColor: 'white',
                    color: '#374151',
                    border: '1px solid #d1d5db',
                    borderRadius: '8px',
                    fontSize: '16px',
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  ← Back
                </button>
                <button
                  onClick={handleHeaderMappingSave}
                  disabled={
                    !Object.values(columnMappings).includes('date') ||
                    (!Object.values(columnMappings).includes('amount') &&
                      !Object.values(columnMappings).includes('inflow') &&
                      !Object.values(columnMappings).includes('outflow')) ||
                    !Object.values(columnMappings).includes('description') ||
                    !firstTransactionRow ||
                    !mappingNetFlowPreview ||
                    isCalculatingMappingNetFlow
                  }
                  style={{
                    flex: 1,
                    padding: '14px',
                    backgroundColor: (
                      Object.values(columnMappings).includes('date') &&
                      (Object.values(columnMappings).includes('amount') ||
                        Object.values(columnMappings).includes('inflow') ||
                        Object.values(columnMappings).includes('outflow')) &&
                      Object.values(columnMappings).includes('description') &&
                      firstTransactionRow &&
                      mappingNetFlowPreview &&
                      !isCalculatingMappingNetFlow
                    ) ? '#dc2626' : '#9ca3af',
                    color: 'white',
                    border: 'none',
                    borderRadius: '8px',
                    fontSize: '16px',
                    fontWeight: 600,
                    cursor: (
                      Object.values(columnMappings).includes('date') &&
                      (Object.values(columnMappings).includes('amount') ||
                        Object.values(columnMappings).includes('inflow') ||
                        Object.values(columnMappings).includes('outflow')) &&
                      Object.values(columnMappings).includes('description') &&
                      firstTransactionRow &&
                      mappingNetFlowPreview &&
                      !isCalculatingMappingNetFlow
                    ) ? 'pointer' : 'not-allowed',
                  }}
                >
                  {isCalculatingMappingNetFlow ? 'Verifying...'
                    : isAutoDetected ? 'Looks Good \u2014 Process'
                    : 'Save & Process Statement'}
                </button>
              </div>
            </div>
          )}

        </div>
      </div>
    </>
  );
};
