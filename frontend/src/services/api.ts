import {
  MarketStatus,
  Candle,
  OptionChainResponse,
  StrategyStatus,
  StrategySettings,
  StrategyProfile,
  StrategyType,
  PaperAccountStatus,
  PaperPosition,
  PaperTrade,
  ChargeSettings,
  AutoExitSettings,
  BacktestResult,
  AnalyticsSummary,
  SystemEventItem,
  MonthlyCalendarResponse,
  YearlyCalendarResponse,
  DailyDetailResponse,
  CustomRangeResponse,
  ChartCandlesResponse,
  ChartTradeMarker,
  InstrumentItem,
  BacktestRunItem,
  Timeframe,
  ComparisonAuditResponse,
  ChartMode,
  RangePreset,
  PCRResponse,
  PCRHistoryResponse,
} from '../types';

// Configure base URL dynamically from environment (Vercel production support)
// Normalizes base URL and guarantees exactly one single '/api' prefix without duplicates
const rawBase = (import.meta.env.VITE_API_BASE_URL || '').trim();
// Strip trailing slashes, then strip any trailing /api or /api/
const cleanOrigin = rawBase.replace(/\/+$/, '').replace(/\/api\/?$/, '');
export const API_BASE = cleanOrigin ? `${cleanOrigin}/api` : '/api';

export const getApiBaseUrl = () => API_BASE;

let currentAuthToken: string | null = typeof window !== 'undefined'
  ? localStorage.getItem('nextrade_auth_token')
  : null;

export const setAuthToken = (token: string | null) => {
  currentAuthToken = token;
  if (typeof window !== 'undefined') {
    if (token) {
      localStorage.setItem('nextrade_auth_token', token);
    } else {
      localStorage.removeItem('nextrade_auth_token');
    }
  }
};

export const getAuthToken = () => currentAuthToken;

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options?.headers as Record<string, string>),
  };

  if (currentAuthToken) {
    headers['Authorization'] = `Bearer ${currentAuthToken}`;
  }

  // Ensure path starts with '/' and does not duplicate '/api' if already present
  const cleanPath = url.startsWith('/') ? url : `/${url}`;
  const normalizedPath = cleanPath.startsWith('/api/')
    ? cleanPath.substring(4) // strip leading '/api' so it's not duplicated
    : cleanPath;

  const targetUrl = `${API_BASE}${normalizedPath}`;
  const res = await fetch(targetUrl, {
    ...options,
    headers,
  });
  if (!res.ok) {
    let errorMsg = `HTTP Error ${res.status}`;
    try {
      const err = await res.json();
      if (err.detail) errorMsg = err.detail;
    } catch {
      // ignore
    }
    throw new Error(errorMsg);
  }
  return res.json();
}

