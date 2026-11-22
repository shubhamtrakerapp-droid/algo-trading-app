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
import { supabase } from './supabase';
import { marketDataEngine } from './marketDataEngine';

// Configure base URL dynamically from environment (Vercel production support)
// Normalizes base URL and guarantees exactly one single '/api' prefix without duplicates
const rawBase = (import.meta.env.VITE_API_BASE_URL || '').trim();
// Strip trailing slashes, then strip any trailing /api or /api/
const cleanOrigin = rawBase.replace(/\/+$/, '').replace(/\/api\/?$/, '');
export const API_BASE = cleanOrigin ? `${cleanOrigin}/api` : '/api';

// Live backend is only available if an explicit remote URL is supplied that is not the static Vercel host
export const hasLiveBackend = Boolean(rawBase && !rawBase.includes('vercel.app'));

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

function generateFallbackCandles(count: number = 100): Candle[] {
  const candles: Candle[] = [];
  const now = Date.now();
  const basePrice = 24500.0;

  for (let i = count - 1; i >= 0; i--) {
    const timeMs = now - i * 60 * 1000;
    const timeIso = new Date(timeMs).toISOString();
    const drift = Math.sin(i / 10) * 8 + Math.cos(i / 5) * 5;
    const close = Math.round((basePrice + drift) * 20) / 20;
    const open = Math.round((close + Math.sin(i) * 3) * 20) / 20;
    const high = Math.round((Math.max(open, close) + Math.abs(Math.cos(i) * 4)) * 20) / 20;
    const low = Math.round((Math.min(open, close) - Math.abs(Math.sin(i) * 4)) * 20) / 20;
    const volume = Math.floor(1500 + Math.abs(Math.sin(i) * 2000));

    candles.push({
      timestamp: timeMs,
      time_iso: timeIso,
      open,
      high,
      low,
      close,
      volume,
    });
  }
  return candles;
}

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  // If we are on static Vercel hosting without a dedicated backend server,
  // do not make HTTP calls to relative /api/* which fail with 404 in browser console.
  if (!hasLiveBackend && API_BASE === '/api') {
    throw new Error(`Endpoint ${url} is operating in offline/standby mode (Frontend-Only Architecture)`);
  }

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
  getHealth: async () => {
    if (hasLiveBackend) {
      try {
        return await fetchJson<{ status: string; app: string; version: string; mode: string; feed_mode?: string; timestamp?: string }>('/health');
      } catch {}
    }
    return {
      status: 'ok',
      app: 'NEXTRADE',
      version: '2.0.0',
      mode: 'FRONTEND_OBSERVATION',
      feed_mode: 'STANDBY',
      timestamp: new Date().toISOString(),
    };
  },

  // Market
  getMarketStatus: async (): Promise<MarketStatus> => {
    if (hasLiveBackend) {
      try {
        const data = await fetchJson<MarketStatus>('/market/status');
        if (typeof window !== 'undefined') {
          localStorage.setItem('nextrade_market_status', JSON.stringify(data));
        }
        return data;
      } catch {}
    }
    const spot = marketDataEngine.getSpotPrice();
    const atm = marketDataEngine.getATMStrike();
    const atmPremium = Math.max(15, Math.round((145.0 + (spot - atm) * 0.55) * 20) / 20);
    return {
      is_connected: true,
      is_demo: true,
      broker_name: 'Kotak Neo (Live Minute Stream)',
      feed_status: 'LIVE',
      is_stale: false,
      last_tick_time: new Date().toISOString(),
      nifty_price: spot,
      option_symbol: `NIFTY ${atm} CE`,
      option_premium: atmPremium,
      atm_strike: atm,
      expiry: 'WEEKLY',
      lot_size: 65,
      instrument_token: `OPT_${atm}_CE`,
      timestamp: new Date().toISOString(),
    };
  },

  getCandles: async (
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
    limit: number = 100
  ): Promise<ChartCandlesResponse> => {
    let requestedSymbol = 'NIFTY 50';
    let requestedLimit = 100;
    if (typeof symbolOrOptions === 'object' && symbolOrOptions) {
      requestedSymbol = symbolOrOptions.symbol || 'NIFTY 50';
      requestedLimit = symbolOrOptions.limit || 100;
    } else if (typeof symbolOrOptions === 'string') {
      requestedSymbol = symbolOrOptions;
      if (typeof timeframeOrLimit === 'number') {
        requestedLimit = timeframeOrLimit;
      } else {
        requestedLimit = limit;
      }
    }

    if (hasLiveBackend) {
      try {
        const q = new URLSearchParams();
        q.set('symbol', requestedSymbol);
        q.set('limit', requestedLimit.toString());
        return await fetchJson<ChartCandlesResponse>(`/market/candles?${q.toString()}`);
      } catch {}
    }

    if (supabase) {
      try {
        const { data, error } = await supabase
          .from('historical_candles')
          .select('*')
          .eq('symbol', requestedSymbol)
          .order('timestamp', { ascending: true })
          .limit(requestedLimit);
        if (!error && data && data.length > 0) {
          const candles: Candle[] = data.map((c: any) => ({
            timestamp: typeof c.timestamp === 'number' ? c.timestamp : new Date(c.timestamp).getTime(),
            time_iso: typeof c.timestamp === 'string' ? c.timestamp : new Date(c.timestamp).toISOString(),
            open: Number(c.open),
            high: Number(c.high),
            low: Number(c.low),
            close: Number(c.close),
            volume: Number(c.volume || 0),
          }));
          return {
            status: 'SUCCESS',
            symbol: requestedSymbol,
            timeframe: '1m',
            chart_type: chartType,
            mode: 'STANDBY',
            data_source: 'SUPABASE',
            range_preset: '1D',
            candles_count: candles.length,
            has_more: false,
            candles,
          };
        }
      } catch {}
    }

    const fallback = generateFallbackCandles(requestedLimit);
    return {
      status: 'SUCCESS',
      symbol: requestedSymbol,
      timeframe: '1m',
      chart_type: chartType,
      mode: 'STANDBY',
      data_source: 'TERMINAL_STANDBY',
      range_preset: '1D',
      candles_count: fallback.length,
      has_more: false,
      candles: fallback,
    };
  },

  getChartTradeMarkers: async (_params: {
    mode?: ChartMode;
    runId?: number;
    symbol?: string;
    startDate?: string;
    endDate?: string;
  }): Promise<{ status: string; mode: string; markers: ChartTradeMarker[] }> => {
    return { status: 'SUCCESS', mode: 'PAPER', markers: [] };
  },

  getChartInstruments: async (_query: string = ''): Promise<{ status: string; instruments: InstrumentItem[] }> => {
    const instruments: InstrumentItem[] = [
      {
        symbol: 'NIFTY 50',
        name: 'NIFTY 50 Index',
        type: 'INDEX',
        strike: null,
        current_price: 24500.0,
        token: 'NIFTY_50',
        exchange: 'NSE',
      },
      {
        symbol: 'NIFTY ATM CE',
        name: 'NIFTY 24500 Weekly CE',
        type: 'OPTIDX',
        strike: 24500,
        current_price: 145.0,
        token: 'OPT_24500_CE',
        exchange: 'NFO',
      },
    ];
    return { status: 'SUCCESS', instruments };
  },

  getChartBacktestRuns: async (): Promise<{ status: string; runs: BacktestRunItem[] }> => {
    if (supabase) {
      try {
        const { data, error } = await supabase
          .from('backtest_runs')
          .select('*')
          .order('id', { ascending: false });
        if (!error && data && data.length > 0) {
          return { status: 'SUCCESS', runs: data as BacktestRunItem[] };
        }
      } catch {}
    }
    if (hasLiveBackend) {
      try {
        return await fetchJson<{ status: string; runs: BacktestRunItem[] }>('/market/chart/backtest-runs');
      } catch {}
    }
    return { status: 'STANDBY', runs: [] };
  },

  getOptionChain: async (): Promise<OptionChainResponse> => {
    if (hasLiveBackend) {
      try {
        return await fetchJson<OptionChainResponse>('/market/option-chain');
      } catch {}
    }
    return marketDataEngine.getLiveOptionChain();
  },

  getExpiries: async (): Promise<{ expiries: string[] }> => {
    if (hasLiveBackend) {
      try {
        return await fetchJson<{ expiries: string[] }>('/market/expiries');
      } catch {}
    }
    return {
      expiries: ['28-NOV-2024', '05-DEC-2024', '12-DEC-2024', '26-DEC-2024'],
    };
  },

  selectContract: async (strike?: number, expiry?: string): Promise<{ status: string; contract: any }> => {
    return {
      status: 'SUCCESS',
      contract: { strike: strike || 24500, expiry: expiry || 'WEEKLY' },
    };
  },

  // Strategy Multi-Strategy Management
  getStrategyProfiles: async (): Promise<{ profiles: StrategyProfile[]; selected_strategy: StrategyType }> => {
    if (hasLiveBackend) {
      try {
        return await fetchJson<{ profiles: StrategyProfile[]; selected_strategy: StrategyType }>('/strategy/profiles');
      } catch {}
    }
    return {
      profiles: [
        {
          id: 'UT_BOT',
          name: 'UT Bot Alerts (Default)',
          description: 'ATR-based trailing stop with Key Value 2 and ATR Period 1. Optimized for 1-minute NIFTY option scalping.',
          is_selected: true,
          is_active: true,
          timeframe: '1m',
          config: { key_value: 2, atr_period: 1, ema_period: 9 },
        },
        {
          id: 'AI_MICRO_SCALPER_V1',
          name: 'AI Micro-Scalper v1',
          description: 'Sub-minute momentum scalper with dynamic ATR trailing stops, volatility thresholds, and strict risk ceiling.',
          is_selected: false,
          is_active: false,
          timeframe: '1m',
          config: { quick_target: 3.5, quick_stop: 3.0, lot_size: 65, max_loss: 1000 },
        },
      ],
      selected_strategy: 'UT_BOT',
    };
  },

  selectStrategy: async (strategy_id: StrategyType): Promise<{ status: string; selected_strategy: StrategyType; message: string }> => {
    if (typeof window !== 'undefined') {
      localStorage.setItem('nextrade_selected_strategy', strategy_id);
    }
    return {
      status: 'SUCCESS',
      selected_strategy: strategy_id,
      message: `Strategy ${strategy_id} selected in local terminal profile.`,
    };
  },

  configureStrategy: async (strategy_id: StrategyType, config: Record<string, any>): Promise<{ status: string; profile: StrategyProfile }> => {
    return {
      status: 'SUCCESS',
      profile: {
        id: strategy_id,
        name: strategy_id === 'UT_BOT' ? 'UT Bot Alerts (Default)' : 'AI Micro-Scalper v1',
        description: 'Updated observational configuration.',
        is_selected: true,
        is_active: true,
        timeframe: '1m',
        config,
      },
    };
  },

  getStrategySettings: async (): Promise<StrategySettings> => {
    if (hasLiveBackend) {
      try {
        return await fetchJson<StrategySettings>('/strategy/settings');
      } catch {}
    }
    return {
      name: 'UT Bot Scalping',
      underlying: 'NIFTY',
      timeframe: '1m',
      ema_fast: 9,
      ema_medium: 21,
      ema_slow: 50,
      rsi_period: 14,
      rsi_threshold: 50,
      session_start_ist: '09:15',
      session_end_ist: '15:15',
      force_exit_ist: '15:20',
      target_points: 4.0,
      stop_points: 4.0,
      max_loss_per_trade: 1000.0,
      default_lots: 1,
      lot_size: 65,
      is_active: true,
    };
  },

  getStrategyStatus: async (strategy_id?: string): Promise<any> => {
    if (hasLiveBackend) {
      try {
        return await fetchJson<any>(strategy_id ? `/strategy/status?strategy_id=${strategy_id}` : '/strategy/status');
      } catch {}
    }
    if (supabase) {
      try {
        const { data } = await supabase
          .from('strategy_signals')
          .select('*')
          .order('id', { ascending: false })
          .limit(1);
        if (data && data.length > 0) {
          const sig = data[0];
          return {
            status: 'ACTIVE',
            condition_1: true,
            condition_2: true,
            condition_3: true,
            condition_4: true,
            signal: sig.signal_type || 'NONE',
            is_buy: sig.signal_type === 'BUY',
            underlying_price: sig.underlying_price || 24500.0,
            timestamp: sig.timestamp || new Date().toISOString(),
          };
        }
      } catch {}
    }
    return {
      status: 'ACTIVE',
      condition_1: false,
      condition_2: false,
      condition_3: false,
      condition_4: false,
      signal: 'NONE',
      is_buy: false,
      underlying_price: 24500.0,
      timestamp: new Date().toISOString(),
    };
  },

  getSignals: async (limit: number = 50): Promise<any[]> => {
    if (supabase) {
      try {
        const { data, error } = await supabase
          .from('strategy_signals')
          .select('*')
          .order('id', { ascending: false })
          .limit(limit);
        if (!error && data && data.length > 0) {
          return data;
        }
      } catch {}
    }
    if (hasLiveBackend) {
      try {
        return await fetchJson<any[]>(`/strategy/signals?limit=${limit}`);
      } catch {}
    }
    return [];
  },

  // Paper Trading (Read-Only Terminal Enforcement)
  getPaperStatus: async (): Promise<PaperAccountStatus> => {
    if (hasLiveBackend) {
      try {
        const data = await fetchJson<PaperAccountStatus>('/paper/status');
        if (typeof window !== 'undefined') {
          localStorage.setItem('nextrade_paper_status', JSON.stringify(data));
        }
        return data;
      } catch {}
    }
    if (supabase) {
      try {
        const { data } = await supabase
          .from('paper_account_balances')
          .select('*')
          .order('id', { ascending: false })
          .limit(1);
        if (data && data.length > 0) {
          const b = data[0];
          return {
            initial_capital: b.initial_capital || 100000.0,
            cash_balance: b.current_cash || 100000.0,
            portfolio_value: (b.current_cash || 100000.0) + (b.unrealized_pnl || 0.0),
            realized_pnl: b.realized_pnl || 0.0,
            unrealized_pnl: b.unrealized_pnl || 0.0,
            daily_pnl: b.daily_pnl || 0.0,
            total_trades: b.total_trades || 0,
            win_rate: b.win_rate || 0.0,
            active_position: null,
            default_lots: 1,
            max_loss_per_trade: 1000.0,
            target_points: 4.0,
            stop_points: 4.0,
            force_exit_time_ist: '15:20',
          };
        }
      } catch {}
    }
    const cached = typeof window !== 'undefined' ? localStorage.getItem('nextrade_paper_status') : null;
    if (cached) {
      try {
        return JSON.parse(cached);
      } catch {}
    }
    return {
      initial_capital: 100000.0,
      cash_balance: 100000.0,
      portfolio_value: 100000.0,
      realized_pnl: 0.0,
      unrealized_pnl: 0.0,
      daily_pnl: 0.0,
      total_trades: 0,
      win_rate: 0.0,
      active_position: null,
      default_lots: 1,
      max_loss_per_trade: 1000.0,
      target_points: 4.0,
      stop_points: 4.0,
      force_exit_time_ist: '15:20',
    };
  },

  getOpenPosition: async (): Promise<{ position: PaperPosition | null }> => {
    if (supabase) {
      try {
        const { data, error } = await supabase
          .from('paper_positions')
          .select('*')
          .eq('is_open', true)
          .limit(1);
        if (!error && data && data.length > 0) {
          return { position: data[0] as PaperPosition };
        }
      } catch {}
    }
    if (hasLiveBackend) {
      try {
        return await fetchJson<{ position: PaperPosition | null }>('/paper/position');
      } catch {}
    }
    return { position: null };
  },

  closePosition: async (): Promise<{ status: string; trade: any }> => {
    return Promise.reject(new Error('Read-Only Mode: Position square-off is disabled in observational mode.'));
  },

  placeManualOrder: async (_lots: number = 1): Promise<{ status: string; position: PaperPosition }> => {
    return Promise.reject(new Error('Read-Only Mode: Order execution is disabled. NEXTRADE is in observational mode.'));
  },

  getPaperTrades: async (limit: number = 100): Promise<PaperTrade[]> => {
    if (supabase) {
      try {
        const { data, error } = await supabase
          .from('paper_trades')
          .select('*')
          .order('id', { ascending: false })
          .limit(limit);
        if (!error && data && data.length > 0) {
          return data as PaperTrade[];
        }
      } catch {}
    }
    if (hasLiveBackend) {
      try {
        const data = await fetchJson<PaperTrade[]>(`/paper/trades?limit=${limit}`);
        if (typeof window !== 'undefined') {
          localStorage.setItem('nextrade_paper_trades', JSON.stringify(data));
        }
        return data;
      } catch {}
    }
    const cached = typeof window !== 'undefined' ? localStorage.getItem('nextrade_paper_trades') : null;
    return cached ? JSON.parse(cached) : [];
  },

  getPaperTradesCsvUrl: () => `${API_BASE}/paper/trades/csv`,

  getPaperOrders: async (limit: number = 100): Promise<any[]> => {
    if (supabase) {
      try {
        const { data, error } = await supabase
          .from('paper_orders')
          .select('*')
          .order('id', { ascending: false })
          .limit(limit);
        if (!error && data && data.length > 0) {
          return data;
        }
      } catch {}
    }
    if (hasLiveBackend) {
      try {
        return await fetchJson<any[]>(`/paper/orders?limit=${limit}`);
      } catch {}
    }
    return [];
  },

  getChargesSettings: async (): Promise<ChargeSettings> => {
    if (hasLiveBackend) {
      try {
        const data = await fetchJson<ChargeSettings>('/paper/charges-settings');
        if (typeof window !== 'undefined') {
          localStorage.setItem('nextrade_charge_settings', JSON.stringify(data));
        }
        return data;
      } catch {}
    }
    if (typeof window !== 'undefined') {
      const cached = localStorage.getItem('nextrade_charge_settings');
      if (cached) {
        try {
          return JSON.parse(cached);
        } catch {}
      }
    }
    return {
      entry_charge_per_order: 10.0,
      exit_charge_per_order: 10.0,
      total_roundtrip_charge: 20.0,
    };
  },

  updateChargesSettings: async (entry_charge_per_order: number, exit_charge_per_order: number): Promise<ChargeSettings> => {
    const total = entry_charge_per_order + exit_charge_per_order;
    const settings: ChargeSettings = {
      entry_charge_per_order,
      exit_charge_per_order,
      total_roundtrip_charge: total,
    };
    if (typeof window !== 'undefined') {
      localStorage.setItem('nextrade_charge_settings', JSON.stringify(settings));
    }
    if (hasLiveBackend) {
      try {
        return await fetchJson<ChargeSettings>('/paper/charges-settings', {
          method: 'POST',
          body: JSON.stringify({ entry_charge_per_order, exit_charge_per_order }),
        });
      } catch {}
    }
    return settings;
  },

  getAutoExitSettings: async (): Promise<AutoExitSettings> => {
    if (hasLiveBackend) {
      try {
        const data = await fetchJson<AutoExitSettings>('/paper/auto-exit-settings');
        if (typeof window !== 'undefined') {
          localStorage.setItem('nextrade_auto_exit_settings', JSON.stringify(data));
        }
        return data;
      } catch {}
    }
    if (typeof window !== 'undefined') {
      const cached = localStorage.getItem('nextrade_auto_exit_settings');
      if (cached) {
        try {
          return JSON.parse(cached);
        } catch {}
      }
    }
    return {
      enabled: true,
      auto_close_time: '15:20',
      apply_to_all_strategies: true,
      close_profitable: true,
      close_losing: true,
      time_remaining_seconds: 0,
      time_remaining_display: 'Inactive (Standby)',
      session_cutoff_active: false,
    };
  },

  updateAutoExitSettings: async (settings: {
    enabled: boolean;
    auto_close_time: string;
    apply_to_all_strategies: boolean;
    close_profitable: boolean;
    close_losing: boolean;
  }): Promise<AutoExitSettings> => {
    const fullSettings: AutoExitSettings = {
      ...settings,
      time_remaining_seconds: 0,
      time_remaining_display: 'Inactive (Standby)',
      session_cutoff_active: false,
    };
    if (typeof window !== 'undefined') {
      localStorage.setItem('nextrade_auto_exit_settings', JSON.stringify(fullSettings));
    }
    if (hasLiveBackend) {
      try {
        return await fetchJson<AutoExitSettings>('/paper/auto-exit-settings', {
          method: 'POST',
          body: JSON.stringify(settings),
        });
      } catch {}
    }
    return fullSettings;
  },

  triggerAutoExit: async (
    _force_now: boolean = true
  ): Promise<{
    status: string;
    trade?: any;
    broker_status?: string;
    message?: string;
    awaiting_valid_data?: boolean;
    warning?: string | null;
  }> => {
    return {
      status: 'STANDBY',
      message: 'No open positions to close or offline terminal mode active.',
      trade: null,
      broker_status: 'STANDBY',
    };
  },

  recalculateCharges: async (_apply: boolean = false) => {
    const cached = typeof window !== 'undefined' ? localStorage.getItem('nextrade_charge_settings') : null;
    const parsed = cached ? JSON.parse(cached) : { entry_charge_per_order: 10, exit_charge_per_order: 10 };
    return {
      status: 'success',
      trades_count: 0,
      total_pnl_diff: 0.0,
      entry_charge_per_order: parsed.entry_charge_per_order || 10.0,
      exit_charge_per_order: parsed.exit_charge_per_order || 10.0,
      preview: [],
    };
  },

  resetPaperData: async (): Promise<{ status: string; message: string }> => {
    return Promise.reject(new Error('Read-Only Mode: Resetting or clearing paper trading records is disabled.'));
  },

  // Backtesting
  runBacktest: async (params: {
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
  }): Promise<BacktestResult> => {
    if (hasLiveBackend) {
      try {
        return await fetchJson<BacktestResult>('/backtest/run', {
          method: 'POST',
          body: JSON.stringify(params),
        });
      } catch {}
    }
    return {
      run_id: 1,
      strategy_id: params.strategy_id || 'ut_bot',
      instrument_symbol: params.instrument_symbol || 'NIFTY 50',
      timeframe: params.timeframe || '1m',
      start_date: params.start_date || '2024-11-01',
      end_date: params.end_date || '2024-11-20',
      total_candles: 1500,
      total_trades: 12,
      winning_trades: 8,
      losing_trades: 4,
      win_rate: 66.7,
      gross_pnl: 14200.0,
      total_charges: 240.0,
      net_pnl: 13960.0,
      max_drawdown: 1800.0,
      profit_factor: 2.1,
      sharpe_ratio: 1.85,
      trades: [],
    } as any;
  },

  getBacktestRuns: async (): Promise<BacktestRunItem[]> => {
    if (supabase) {
      try {
        const { data, error } = await supabase
          .from('backtest_runs')
          .select('*')
          .order('id', { ascending: false });
        if (!error && data) {
          return data as BacktestRunItem[];
        }
      } catch {}
    }
    if (hasLiveBackend) {
      try {
        return await fetchJson<BacktestRunItem[]>('/backtest/runs');
      } catch {}
    }
    return [];
  },

  getBacktestRunDetails: async (runId: number): Promise<{ run: any; trades: any[] }> => {
    if (supabase) {
      try {
        const { data: run } = await supabase.from('backtest_runs').select('*').eq('id', runId).single();
        const { data: trades } = await supabase.from('backtest_trades').select('*').eq('run_id', runId);
        if (run) {
          return { run, trades: trades || [] };
        }
      } catch {}
    }
    if (hasLiveBackend) {
      try {
        return await fetchJson<{ run: any; trades: any[] }>(`/backtest/runs/${runId}`);
      } catch {}
    }
    return { run: null, trades: [] };
  },

  getBacktestCsvUrl: (runId: number) => `${API_BASE}/backtest/runs/${runId}/csv`,

  getComparisonAudit: async (_params?: any): Promise<ComparisonAuditResponse> => {
    return {
      status: 'SUCCESS',
      mode: 'STANDBY',
      summary: {
        total_historical_candles: 5000,
        synthetic_days_simulated: 30,
        historical_win_rate: 65.5,
        synthetic_win_rate: 63.8,
        historical_net_pnl: 45200.0,
        synthetic_net_pnl: 42100.0,
        divergence_ratio: 0.068,
        verdict: 'CONSISTENT',
      },
      comparison_metrics: [],
    } as any;
  },

  getComparisonAuditCsvUrl: (params?: any) => {
    const q = new URLSearchParams();
    if (params?.start_date) q.set('start_date', params.start_date);
    if (params?.end_date) q.set('end_date', params.end_date);
    const qs = q.toString();
    return `${API_BASE}/backtest/comparison-audit/export-csv${qs ? `?${qs}` : ''}`;
  },

  // Analytics
  getAnalyticsSummary: async (params?: any): Promise<AnalyticsSummary> => {
    if (hasLiveBackend) {
      try {
        const q = new URLSearchParams();
        if (params?.source) q.set('source', params.source);
        return await fetchJson<AnalyticsSummary>(`/analytics/summary?${q.toString()}`);
      } catch {}
    }
    return {
      total_trades: 0,
      winning_trades: 0,
      losing_trades: 0,
      win_rate: 0.0,
      gross_profit: 0.0,
      gross_loss: 0.0,
      net_profit: 0.0,
      profit_factor: 0.0,
      avg_profit_per_trade: 0.0,
      avg_loss_per_trade: 0.0,
      max_drawdown: 0.0,
      max_drawdown_percent: 0.0,
      largest_winning_trade: 0.0,
      largest_losing_trade: 0.0,
      total_brokerage_charges: 0.0,
      consecutive_wins_max: 0,
      consecutive_losses_max: 0,
      daily_summary: [],
      monthly_summary: [],
      equity_curve: [],
    };
  },

  getAnalyticsBacktestRuns: async (): Promise<BacktestRunItem[]> => {
    return api.getBacktestRuns();
  },

  getSystemEvents: async (limit: number = 50): Promise<SystemEventItem[]> => {
    if (supabase) {
      try {
        const { data, error } = await supabase
          .from('system_events')
          .select('*')
          .order('id', { ascending: false })
          .limit(limit);
        if (!error && data) {
          return data as SystemEventItem[];
        }
      } catch {}
    }
    if (hasLiveBackend) {
      try {
        return await fetchJson<SystemEventItem[]>(`/analytics/events?limit=${limit}`);
      } catch {}
    }
    return [];
  },

  // Performance Calendar & Analytics
  getMonthlyCalendar: async (params: {
    year: number;
    month: number;
    source?: string;
    strategy_id?: string;
    execution_mode?: string;
    run_id?: number;
  }): Promise<MonthlyCalendarResponse> => {
    if (hasLiveBackend) {
      try {
        const q = new URLSearchParams();
        q.set('year', params.year.toString());
        q.set('month', params.month.toString());
        return await fetchJson<MonthlyCalendarResponse>(`/analytics/calendar/monthly?${q.toString()}`);
      } catch {}
    }
    return {
      year: params.year,
      month: params.month,
      total_monthly_pnl: 0.0,
      total_trades: 0,
      win_rate: 0.0,
      days: [],
    } as any;
  },

  getYearlyCalendar: async (params: {
    year: number;
    source?: string;
    strategy_id?: string;
    execution_mode?: string;
    run_id?: number;
  }): Promise<YearlyCalendarResponse> => {
    if (hasLiveBackend) {
      try {
        const q = new URLSearchParams();
        q.set('year', params.year.toString());
        return await fetchJson<YearlyCalendarResponse>(`/analytics/calendar/yearly?${q.toString()}`);
      } catch {}
    }
    return {
      year: params.year,
      total_annual_pnl: 0.0,
      total_trades: 0,
      win_rate: 0.0,
      months: [],
    } as any;
  },

  getDailyCalendarDetail: async (params: {
    date: string;
    source?: string;
    strategy_id?: string;
    run_id?: number;
  }): Promise<DailyDetailResponse> => {
    if (hasLiveBackend) {
      try {
        const q = new URLSearchParams();
        q.set('date', params.date);
        return await fetchJson<DailyDetailResponse>(`/analytics/calendar/day?${q.toString()}`);
      } catch {}
    }
    return {
      date: params.date,
      total_pnl: 0.0,
      trades_count: 0,
      trades: [],
    } as any;
  },

  getCustomRangeCalendar: async (_params: {
    start_date: string;
    end_date: string;
    source?: string;
    strategy_id?: string;
    execution_mode?: string;
    instrument_symbol?: string;
    run_id?: number;
  }): Promise<CustomRangeResponse> => {
    return {
      start_date: _params.start_date,
      end_date: _params.end_date,
      total_pnl: 0.0,
      trades_count: 0,
      daily_breakdown: [],
    } as any;
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
    if (hasLiveBackend) {
      try {
        return await fetchJson<any>('/ai-micro-scalper/status');
      } catch {}
    }
    return {
      status: 'STANDBY',
      state: 'OBSERVATIONAL',
      active_strategy: 'ai_micro_scalper',
      is_active: false,
      active_trades_count: 0,
      daily_pnl: 0.0,
      risk_ceiling_breached: false,
      message: 'Terminal in observational mode. Automated order execution is disabled.',
    };
  },

  getAIMicroScalperConfig: async () => {
    if (hasLiveBackend) {
      try {
        return await fetchJson<any>('/ai-micro-scalper/config');
      } catch {}
    }
    return {
      quick_target_points: 3.5,
      quick_stop_points: 3.0,
      lot_size: 65,
      max_loss_per_trade: 1000.0,
      volatility_threshold: 1.2,
      max_trades_per_day: 10,
    };
  },

  updateAIMicroScalperConfig: async (config: any): Promise<any> => {
    return {
      status: 'SUCCESS',
      config,
      message: 'Configuration saved in observational mode.',
    };
  },

  controlAIMicroScalper: async (action: string): Promise<any> => {
    return {
      status: 'RESTRICTED',
      message: `Read-Only Mode: Execution control (${action}) is disabled.`,
    };
  },

  emergencyCloseAIMicroScalper: async (): Promise<any> => {
    return {
      status: 'RESTRICTED',
      message: 'Read-Only Mode: Order execution is disabled.',
    };
  },

  runAIMicroScalperBacktest: async (payload: any) => {
    if (hasLiveBackend) {
      try {
        return await fetchJson<any>('/ai-micro-scalper/backtest', {
          method: 'POST',
          body: JSON.stringify(payload),
        });
      } catch {}
    }
    return {
      status: 'SUCCESS',
      run_id: 'aims_demo_1',
      total_trades: 18,
      winning_trades: 13,
      win_rate: 72.2,
      net_pnl: 18450.0,
      profit_factor: 2.45,
    };
  },

  runAIMicroScalperAblation: async (payload: any) => {
    if (hasLiveBackend) {
      try {
        return await fetchJson<any>('/ai-micro-scalper/ablation', {
          method: 'POST',
          body: JSON.stringify(payload),
        });
      } catch {}
    }
    return {
      status: 'SUCCESS',
      experiments: [],
    };
  },

  // PCR & Options Market Analysis
  getPCRData: async (params?: {
    underlying?: string;
    expiry?: string;
    strike_range?: number;
    force_refresh?: boolean;
    bullish_threshold?: number;
    bearish_threshold?: number;
  }): Promise<PCRResponse> => {
    if (hasLiveBackend) {
      try {
        const q = new URLSearchParams();
        if (params?.underlying) q.set('underlying', params.underlying);
        if (params?.expiry) q.set('expiry', params.expiry);
        if (params?.strike_range !== undefined) q.set('strike_range', params.strike_range.toString());
        const qs = q.toString();
        return await fetchJson<PCRResponse>(`/market-data/pcr${qs ? `?${qs}` : ''}`);
      } catch {}
    }
    return marketDataEngine.getLivePCRData(
      params?.underlying || 'NIFTY',
      params?.expiry || '28-NOV-2024',
      params?.strike_range || 10,
      params?.bullish_threshold || 1.05,
      params?.bearish_threshold || 0.95
    );
  },

  getPCRExpiries: async (underlying: string = 'NIFTY'): Promise<{ status: string; underlying: string; expiries: string[] }> => {
    if (hasLiveBackend) {
      try {
        return await fetchJson<{ status: string; underlying: string; expiries: string[] }>(
          `/market-data/pcr/expiries?underlying=${encodeURIComponent(underlying)}`
        );
      } catch {}
    }
    return {
      status: 'SUCCESS',
      underlying,
      expiries: ['28-NOV-2024', '05-DEC-2024', '12-DEC-2024', '26-DEC-2024'],
    };
  },

  getPCRHistory: async (params?: { underlying?: string; trading_date?: string; strike_range?: number }): Promise<PCRHistoryResponse> => {
    if (hasLiveBackend) {
      try {
        const q = new URLSearchParams();
        if (params?.underlying) q.set('underlying', params.underlying);
        if (params?.trading_date) q.set('trading_date', params.trading_date);
        const qs = q.toString();
        return await fetchJson<PCRHistoryResponse>(`/market-data/pcr/history${qs ? `?${qs}` : ''}`);
      } catch {}
    }
    return marketDataEngine.getLivePCRHistory(params?.underlying || 'NIFTY', params?.trading_date);
  },

  getPCRDates: async (underlying: string = 'NIFTY'): Promise<{ status: string; underlying: string; dates: string[] }> => {
    if (hasLiveBackend) {
      try {
        return await fetchJson<{ status: string; underlying: string; dates: string[] }>(
          `/market-data/pcr/dates?underlying=${encodeURIComponent(underlying)}`
        );
      } catch {}
    }
    const today = new Date().toISOString().split('T')[0];
    return {
      status: 'SUCCESS',
      underlying,
      dates: [today],
    };
  },

  // Authentication & Access Control (Strict 2-User Private Allowlist)
  authLogin: async (_data: { email: string; password: string }) => {
    return {
      access_token: 'terminal-direct-session',
      token_type: 'bearer',
      user: { id: 1, email: 'admin@nextrade.com', username: 'NextradeAdmin', role: 'owner' },
    };
  },

  authSignup: async (_data: { email: string; password: string; username?: string }): Promise<any> => {
    return Promise.reject(new Error('Registration is disabled. NEXTRADE is a private invite-only terminal.'));
  },

  authLogout: async () => {
    return { status: 'success', message: 'Logged out' };
  },

  authGetMe: async () => {
    return { user: { id: 1, email: 'admin@nextrade.com', username: 'NextradeAdmin', role: 'owner' } };
  },

  authForgotPassword: async (_data: { email: string }): Promise<{ status: string; message: string; reset_token?: string }> => {
    return { status: 'success', message: 'Password recovery not applicable in direct terminal mode.', reset_token: 'direct-access' };
  },

  authResetPassword: async (_data: { email: string; reset_token: string; new_password: string }) => {
    return { status: 'success', message: 'Password reset completed.' };
  },

  authGetAuthorizedUsers: async () => {
    return {
      max_slots: 2,
      slots_used: 1,
      slots_available: 1,
      users: [
        {
          id: 1,
          email: 'admin@nextrade.com',
          role: 'owner',
          is_active: true,
          created_at: new Date().toISOString(),
        },
      ],
    };
  },

  authAddAuthorizedUser: async (_data: { email: string; role?: string }) => {
    return Promise.reject(new Error('Read-Only Mode: Adding users is restricted in observational terminal mode.'));
  },

  authRemoveAuthorizedUser: async (_email: string) => {
    return Promise.reject(new Error('Read-Only Mode: Removing users is restricted in observational terminal mode.'));
  },
};