export const api = {
  // System Health
  getHealth: () =>
    fetchJson<{ status: string; app: string; version: string; mode: string; feed_mode?: string; timestamp?: string }>('/health'),

  // Market
  getMarketStatus: () => fetchJson<MarketStatus>('/market/status'),
  getCandles: (
    symbolOrOptions:
      | string
      | {
          symbol?: string;
          timeframe?: Timeframe;
          chartType?: string;
          mode?: ChartMode;
          dataSource?: string;
          rangePreset?: RangePreset;
          startDate?: string;
          endDate?: string;
          beforeTimestamp?: number;
          limit?: number;
          runId?: number;
        } = 'NIFTY 50',
    timeframeOrLimit: string | number = '1m',
    chartType: string = 'candlestick',
    limit: number = 300
  ) => {
    if (typeof symbolOrOptions === 'object') {
      const q = new URLSearchParams();
      if (symbolOrOptions.symbol) q.set('symbol', symbolOrOptions.symbol);
      if (symbolOrOptions.timeframe) q.set('timeframe', symbolOrOptions.timeframe);
      if (symbolOrOptions.chartType) q.set('chart_type', symbolOrOptions.chartType);
      if (symbolOrOptions.mode) q.set('mode', symbolOrOptions.mode);
      if (symbolOrOptions.dataSource) q.set('data_source', symbolOrOptions.dataSource);
      if (symbolOrOptions.rangePreset) q.set('range_preset', symbolOrOptions.rangePreset);
      if (symbolOrOptions.startDate) q.set('start_date', symbolOrOptions.startDate);
      if (symbolOrOptions.endDate) q.set('end_date', symbolOrOptions.endDate);
      if (symbolOrOptions.beforeTimestamp) q.set('before_timestamp', symbolOrOptions.beforeTimestamp.toString());
      if (symbolOrOptions.limit) q.set('limit', symbolOrOptions.limit.toString());
      if (symbolOrOptions.runId) q.set('run_id', symbolOrOptions.runId.toString());
      return fetchJson<ChartCandlesResponse>(`/market/candles?${q.toString()}`);
    }

    let tf = '1m';
    let ct = chartType;
    let lim = limit;
    if (typeof timeframeOrLimit === 'number') {
      lim = timeframeOrLimit;
      tf = '1m';
    } else {
      tf = timeframeOrLimit;
    }
    return fetchJson<ChartCandlesResponse>(
      `/market/candles?symbol=${encodeURIComponent(symbolOrOptions)}&timeframe=${encodeURIComponent(
        tf
      )}&chart_type=${encodeURIComponent(ct)}&limit=${lim}`
    );
  },
  getChartTradeMarkers: (params: {
    mode?: ChartMode;
    runId?: number;
    symbol?: string;
    startDate?: string;
    endDate?: string;
  }) => {
    const q = new URLSearchParams();
    if (params.mode) q.set('mode', params.mode);
    if (params.runId) q.set('run_id', params.runId.toString());
    if (params.symbol) q.set('symbol', params.symbol);
    if (params.startDate) q.set('start_date', params.startDate);
    if (params.endDate) q.set('end_date', params.endDate);
    return fetchJson<{ status: string; mode: string; markers: ChartTradeMarker[] }>(
      `/market/chart/trade-markers?${q.toString()}`
    );
  },
  getChartInstruments: (query: string = '') =>
    fetchJson<{ status: string; instruments: InstrumentItem[] }>(
      `/market/chart/instruments?query=${encodeURIComponent(query)}`
    ),
  getChartBacktestRuns: () =>
    fetchJson<{ status: string; runs: BacktestRunItem[] }>('/market/chart/backtest-runs'),

  getOptionChain: () => fetchJson<OptionChainResponse>('/market/option-chain'),
  getExpiries: () => fetchJson<{ expiries: string[] }>('/market/expiries'),
  selectContract: (strike?: number, expiry?: string) =>
    fetchJson<{ status: string; contract: any }>('/market/select-contract', {
      method: 'POST',
      body: JSON.stringify({ strike, expiry }),
    }),

  // Strategy Multi-Strategy Management
  getStrategyProfiles: () =>
    fetchJson<{ profiles: StrategyProfile[]; selected_strategy: StrategyType }>('/strategy/profiles'),
  selectStrategy: (strategy_id: StrategyType) =>
    fetchJson<{ status: string; selected_strategy: StrategyType; message: string }>('/strategy/select', {
      method: 'POST',
      body: JSON.stringify({ strategy_id }),
    }),
  configureStrategy: (strategy_id: StrategyType, config: Record<string, any>) =>
    fetchJson<{ status: string; profile: StrategyProfile }>('/strategy/configure', {
      method: 'POST',
      body: JSON.stringify({ strategy_id, config }),
    }),
  getStrategySettings: () => fetchJson<StrategySettings>('/strategy/settings'),
  getStrategyStatus: (strategy_id?: string) =>
    fetchJson<any>(strategy_id ? `/strategy/status?strategy_id=${strategy_id}` : '/strategy/status'),
  getSignals: (limit: number = 50) => fetchJson<any[]>(`/strategy/signals?limit=${limit}`),

  // Paper Trading
  getPaperStatus: () => fetchJson<PaperAccountStatus>('/paper/status'),
  getOpenPosition: () => fetchJson<{ position: PaperPosition | null }>('/paper/position'),
  closePosition: () =>
    fetchJson<{ status: string; trade: any }>('/paper/close', {
      method: 'POST',
    }),
  placeManualOrder: (lots: number = 1) =>
    fetchJson<{ status: string; position: PaperPosition }>('/paper/order', {
      method: 'POST',
      body: JSON.stringify({ action: 'BUY', lots }),
    }),
  getPaperTrades: (limit: number = 100) => fetchJson<PaperTrade[]>(`/paper/trades?limit=${limit}`),
  getPaperTradesCsvUrl: () => `${API_BASE}/paper/trades/csv`,
  getPaperOrders: (limit: number = 100) => fetchJson<any[]>(`/paper/orders?limit=${limit}`),
  getChargesSettings: () => fetchJson<ChargeSettings>('/paper/charges-settings'),
  updateChargesSettings: (entry_charge_per_order: number, exit_charge_per_order: number) =>
    fetchJson<ChargeSettings>('/paper/charges-settings', {
      method: 'POST',
      body: JSON.stringify({ entry_charge_per_order, exit_charge_per_order }),
    }),
  getAutoExitSettings: () => fetchJson<AutoExitSettings>('/paper/auto-exit-settings'),
  updateAutoExitSettings: (settings: {
    enabled: boolean;
    auto_close_time: string;
    apply_to_all_strategies: boolean;
    close_profitable: boolean;
    close_losing: boolean;
  }) =>
    fetchJson<AutoExitSettings>('/paper/auto-exit-settings', {
      method: 'POST',
      body: JSON.stringify(settings),
    }),
  triggerAutoExit: (force_now: boolean = true) =>
    fetchJson<{
      status: string;
      trade?: any;
      broker_status?: string;
      message?: string;
      awaiting_valid_data?: boolean;
      warning?: string | null;
    }>(`/paper/auto-exit-trigger?force_now=${force_now}`, {
      method: 'POST',
    }),
  recalculateCharges: (apply: boolean = false) =>
    fetchJson<{
      status: string;
      trades_count: number;
      total_pnl_diff: number;
      entry_charge_per_order: number;
      exit_charge_per_order: number;
      preview: any[];
    }>(`/paper/charges/recalculate?apply=${apply}`, {
      method: 'POST',
    }),
  resetPaperData: () =>
    fetchJson<{ status: string; message: string }>('/paper/reset', {
      method: 'POST',
    }),

  // Backtesting
  runBacktest: (params: {
    strategy_id?: StrategyType;
    timeframe?: string;
    instrument_symbol?: string;
    days?: number;
    start_date?: string;
    end_date?: string;
    data_source?: string;
    initial_capital?: number;
    lots?: number;
    lot_size?: number;
    target_points?: number;
    stop_points?: number;
    max_loss_per_trade?: number;
    use_risk_cap?: boolean;
    slippage_points?: number;
    execution_mode?: 'TRIGGER_PRICE' | 'REALISTIC';
    exit_on_ut_sell_signal?: boolean;
    same_candle_resolution?: string;
    use_synthetic_data?: boolean;
    seed?: number;
    ut_bot?: Record<string, any>;
    supertrend_ema?: Record<string, any>;
  }) =>
    fetchJson<BacktestResult>('/backtest/run', {
      method: 'POST',
      body: JSON.stringify(params),
    }),
  getBacktestRuns: () => fetchJson<BacktestRunItem[]>('/backtest/runs'),
  getBacktestRunDetails: (runId: number) => fetchJson<{ run: any; trades: any[] }>(`/backtest/runs/${runId}`),
  getBacktestCsvUrl: (runId: number) => `${API_BASE}/backtest/runs/${runId}/csv`,
  getComparisonAudit: (params?: {
    start_date?: string;
    end_date?: string;
    lots?: number;
    lot_size?: number;
    target_points?: number;
    stop_points?: number;
    slippage_points?: number;
    key_value?: number;
    atr_period?: number;
    use_heikin_ashi?: boolean;
  }) => {
    const q = new URLSearchParams();
    if (params?.start_date) q.set('start_date', params.start_date);
    if (params?.end_date) q.set('end_date', params.end_date);
    if (params?.lots) q.set('lots', params.lots.toString());
    if (params?.lot_size) q.set('lot_size', params.lot_size.toString());
    if (params?.target_points) q.set('target_points', params.target_points.toString());
    if (params?.stop_points) q.set('stop_points', params.stop_points.toString());
    if (params?.slippage_points) q.set('slippage_points', params.slippage_points.toString());
    if (params?.key_value) q.set('key_value', params.key_value.toString());
    if (params?.atr_period) q.set('atr_period', params.atr_period.toString());
    if (params?.use_heikin_ashi !== undefined) q.set('use_heikin_ashi', params.use_heikin_ashi.toString());
    const qs = q.toString();
    return fetchJson<ComparisonAuditResponse>(`/backtest/comparison-audit${qs ? `?${qs}` : ''}`);
  },
  getComparisonAuditCsvUrl: (params?: {
    start_date?: string;
    end_date?: string;
    lots?: number;
    lot_size?: number;
    target_points?: number;
    stop_points?: number;
    slippage_points?: number;
  }) => {
    const q = new URLSearchParams();
    if (params?.start_date) q.set('start_date', params.start_date);
    if (params?.end_date) q.set('end_date', params.end_date);
    if (params?.lots) q.set('lots', params.lots.toString());
    if (params?.lot_size) q.set('lot_size', params.lot_size.toString());
    if (params?.target_points) q.set('target_points', params.target_points.toString());
    if (params?.stop_points) q.set('stop_points', params.stop_points.toString());
    if (params?.slippage_points) q.set('slippage_points', params.slippage_points.toString());
    const qs = q.toString();
    return `${API_BASE}/backtest/comparison-audit/export-csv${qs ? `?${qs}` : ''}`;
  },

  // Analytics
  getAnalyticsSummary: (params?: {
    source?: string;
    run_id?: number;
    strategy_id?: string;
    execution_mode?: string;
    instrument_symbol?: string;
    start_date?: string;
    end_date?: string;
  }) => {
    const q = new URLSearchParams();
    if (params?.source) q.set('source', params.source);
    if (params?.run_id) q.set('run_id', params.run_id.toString());
    if (params?.strategy_id && params.strategy_id !== 'ALL') q.set('strategy_id', params.strategy_id);
    if (params?.execution_mode && params.execution_mode !== 'ALL') q.set('execution_mode', params.execution_mode);
    if (params?.instrument_symbol && params.instrument_symbol !== 'ALL') q.set('instrument_symbol', params.instrument_symbol);
    if (params?.start_date) q.set('start_date', params.start_date);
    if (params?.end_date) q.set('end_date', params.end_date);
    const qs = q.toString();
    return fetchJson<AnalyticsSummary>(`/analytics/summary${qs ? `?${qs}` : ''}`);
  },
  getAnalyticsBacktestRuns: () => fetchJson<BacktestRunItem[]>('/analytics/backtest-runs'),
  getSystemEvents: (limit: number = 50) => fetchJson<SystemEventItem[]>(`/analytics/events?limit=${limit}`),

  // Performance Calendar & Analytics
  getMonthlyCalendar: (params: {
    year: number;
    month: number;
    source?: string;
    strategy_id?: string;
    execution_mode?: string;
    run_id?: number;
  }) => {
    const q = new URLSearchParams();
    q.set('year', params.year.toString());
    q.set('month', params.month.toString());
    if (params.source) q.set('source', params.source);
    if (params.strategy_id) q.set('strategy_id', params.strategy_id);
    if (params.execution_mode) q.set('execution_mode', params.execution_mode);
    if (params.run_id) q.set('run_id', params.run_id.toString());
    return fetchJson<MonthlyCalendarResponse>(`/analytics/calendar/monthly?${q.toString()}`);
  },

  getYearlyCalendar: (params: {
    year: number;
    source?: string;
    strategy_id?: string;
    execution_mode?: string;
    run_id?: number;
  }) => {
    const q = new URLSearchParams();
    q.set('year', params.year.toString());
    if (params.source) q.set('source', params.source);
    if (params.strategy_id) q.set('strategy_id', params.strategy_id);
    if (params.execution_mode) q.set('execution_mode', params.execution_mode);
    if (params.run_id) q.set('run_id', params.run_id.toString());
    return fetchJson<YearlyCalendarResponse>(`/analytics/calendar/yearly?${q.toString()}`);
  },

  getDailyCalendarDetail: (params: {
    date: string;
    source?: string;
    strategy_id?: string;
    run_id?: number;
  }) => {
    const q = new URLSearchParams();
    q.set('date', params.date);
    if (params.source) q.set('source', params.source);
    if (params.strategy_id) q.set('strategy_id', params.strategy_id);
    if (params.run_id) q.set('run_id', params.run_id.toString());
    return fetchJson<DailyDetailResponse>(`/analytics/calendar/day?${q.toString()}`);
  },

  getCustomRangeCalendar: (params: {
    start_date: string;
    end_date: string;
    source?: string;
    strategy_id?: string;
    execution_mode?: string;
    instrument_symbol?: string;
    run_id?: number;
  }) => {
    const q = new URLSearchParams();
    q.set('start_date', params.start_date);
    q.set('end_date', params.end_date);
    if (params.source) q.set('source', params.source);
    if (params.strategy_id) q.set('strategy_id', params.strategy_id);
    if (params.execution_mode) q.set('execution_mode', params.execution_mode);
    if (params.instrument_symbol) q.set('instrument_symbol', params.instrument_symbol);
    if (params.run_id) q.set('run_id', params.run_id.toString());
    return fetchJson<CustomRangeResponse>(`/analytics/calendar/custom-range?${q.toString()}`);
  },

  getExportDailyTradesCsvUrl: (date: string, source = 'PAPER', strategy_id?: string, run_id?: number) => {
    const q = new URLSearchParams();
    q.set('date', date);
    if (source) q.set('source', source);
    if (strategy_id) q.set('strategy_id', strategy_id);
    if (run_id) q.set('run_id', run_id.toString());
    return `${API_BASE}/analytics/export/daily-trades-csv?${q.toString()}`;
  },

  getExportMonthlyCsvUrl: (year: number, month: number, source = 'PAPER', strategy_id?: string, run_id?: number) => {
    const q = new URLSearchParams();
    q.set('year', year.toString());
    q.set('month', month.toString());
    if (source) q.set('source', source);
    if (strategy_id) q.set('strategy_id', strategy_id);
    if (run_id) q.set('run_id', run_id.toString());
    return `${API_BASE}/analytics/export/monthly-csv?${q.toString()}`;
  },

  getExportYearlyCsvUrl: (year: number, source = 'PAPER', strategy_id?: string, run_id?: number) => {
    const q = new URLSearchParams();
    q.set('year', year.toString());
    if (source) q.set('source', source);
    if (strategy_id) q.set('strategy_id', strategy_id);
    if (run_id) q.set('run_id', run_id.toString());
    return `${API_BASE}/analytics/export/yearly-csv?${q.toString()}`;
  },

  getExportCustomCsvUrl: (start_date: string, end_date: string, source = 'PAPER', strategy_id?: string, run_id?: number) => {
    const q = new URLSearchParams();
    q.set('start_date', start_date);
    q.set('end_date', end_date);
    if (source) q.set('source', source);
    if (strategy_id) q.set('strategy_id', strategy_id);
    if (run_id) q.set('run_id', run_id.toString());
    return `${API_BASE}/analytics/export/custom-csv?${q.toString()}`;
  },

  // AI Micro-Scalper V1
  getAIMicroScalperStatus: async () => {
    return fetchJson<any>('/ai-micro-scalper/status');
  },

  getAIMicroScalperConfig: async () => {
    return fetchJson<any>('/ai-micro-scalper/config');
  },

  updateAIMicroScalperConfig: async (config: any) => {
    return fetchJson<any>('/ai-micro-scalper/config', {
      method: 'POST',
      body: JSON.stringify(config),
    });
  },

  controlAIMicroScalper: async (action: string) => {
    return fetchJson<any>(`/ai-micro-scalper/control?action=${action}`, {
      method: 'POST',
    });
  },

  emergencyCloseAIMicroScalper: async () => {
    return fetchJson<any>('/ai-micro-scalper/emergency-close', {
      method: 'POST',
    });
  },

  runAIMicroScalperBacktest: async (payload: any) => {
    return fetchJson<any>('/ai-micro-scalper/backtest', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  runAIMicroScalperAblation: async (payload: any) => {
    return fetchJson<any>('/ai-micro-scalper/ablation', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  // PCR & Options Market Analysis
  getPCRData: (params?: {
    underlying?: string;
    expiry?: string;
    strike_range?: number;
    force_refresh?: boolean;
    bullish_threshold?: number;
    bearish_threshold?: number;
  }) => {
    const q = new URLSearchParams();
    if (params?.underlying) q.set('underlying', params.underlying);
    if (params?.expiry) q.set('expiry', params.expiry);
    if (params?.strike_range !== undefined) q.set('strike_range', params.strike_range.toString());
    if (params?.force_refresh) q.set('force_refresh', 'true');
    if (params?.bullish_threshold) q.set('bullish_threshold', params.bullish_threshold.toString());
    if (params?.bearish_threshold) q.set('bearish_threshold', params.bearish_threshold.toString());
    const qs = q.toString();
    return fetchJson<PCRResponse>(`/market-data/pcr${qs ? `?${qs}` : ''}`);
  },

  getPCRExpiries: (underlying: string = 'NIFTY') =>
    fetchJson<{ status: string; underlying: string; expiries: string[] }>(
      `/market-data/pcr/expiries?underlying=${encodeURIComponent(underlying)}`
    ),

  getPCRHistory: (params?: { underlying?: string; trading_date?: string; strike_range?: number }) => {
    const q = new URLSearchParams();
    if (params?.underlying) q.set('underlying', params.underlying);
    if (params?.trading_date) q.set('trading_date', params.trading_date);
    if (params?.strike_range !== undefined) q.set('strike_range', params.strike_range.toString());
    const qs = q.toString();
    return fetchJson<PCRHistoryResponse>(`/market-data/pcr/history${qs ? `?${qs}` : ''}`);
  },

  getPCRDates: (underlying: string = 'NIFTY') =>
    fetchJson<{ status: string; underlying: string; dates: string[] }>(
      `/market-data/pcr/dates?underlying=${encodeURIComponent(underlying)}`
    ),

  // Authentication & Access Control (Strict 2-User Private Allowlist)
  authLogin: (data: { email: string; password: string }) =>
    fetchJson<{ access_token: string; token_type: string; user: any }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  authSignup: (data: { email: string; password: string; username?: string }) =>
    fetchJson<{ access_token: string; token_type: string; user: any }>('/auth/signup', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  authLogout: () =>
    fetchJson<{ status: string; message: string }>('/auth/logout', {
      method: 'POST',
    }),

  authGetMe: () =>
    fetchJson<{ user: { id: number; email: string; username: string; role: string } }>('/auth/me'),

  authForgotPassword: (data: { email: string }) =>
    fetchJson<{ status: string; message: string; reset_token?: string }>('/auth/forgot-password', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  authResetPassword: (data: { email: string; reset_token: string; new_password: string }) =>
    fetchJson<{ status: string; message: string }>('/auth/reset-password', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  authGetAuthorizedUsers: () =>
    fetchJson<{
      max_slots: number;
      slots_used: number;
      slots_available: number;
      users: Array<{ id: number; email: string; role: string; is_active: boolean; invited_by?: string; created_at?: string }>;
    }>('/auth/authorized-users'),

  authAddAuthorizedUser: (data: { email: string; role?: string }) =>
    fetchJson<any>('/auth/authorized-users', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  authRemoveAuthorizedUser: (email: string) =>
    fetchJson<{ status: string; message: string }>(`/auth/authorized-users/${encodeURIComponent(email)}`, {
      method: 'DELETE',
    }),
};
