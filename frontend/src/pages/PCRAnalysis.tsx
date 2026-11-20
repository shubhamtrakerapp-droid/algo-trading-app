import React, { useEffect, useState, useRef, useMemo, useCallback } from 'react';
import {
  Scale,
  RefreshCw,
  TrendingUp,
  TrendingDown,
  Clock,
  ShieldCheck,
  AlertTriangle,
  Info,
  Sliders,
  ChevronDown,
  Layers,
  BarChart2,
  Calendar,
  CheckCircle2,
  Activity,
  ArrowUpRight,
  ArrowDownRight,
  XCircle,
  HelpCircle,
} from 'lucide-react';
import { api } from '../services/api';
import {
  PCRResponse,
  PCRStrikeData,
  PCRHistoryPoint,
  PCRSettings,
} from '../types';

const UNDERLYING_OPTIONS = [
  { id: 'NIFTY', label: 'NIFTY 50' },
  { id: 'BANKNIFTY', label: 'BANKNIFTY' },
  { id: 'FINNIFTY', label: 'FINNIFTY' },
];

const STRIKE_RANGE_OPTIONS = [
  { value: 5, label: '±5 strikes (11 levels)' },
  { value: 10, label: '±10 strikes (21 levels)' },
  { value: 15, label: '±15 strikes (31 levels)' },
  { value: 20, label: '±20 strikes (41 levels)' },
  { value: 25, label: '±25 strikes (51 levels)' },
  { value: 0, label: 'All available strikes' },
];

const DEFAULT_SETTINGS: PCRSettings = {
  underlying: 'NIFTY',
  strike_range: 10,
  refresh_interval_sec: 60,
  bullish_threshold: 1.05,
  bearish_threshold: 0.95,
  neutral_upper: 1.05,
  neutral_lower: 0.95,
  show_volume: true,
  show_oi_change_pct: true,
  show_strike_ratios: true,
};

export const PCRAnalysis: React.FC = () => {
  // Settings & Configuration
  const [settings, setSettings] = useState<PCRSettings>(() => {
    try {
      const saved = localStorage.getItem('nextrade_pcr_settings');
      return saved ? { ...DEFAULT_SETTINGS, ...JSON.parse(saved) } : DEFAULT_SETTINGS;
    } catch {
      return DEFAULT_SETTINGS;
    }
  });

  const [selectedUnderlying, setSelectedUnderlying] = useState<string>(settings.underlying);
  const [selectedExpiry, setSelectedExpiry] = useState<string>('');
  const [availableExpiries, setAvailableExpiries] = useState<string[]>([]);
  const [selectedRange, setSelectedRange] = useState<number>(settings.strike_range);

  // Active view tab
  const [activeTab, setActiveTab] = useState<'chain' | 'chart' | 'levels' | 'settings'>('chain');

  // Live Data & Loading
  const [data, setData] = useState<PCRResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Countdown Timer
  const [countdown, setCountdown] = useState<number>(settings.refresh_interval_sec);
  const isFetchingRef = useRef<boolean>(false);

  // Historical Snapshot Chart State
  const [historyPoints, setHistoryPoints] = useState<PCRHistoryPoint[]>([]);
  const [availableDates, setAvailableDates] = useState<string[]>([]);
  const [selectedDate, setSelectedDate] = useState<string>('');
  const [loadingHistory, setLoadingHistory] = useState<boolean>(false);
  const [chartHoverPoint, setChartHoverPoint] = useState<PCRHistoryPoint | null>(null);

  // Save settings helper
  const updateSettings = (partial: Partial<PCRSettings>) => {
    setSettings((prev) => {
      const next = { ...prev, ...partial };
      localStorage.setItem('nextrade_pcr_settings', JSON.stringify(next));
      return next;
    });
  };

  // Format numbers to Indian numbering system (Lakhs / Crores) or short format
  const formatNumber = (num: number | null | undefined): string => {
    if (num === null || num === undefined) return 'N/A';
    const abs = Math.abs(num);
    const sign = num < 0 ? '-' : '';
    if (abs >= 10000000) {
      return `${sign}${(abs / 10000000).toFixed(2)} Cr`;
    }
    if (abs >= 100000) {
      return `${sign}${(abs / 100000).toFixed(2)} L`;
    }
    if (abs >= 1000) {
      return `${sign}${(abs / 1000).toFixed(1)} k`;
    }
    return `${sign}${abs.toLocaleString()}`;
  };

  // 1. Fetch available expiries when underlying changes
  useEffect(() => {
    let mounted = true;
    const fetchExpiries = async () => {
      try {
        const res = await api.getPCRExpiries(selectedUnderlying);
        if (mounted && res && res.expiries && res.expiries.length > 0) {
          setAvailableExpiries(res.expiries);
          if (!selectedExpiry || !res.expiries.includes(selectedExpiry)) {
            setSelectedExpiry(res.expiries[0]);
          }
        }
      } catch (err: any) {
        console.error('Failed to fetch expiries:', err);
      }
    };
    fetchExpiries();
    return () => {
      mounted = false;
    };
  }, [selectedUnderlying]);

  // 2. Fetch PCR Data
  const loadPCRData = useCallback(
    async (force = false) => {
      if (isFetchingRef.current) return;
      isFetchingRef.current = true;
      if (!data) setIsLoading(true);
      else setIsRefreshing(true);
      setErrorMsg(null);

      try {
        const res = await api.getPCRData({
          underlying: selectedUnderlying,
          expiry: selectedExpiry || undefined,
          strike_range: selectedRange,
          force_refresh: force,
          bullish_threshold: settings.bullish_threshold,
          bearish_threshold: settings.bearish_threshold,
        });

        if (res.status === 'SUCCESS') {
          setData(res);
          if (!selectedExpiry && res.expiry) {
            setSelectedExpiry(res.expiry);
          }
          setCountdown(settings.refresh_interval_sec);
        } else {
          setErrorMsg(res.message || 'Error loading option chain data.');
        }
      } catch (err: any) {
        setErrorMsg(err.message || 'Failed to connect to PCR service.');
      } finally {
        setIsLoading(false);
        setIsRefreshing(false);
        isFetchingRef.current = false;
      }
    },
    [selectedUnderlying, selectedExpiry, selectedRange, settings.bullish_threshold, settings.bearish_threshold, settings.refresh_interval_sec]
  );

  // Trigger load on filter change
  useEffect(() => {
    loadPCRData(false);
  }, [loadPCRData]);

  // 3. 60-Second Auto Refresh Timer
  useEffect(() => {
    const timer = setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) {
          loadPCRData(false);
          return settings.refresh_interval_sec;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [loadPCRData, settings.refresh_interval_sec]);

  // 4. Fetch Available Dates for Historical PCR Chart
  useEffect(() => {
    let mounted = true;
    const fetchDates = async () => {
      try {
        const res = await api.getPCRDates(selectedUnderlying);
        if (mounted && res && res.dates) {
          setAvailableDates(res.dates);
          if (!selectedDate && res.dates.length > 0) {
            setSelectedDate(res.dates[0]);
          }
        }
      } catch (e) {
        console.error('Failed to load PCR dates:', e);
      }
    };
    fetchDates();
    return () => {
      mounted = false;
    };
  }, [selectedUnderlying]);

  // 5. Fetch Historical Snapshots for the selected date
  const loadHistory = useCallback(async () => {
    setLoadingHistory(true);
    try {
      const res = await api.getPCRHistory({
        underlying: selectedUnderlying,
        trading_date: selectedDate || undefined,
        strike_range: selectedRange,
      });
      if (res && res.history) {
        setHistoryPoints(res.history);
      }
    } catch (e) {
      console.error('Failed to load PCR history:', e);
    } finally {
      setLoadingHistory(false);
    }
  }, [selectedUnderlying, selectedDate, selectedRange]);

  useEffect(() => {
    if (activeTab === 'chart') {
      loadHistory();
    }
  }, [activeTab, loadHistory]);

  // Calculate highest OI for visual progress bar scale
  const maxStrikeOI = useMemo(() => {
    if (!data || !data.strikes) return 1;
    let m = 1;
    for (const s of data.strikes) {
      if (s.ce_oi > m) m = s.ce_oi;
      if (s.pe_oi > m) m = s.pe_oi;
    }
    return m;
  }, [data]);

  // Data status badge helper
  const renderStatusBadge = () => {
    const st = data?.data_status || 'UPDATING';
    if (st === 'FRESH') {
      return (
        <span className="flex items-center space-x-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-950/80 text-emerald-400 border border-emerald-700/60 shadow-sm shadow-emerald-950">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          <span>LIVE &bull; FRESH</span>
        </span>
      );
    }
    if (st === 'MARKET CLOSED') {
      return (
        <span className="flex items-center space-x-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-blue-950/80 text-blue-300 border border-blue-700/60">
          <Clock className="w-3.5 h-3.5 text-blue-400" />
          <span>MARKET CLOSED</span>
        </span>
      );
    }
    if (st === 'STALE') {
      return (
        <span className="flex items-center space-x-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-950/80 text-amber-400 border border-amber-700/60">
          <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
          <span>STALE DATA</span>
        </span>
      );
    }
    return (
      <span className="flex items-center space-x-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-950/80 text-rose-400 border border-rose-700/60">
        <XCircle className="w-3.5 h-3.5 text-rose-400" />
        <span>{st}</span>
      </span>
    );
  };

  // Sentiment color helper
  const getSentimentColor = (label: string) => {
    const l = (label || '').toUpperCase();
    if (l === 'BULLISH' || l.includes('BULLISH')) {
      return {
        bg: 'bg-emerald-950/40',
        border: 'border-emerald-600/50',
        text: 'text-emerald-400',
        badge: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
      };
    }
    if (l === 'BEARISH' || l.includes('BEARISH')) {
      return {
        bg: 'bg-rose-950/40',
        border: 'border-rose-600/50',
        text: 'text-rose-400',
        badge: 'bg-rose-500/20 text-rose-300 border-rose-500/40',
      };
    }
    if (l === 'CONFLICTING') {
      return {
        bg: 'bg-amber-950/40',
        border: 'border-amber-600/50',
        text: 'text-amber-400',
        badge: 'bg-amber-500/20 text-amber-300 border-amber-500/40',
      };
    }
    return {
      bg: 'bg-slate-900/40',
      border: 'border-slate-700/50',
      text: 'text-slate-300',
      badge: 'bg-slate-800 text-slate-300 border-slate-700',
    };
  };

  return (
    <div className="flex-1 flex flex-col min-w-0 bg-background text-gray-100 overflow-y-auto">
      {/* 1. Header Bar */}
      <div className="border-b border-border bg-surface/70 backdrop-blur-md px-4 sm:px-6 py-4 flex flex-col md:flex-row md:items-center justify-between gap-4 sticky top-0 z-30 shadow-md">
        <div>
          <div className="flex items-center space-x-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-500/20 to-blue-600/20 border border-indigo-500/40 flex items-center justify-center text-indigo-400 shadow-inner">
              <Scale className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-lg sm:text-xl font-bold tracking-tight text-white flex items-center space-x-2">
                <span>Options Market Intelligence</span>
                <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-400 border border-indigo-500/30">
                  PCR &bull; VWAP &bull; OI
                </span>
              </h1>
              <p className="text-xs text-gray-400 font-mono">
                Live Put-Call Ratio, Open Interest Distribution, Volume &amp; Market Sentiment
              </p>
            </div>
          </div>
        </div>

        {/* Live Status and Refresh Controls */}
        <div className="flex flex-wrap items-center gap-2.5 sm:gap-3 text-xs">
          {renderStatusBadge()}

          {/* Last Updated IST */}
          <div className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-surface border border-border font-mono text-gray-300">
            <Clock className="w-3.5 h-3.5 text-gray-400" />
            <span>IST: {data?.timestamp_ist ? data.timestamp_ist.split(' ')[1] : '--:--:--'}</span>
          </div>

          {/* Auto-refresh Countdown */}
          <div
            className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-surface border border-border font-mono text-gray-300"
            title="Auto-refresh countdown"
          >
            <Activity className="w-3.5 h-3.5 text-blue-400 animate-pulse" />
            <span>Next in {countdown}s</span>
          </div>

          {/* Manual Refresh Button */}
          <button
            onClick={() => loadPCRData(true)}
            disabled={isRefreshing || isLoading}
            className={`px-3 py-1.5 rounded-lg bg-blue-600/20 hover:bg-blue-600/30 border border-blue-500/50 text-blue-300 flex items-center space-x-1.5 font-semibold transition active:scale-95 ${
              isRefreshing || isLoading ? 'opacity-60 cursor-not-allowed' : ''
            }`}
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing || isLoading ? 'animate-spin' : ''}`} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* 2. Top Control Panel (Underlying, Expiry, Strike Range, Info) */}
      <div className="p-4 sm:p-6 pb-2">
        <div className="bg-surface/80 rounded-2xl border border-border/80 p-4 shadow-lg backdrop-blur flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div className="flex flex-wrap items-center gap-3">
            {/* A. Underlying Selector */}
            <div className="flex flex-col space-y-1">
              <label className="text-[11px] font-mono uppercase text-gray-400 tracking-wider">Underlying</label>
              <div className="relative">
                <select
                  value={selectedUnderlying}
                  onChange={(e) => {
                    setSelectedUnderlying(e.target.value);
                    updateSettings({ underlying: e.target.value });
                  }}
                  className="bg-background border border-border hover:border-gray-600 rounded-xl px-3 py-1.5 pr-8 text-sm font-semibold text-white focus:outline-none focus:border-blue-500 transition cursor-pointer appearance-none"
                >
                  {UNDERLYING_OPTIONS.map((opt) => (
                    <option key={opt.id} value={opt.id} className="bg-gray-900 text-white">
                      {opt.label}
                    </option>
                  ))}
                </select>
                <ChevronDown className="w-4 h-4 text-gray-400 absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
              </div>
            </div>

            {/* B. Expiry Selector */}
            <div className="flex flex-col space-y-1">
              <label className="text-[11px] font-mono uppercase text-gray-400 tracking-wider">Expiry</label>
              <div className="relative">
                <select
                  value={selectedExpiry}
                  onChange={(e) => setSelectedExpiry(e.target.value)}
                  className="bg-background border border-border hover:border-gray-600 rounded-xl px-3 py-1.5 pr-8 text-sm font-semibold text-white focus:outline-none focus:border-blue-500 transition cursor-pointer appearance-none"
                >
                  {availableExpiries.length === 0 ? (
                    <option value="">Loading expiries...</option>
                  ) : (
                    availableExpiries.map((exp) => (
                      <option key={exp} value={exp} className="bg-gray-900 text-white">
                        {exp}
                      </option>
                    ))
                  )}
                </select>
                <ChevronDown className="w-4 h-4 text-gray-400 absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
              </div>
            </div>

            {/* C. Strike Range Selector (AutoTrender Experience) */}
            <div className="flex flex-col space-y-1">
              <label className="text-[11px] font-mono uppercase text-gray-400 tracking-wider">Strike Range</label>
              <div className="relative">
                <select
                  value={selectedRange}
                  onChange={(e) => {
                    const val = Number(e.target.value);
                    setSelectedRange(val);
                    updateSettings({ strike_range: val });
                  }}
                  className="bg-background border border-blue-500/40 hover:border-blue-500 rounded-xl px-3 py-1.5 pr-8 text-sm font-semibold text-blue-300 focus:outline-none transition cursor-pointer appearance-none shadow-sm"
                >
                  {STRIKE_RANGE_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value} className="bg-gray-900 text-white">
                      {opt.label}
                    </option>
                  ))}
                </select>
                <ChevronDown className="w-4 h-4 text-blue-400 absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
              </div>
            </div>
          </div>

          {/* Range Summary Pill & Warnings */}
          <div className="flex flex-col sm:flex-row items-start sm:items-center gap-2 text-xs font-mono">
            {data?.range_info && (
              <div className="px-3.5 py-1.5 rounded-xl bg-background/90 border border-border/80 text-gray-300 flex items-center space-x-2">
                <span className="text-blue-400 font-bold">ATM: {data.range_info.atm_strike.toLocaleString()}</span>
                <span className="text-gray-500">&bull;</span>
                <span>Range: {selectedRange === 0 ? 'ALL' : `±${selectedRange}`}</span>
                <span className="text-gray-500">&bull;</span>
                <span className="text-emerald-400 font-semibold">{data.range_info.selected_levels} strikes</span>
              </div>
            )}

            {data?.warning && (
              <div className="px-3 py-1.5 rounded-xl bg-amber-950/40 border border-amber-600/40 text-amber-300 text-xs flex items-center space-x-1.5">
                <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
                <span className="truncate max-w-xs">{data.warning}</span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 3. Main PCR Summary Cards (6 Cards) */}
      <div className="p-4 sm:p-6 py-2">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3.5">
          {/* Card 1: OI PCR */}
          {(() => {
            const card = data?.cards.oi_pcr;
            const theme = getSentimentColor(card?.sentiment_label || '');
            return (
              <div className={`p-4 rounded-2xl border ${theme.border} ${theme.bg} shadow-md backdrop-blur flex flex-col justify-between transition-all hover:border-gray-500/50`}>
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[11px] font-mono uppercase text-gray-400">OI PCR (Put/Call)</span>
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${theme.badge}`}>
                      {card?.sentiment_label || 'NEUTRAL'}
                    </span>
                  </div>
                  <div className="flex items-baseline space-x-2 mt-1">
                    <span className={`text-2xl sm:text-3xl font-extrabold font-mono tracking-tight ${theme.text}`}>
                      {card?.value !== null && card?.value !== undefined ? card.value.toFixed(2) : 'N/A'}
                    </span>
                    {card?.delta !== null && card?.delta !== undefined && (
                      <span className={`text-xs font-mono font-semibold flex items-center ${card.delta >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {card.delta >= 0 ? '+' : ''}{card.delta.toFixed(2)}
                      </span>
                    )}
                  </div>
                </div>

                <div className="border-t border-border/40 pt-2.5 mt-3 text-[11px] font-mono flex flex-col space-y-1 text-gray-400">
                  <div className="flex justify-between">
                    <span>Put OI:</span>
                    <span className="text-emerald-400 font-semibold">{formatNumber(card?.total_put_oi)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Call OI:</span>
                    <span className="text-rose-400 font-semibold">{formatNumber(card?.total_call_oi)}</span>
                  </div>
                </div>
              </div>
            );
          })()}

          {/* Card 2: Volume PCR */}
          {(() => {
            const card = data?.cards.volume_pcr;
            const theme = getSentimentColor(card?.sentiment_label || '');
            return (
              <div className={`p-4 rounded-2xl border ${theme.border} ${theme.bg} shadow-md backdrop-blur flex flex-col justify-between transition-all hover:border-gray-500/50`}>
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[11px] font-mono uppercase text-gray-400">Volume PCR</span>
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${theme.badge}`}>
                      {card?.sentiment_label || 'NEUTRAL'}
                    </span>
                  </div>
                  <div className="flex items-baseline space-x-2 mt-1">
                    <span className={`text-2xl sm:text-3xl font-extrabold font-mono tracking-tight ${theme.text}`}>
                      {card?.value !== null && card?.value !== undefined ? card.value.toFixed(2) : 'N/A'}
                    </span>
                    {card?.delta !== null && card?.delta !== undefined && (
                      <span className={`text-xs font-mono font-semibold flex items-center ${card.delta >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {card.delta >= 0 ? '+' : ''}{card.delta.toFixed(2)}
                      </span>
                    )}
                  </div>
                </div>

                <div className="border-t border-border/40 pt-2.5 mt-3 text-[11px] font-mono flex flex-col space-y-1 text-gray-400">
                  <div className="flex justify-between">
                    <span>Put Vol:</span>
                    <span className="text-emerald-400 font-semibold">{formatNumber(card?.total_put_volume)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Call Vol:</span>
                    <span className="text-rose-400 font-semibold">{formatNumber(card?.total_call_volume)}</span>
                  </div>
                </div>
              </div>
            );
          })()}

          {/* Card 3: Total Call OI */}
          {(() => {
            const card = data?.cards.call_oi;
            return (
              <div className="p-4 rounded-2xl border border-rose-900/40 bg-surface/70 shadow-md backdrop-blur flex flex-col justify-between hover:border-rose-700/60 transition-all">
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[11px] font-mono uppercase text-gray-400">Total Call OI (CE)</span>
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-rose-950 text-rose-300 border border-rose-800">
                      RESISTANCE
                    </span>
                  </div>
                  <div className="text-2xl sm:text-3xl font-extrabold font-mono tracking-tight text-white mt-1">
                    {formatNumber(card?.total_oi)}
                  </div>
                  <div className="flex items-center space-x-1.5 mt-1 text-xs font-mono">
                    <span className="text-gray-400">Chg:</span>
                    <span className={`font-semibold ${card && card.oi_change >= 0 ? 'text-rose-400' : 'text-emerald-400'}`}>
                      {card && card.oi_change >= 0 ? '+' : ''}{formatNumber(card?.oi_change)} ({card?.oi_change_pct}%)
                    </span>
                  </div>
                </div>

                <div className="border-t border-border/40 pt-2.5 mt-3 text-[11px] font-mono flex flex-col space-y-1 text-gray-400">
                  <div className="flex justify-between">
                    <span>Max Call OI:</span>
                    <span className="text-rose-400 font-semibold">{card?.highest_oi_strike || 0}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Max CE Writing:</span>
                    <span className="text-amber-400 font-semibold">{card?.highest_oi_change_strike || 0}</span>
                  </div>
                </div>
              </div>
            );
          })()}

          {/* Card 4: Total Put OI */}
          {(() => {
            const card = data?.cards.put_oi;
            return (
              <div className="p-4 rounded-2xl border border-emerald-900/40 bg-surface/70 shadow-md backdrop-blur flex flex-col justify-between hover:border-emerald-700/60 transition-all">
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[11px] font-mono uppercase text-gray-400">Total Put OI (PE)</span>
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-emerald-950 text-emerald-300 border border-emerald-800">
                      SUPPORT
                    </span>
                  </div>
                  <div className="text-2xl sm:text-3xl font-extrabold font-mono tracking-tight text-white mt-1">
                    {formatNumber(card?.total_oi)}
                  </div>
                  <div className="flex items-center space-x-1.5 mt-1 text-xs font-mono">
                    <span className="text-gray-400">Chg:</span>
                    <span className={`font-semibold ${card && card.oi_change >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {card && card.oi_change >= 0 ? '+' : ''}{formatNumber(card?.oi_change)} ({card?.oi_change_pct}%)
                    </span>
                  </div>
                </div>

                <div className="border-t border-border/40 pt-2.5 mt-3 text-[11px] font-mono flex flex-col space-y-1 text-gray-400">
                  <div className="flex justify-between">
                    <span>Max Put OI:</span>
                    <span className="text-emerald-400 font-semibold">{card?.highest_oi_strike || 0}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Max PE Writing:</span>
                    <span className="text-emerald-400 font-semibold">{card?.highest_oi_change_strike || 0}</span>
                  </div>
                </div>
              </div>
            );
          })()}

          {/* Card 5: Underlying Price & VWAP */}
          {(() => {
            const card = data?.cards.price_vwap;
            const isAboveVWAP = card?.spot_vwap_diff && card.spot_vwap_diff >= 0;
            return (
              <div className="p-4 rounded-2xl border border-border/80 bg-surface/70 shadow-md backdrop-blur flex flex-col justify-between hover:border-gray-500 transition-all">
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[11px] font-mono uppercase text-gray-400">Spot &amp; VWAP</span>
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-surface border border-border text-gray-400">
                      {card?.futures_symbol ? 'FUT VWAP' : 'VWAP'}
                    </span>
                  </div>
                  <div className="flex items-baseline space-x-2 mt-1">
                    <span className="text-2xl sm:text-3xl font-extrabold font-mono tracking-tight text-white">
                      {card?.spot_price ? card.spot_price.toLocaleString(undefined, { minimumFractionDigits: 1 }) : '--'}
                    </span>
                    <span className={`text-xs font-mono font-semibold flex items-center ${card && card.spot_change >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {card && card.spot_change >= 0 ? '+' : ''}{card?.spot_change} ({card?.spot_change_pct}%)
                    </span>
                  </div>
                </div>

                <div className="border-t border-border/40 pt-2.5 mt-3 text-[11px] font-mono flex flex-col space-y-1 text-gray-400">
                  <div className="flex justify-between">
                    <span>Futures VWAP:</span>
                    <span className="text-blue-300 font-semibold">
                      {card?.futures_vwap ? card.futures_vwap.toLocaleString() : 'N/A'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span>Diff vs VWAP:</span>
                    <span className={`font-semibold ${isAboveVWAP ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {card?.spot_vwap_diff ? `${isAboveVWAP ? '+' : ''}${card.spot_vwap_diff} (${card.spot_vwap_diff_pct}%)` : 'N/A'}
                    </span>
                  </div>
                </div>
              </div>
            );
          })()}

          {/* Card 6: Market Bias & Combined Sentiment */}
          {(() => {
            const card = data?.cards.market_bias;
            const theme = getSentimentColor(card?.bias || '');
            return (
              <div className={`p-4 rounded-2xl border ${theme.border} ${theme.bg} shadow-md backdrop-blur flex flex-col justify-between hover:border-gray-500/50 transition-all`}>
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[11px] font-mono uppercase text-gray-400">Market Bias</span>
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${theme.badge}`}>
                      {card?.bias || 'NEUTRAL'}
                    </span>
                  </div>
                  <div className={`text-lg sm:text-xl font-bold tracking-tight mt-1 line-clamp-1 ${theme.text}`}>
                    {card?.headline || 'Neutral / Balanced'}
                  </div>
                  <p className="text-[11px] text-gray-300 mt-1 line-clamp-2 leading-tight">
                    {card?.explanation || 'Open Interest and volume evenly matched across strikes.'}
                  </p>
                </div>

                <div className="border-t border-border/40 pt-2 mt-2 text-[10px] font-mono flex justify-between text-gray-400">
                  <span>Score: <b className={theme.text}>{card?.score ? (card.score > 0 ? `+${card.score}` : card.score) : 0}</b></span>
                  <span>OI: <b className="text-white">{card?.breakdown.oi_pcr_bias}</b></span>
                  <span>VWAP: <b className="text-white">{card?.breakdown.price_vwap_bias}</b></span>
                </div>
              </div>
            );
          })()}
        </div>
      </div>

      {/* 4. Tab Navigation Bar (Chain Table, Intraday Chart, S&R Levels, Settings) */}
      <div className="px-4 sm:px-6 pt-3 pb-1 border-b border-border/60 flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <button
            onClick={() => setActiveTab('chain')}
            className={`px-4 py-2 rounded-xl text-xs font-semibold flex items-center space-x-2 transition ${
              activeTab === 'chain'
                ? 'bg-blue-600/20 text-blue-400 border border-blue-500/40 shadow-sm'
                : 'text-gray-400 hover:text-white hover:bg-surface'
            }`}
          >
            <Layers className="w-4 h-4" />
            <span>Option Chain &amp; Strike-wise PCR</span>
          </button>

          <button
            onClick={() => setActiveTab('chart')}
            className={`px-4 py-2 rounded-xl text-xs font-semibold flex items-center space-x-2 transition ${
              activeTab === 'chart'
                ? 'bg-blue-600/20 text-blue-400 border border-blue-500/40 shadow-sm'
                : 'text-gray-400 hover:text-white hover:bg-surface'
            }`}
          >
            <BarChart2 className="w-4 h-4" />
            <span>Intraday PCR History Chart</span>
          </button>

          <button
            onClick={() => setActiveTab('levels')}
            className={`px-4 py-2 rounded-xl text-xs font-semibold flex items-center space-x-2 transition ${
              activeTab === 'levels'
                ? 'bg-blue-600/20 text-blue-400 border border-blue-500/40 shadow-sm'
                : 'text-gray-400 hover:text-white hover:bg-surface'
            }`}
          >
            <ShieldCheck className="w-4 h-4" />
            <span>Support &amp; Resistance / Sentiment</span>
          </button>

          <button
            onClick={() => setActiveTab('settings')}
            className={`px-4 py-2 rounded-xl text-xs font-semibold flex items-center space-x-2 transition ${
              activeTab === 'settings'
                ? 'bg-blue-600/20 text-blue-400 border border-blue-500/40 shadow-sm'
                : 'text-gray-400 hover:text-white hover:bg-surface'
            }`}
          >
            <Sliders className="w-4 h-4" />
            <span>Settings</span>
          </button>
        </div>
      </div>

      {/* 5. Tab Content Sections */}
      <div className="p-4 sm:p-6 flex-1">
        {/* TAB 1: OPTION CHAIN & STRIKE-WISE PCR TABLE */}
        {activeTab === 'chain' && (
          <div className="bg-surface/90 rounded-2xl border border-border shadow-xl overflow-hidden flex flex-col">
            {/* Table Header Controls */}
            <div className="p-3.5 px-4 bg-surface border-b border-border/80 flex flex-wrap items-center justify-between gap-3 text-xs">
              <div className="flex items-center space-x-2">
                <span className="font-semibold text-white">Live Strikes Table</span>
                <span className="text-gray-500">&bull;</span>
                <span className="text-gray-400 font-mono">
                  Showing {data?.strikes?.length || 0} strike levels around ATM ({data?.range_info?.atm_strike})
                </span>
              </div>

              <div className="flex items-center space-x-4 font-mono text-[11px]">
                <div className="flex items-center space-x-1.5">
                  <span className="w-2.5 h-2.5 rounded bg-blue-500/40 border border-blue-500 inline-block" />
                  <span className="text-blue-300">ATM Strike</span>
                </div>
                <div className="flex items-center space-x-1.5">
                  <span className="w-2.5 h-2.5 rounded bg-rose-500/30 border border-rose-500 inline-block" />
                  <span className="text-rose-300">Resistance (Max CE OI)</span>
                </div>
                <div className="flex items-center space-x-1.5">
                  <span className="w-2.5 h-2.5 rounded bg-emerald-500/30 border border-emerald-500 inline-block" />
                  <span className="text-emerald-300">Support (Max PE OI)</span>
                </div>
              </div>
            </div>

            {/* Responsive Table */}
            <div className="overflow-x-auto min-w-full">
              <table className="w-full text-left text-xs font-mono border-collapse select-none">
                {/* Master Headers */}
                <thead>
                  <tr className="border-b border-border/80 bg-background/80 text-[11px] font-bold text-gray-400 uppercase tracking-wider">
                    <th colSpan={settings.show_volume ? 5 : 4} className="py-2.5 px-3 text-center bg-emerald-950/20 text-emerald-400 border-r border-border/60">
                      PUT SIDE (BULLISH SUPPORT)
                    </th>
                    <th className="py-2.5 px-4 text-center bg-blue-950/20 text-blue-300 border-r border-border/60">
                      STRIKE
                    </th>
                    <th colSpan={settings.show_volume ? 5 : 4} className="py-2.5 px-3 text-center bg-rose-950/20 text-rose-400 border-r border-border/60">
                      CALL SIDE (BEARISH RESISTANCE)
                    </th>
                    {settings.show_strike_ratios && (
                      <th colSpan={2} className="py-2.5 px-3 text-center bg-indigo-950/20 text-indigo-300">
                        ANALYTICS &amp; DISTRIBUTION
                      </th>
                    )}
                  </tr>

                  {/* Sub-column Headers */}
                  <tr className="border-b border-border/60 bg-surface/90 text-gray-400 text-[11px]">
                    {/* Put columns */}
                    <th className="py-2 px-3 text-right">PE LTP</th>
                    {settings.show_volume && <th className="py-2 px-3 text-right">Volume</th>}
                    <th className="py-2 px-3 text-right">PE OI</th>
                    <th className="py-2 px-3 text-right">OI Chg</th>
                    {settings.show_oi_change_pct && <th className="py-2 px-3 text-right border-r border-border/60">Chg %</th>}

                    {/* Strike column */}
                    <th className="py-2 px-4 text-center border-r border-border/60 font-bold text-white bg-surface">
                      Strike Price
                    </th>

                    {/* Call columns */}
                    <th className="py-2 px-3 text-right">CE LTP</th>
                    {settings.show_volume && <th className="py-2 px-3 text-right">Volume</th>}
                    <th className="py-2 px-3 text-right">CE OI</th>
                    <th className="py-2 px-3 text-right">OI Chg</th>
                    {settings.show_oi_change_pct && <th className="py-2 px-3 text-right border-r border-border/60">Chg %</th>}

                    {/* Analytics */}
                    {settings.show_strike_ratios && (
                      <>
                        <th className="py-2 px-3 text-center">Strike PCR</th>
                        <th className="py-2 px-4 text-center">PE vs CE OI Visual</th>
                      </>
                    )}
                  </tr>
                </thead>

                {/* Table Rows */}
                <tbody className="divide-y divide-border/30">
                  {isLoading ? (
                    <tr>
                      <td colSpan={14} className="py-12 text-center text-gray-400">
                        <RefreshCw className="w-6 h-6 animate-spin mx-auto text-blue-400 mb-2" />
                        <span>Fetching live options chain...</span>
                      </td>
                    </tr>
                  ) : !data || data.strikes.length === 0 ? (
                    <tr>
                      <td colSpan={14} className="py-12 text-center text-gray-400">
                        <AlertTriangle className="w-6 h-6 text-amber-400 mx-auto mb-2" />
                        <span>No strike data available for the selected criteria.</span>
                      </td>
                    </tr>
                  ) : (
                    data.strikes.map((s) => {
                      const isMaxCallOI = s.strike === data.cards.call_oi.highest_oi_strike;
                      const isMaxPutOI = s.strike === data.cards.put_oi.highest_oi_strike;
                      const isMaxCallChg = s.strike === data.cards.call_oi.highest_oi_change_strike;
                      const isMaxPutChg = s.strike === data.cards.put_oi.highest_oi_change_strike;

                      const peRatioWidth = Math.min(100, (s.pe_oi / maxStrikeOI) * 100);
                      const ceRatioWidth = Math.min(100, (s.ce_oi / maxStrikeOI) * 100);

                      return (
                        <tr
                          key={s.strike}
                          className={`hover:bg-blue-600/5 transition-colors ${
                            s.is_atm
                              ? 'bg-blue-950/30 font-bold border-y-2 border-blue-500/60'
                              : isMaxCallOI
                              ? 'bg-rose-950/15'
                              : isMaxPutOI
                              ? 'bg-emerald-950/15'
                              : ''
                          }`}
                        >
                          {/* PUT SIDE */}
                          <td className={`py-2 px-3 text-right ${s.pe_moneyness === 'ITM' ? 'bg-amber-500/5 text-amber-300' : 'text-gray-200'}`}>
                            {s.pe_ltp !== null ? s.pe_ltp.toFixed(2) : 'N/A'}
                          </td>
                          {settings.show_volume && (
                            <td className="py-2 px-3 text-right text-gray-400">{formatNumber(s.pe_volume)}</td>
                          )}
                          <td className={`py-2 px-3 text-right font-semibold ${isMaxPutOI ? 'text-emerald-400 bg-emerald-500/10' : 'text-gray-200'}`}>
                            {formatNumber(s.pe_oi)}
                            {isMaxPutOI && (
                              <span className="ml-1 text-[9px] px-1 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
                                S1
                              </span>
                            )}
                          </td>
                          <td className={`py-2 px-3 text-right font-semibold ${s.pe_oi_change >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                            {s.pe_oi_change >= 0 ? '+' : ''}{formatNumber(s.pe_oi_change)}
                            {isMaxPutChg && (
                              <span className="ml-1 text-[9px] px-1 py-0.5 rounded bg-emerald-500/20 text-emerald-300">
                                PE+
                              </span>
                            )}
                          </td>
                          {settings.show_oi_change_pct && (
                            <td className={`py-2 px-3 text-right border-r border-border/60 ${s.pe_oi_change_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                              {s.pe_oi_change_pct >= 0 ? '+' : ''}{s.pe_oi_change_pct}%
                            </td>
                          )}

                          {/* STRIKE PRICE */}
                          <td className="py-2 px-4 text-center border-r border-border/60 bg-surface/80">
                            <div className="flex items-center justify-center space-x-1.5">
                              <span className={`text-sm font-bold font-mono ${s.is_atm ? 'text-blue-400' : 'text-white'}`}>
                                {s.strike.toLocaleString()}
                              </span>
                              {s.is_atm && (
                                <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-blue-500/30 text-blue-300 border border-blue-500 font-extrabold uppercase">
                                  ATM
                                </span>
                              )}
                            </div>
                          </td>

                          {/* CALL SIDE */}
                          <td className={`py-2 px-3 text-right ${s.ce_moneyness === 'ITM' ? 'bg-amber-500/5 text-amber-300' : 'text-gray-200'}`}>
                            {s.ce_ltp !== null ? s.ce_ltp.toFixed(2) : 'N/A'}
                          </td>
                          {settings.show_volume && (
                            <td className="py-2 px-3 text-right text-gray-400">{formatNumber(s.ce_volume)}</td>
                          )}
                          <td className={`py-2 px-3 text-right font-semibold ${isMaxCallOI ? 'text-rose-400 bg-rose-500/10' : 'text-gray-200'}`}>
                            {formatNumber(s.ce_oi)}
                            {isMaxCallOI && (
                              <span className="ml-1 text-[9px] px-1 py-0.5 rounded bg-rose-500/20 text-rose-300 border border-rose-500/40">
                                R1
                              </span>
                            )}
                          </td>
                          <td className={`py-2 px-3 text-right font-semibold ${s.ce_oi_change >= 0 ? 'text-rose-400' : 'text-emerald-400'}`}>
                            {s.ce_oi_change >= 0 ? '+' : ''}{formatNumber(s.ce_oi_change)}
                            {isMaxCallChg && (
                              <span className="ml-1 text-[9px] px-1 py-0.5 rounded bg-rose-500/20 text-rose-300">
                                CE+
                              </span>
                            )}
                          </td>
                          {settings.show_oi_change_pct && (
                            <td className={`py-2 px-3 text-right border-r border-border/60 ${s.ce_oi_change_pct >= 0 ? 'text-rose-400' : 'text-emerald-400'}`}>
                              {s.ce_oi_change_pct >= 0 ? '+' : ''}{s.ce_oi_change_pct}%
                            </td>
                          )}

                          {/* STRIKE PCR & VISUAL BAR */}
                          {settings.show_strike_ratios && (
                            <>
                              <td className="py-2 px-3 text-center">
                                <span
                                  className={`px-2 py-0.5 rounded font-mono font-bold text-xs ${
                                    s.strike_oi_pcr === null
                                      ? 'text-gray-500'
                                      : s.strike_oi_pcr >= settings.bullish_threshold
                                      ? 'text-emerald-400 bg-emerald-950/60'
                                      : s.strike_oi_pcr <= settings.bearish_threshold
                                      ? 'text-rose-400 bg-rose-950/60'
                                      : 'text-gray-300 bg-surface'
                                  }`}
                                >
                                  {s.strike_oi_pcr !== null ? s.strike_oi_pcr.toFixed(2) : 'N/A'}
                                </span>
                              </td>

                              <td className="py-2 px-4">
                                <div className="flex items-center space-x-1.5 h-3 w-36 mx-auto bg-surface rounded-full overflow-hidden p-0.5 border border-border/60">
                                  {/* Put bar (green) */}
                                  <div
                                    style={{ width: `${peRatioWidth / 2}%` }}
                                    className="h-full bg-emerald-500 rounded-l-full transition-all"
                                    title={`Put OI: ${s.pe_oi}`}
                                  />
                                  {/* Call bar (red) */}
                                  <div
                                    style={{ width: `${ceRatioWidth / 2}%` }}
                                    className="h-full bg-rose-500 rounded-r-full transition-all"
                                    title={`Call OI: ${s.ce_oi}`}
                                  />
                                </div>
                              </td>
                            </>
                          )}
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* TAB 2: INTRADAY PCR HISTORY CHART */}
        {activeTab === 'chart' && (
          <div className="bg-surface/90 rounded-2xl border border-border p-5 shadow-xl flex flex-col space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border/80 pb-4">
              <div>
                <h3 className="text-base font-bold text-white flex items-center space-x-2">
                  <BarChart2 className="w-5 h-5 text-blue-400" />
                  <span>Intraday PCR &amp; Spot History (1-Minute Snapshots)</span>
                </h3>
                <p className="text-xs text-gray-400 font-mono">
                  Track intraday Put-Call Ratio evolution alongside Underlying Spot Price and Futures VWAP
                </p>
              </div>

              {/* Date Selector for Historical Sessions */}
              <div className="flex items-center space-x-2">
                <span className="text-xs font-mono text-gray-400">Date:</span>
                <select
                  value={selectedDate}
                  onChange={(e) => setSelectedDate(e.target.value)}
                  className="bg-background border border-border rounded-xl px-3 py-1.5 text-xs font-semibold text-white focus:outline-none focus:border-blue-500"
                >
                  {availableDates.map((d) => (
                    <option key={d} value={d}>
                      {d}
                    </option>
                  ))}
                </select>

                <button
                  onClick={loadHistory}
                  disabled={loadingHistory}
                  className="p-1.5 rounded-lg bg-surface border border-border hover:bg-surface/80 text-gray-300 transition"
                  title="Reload Chart Data"
                >
                  <RefreshCw className={`w-4 h-4 ${loadingHistory ? 'animate-spin' : ''}`} />
                </button>
              </div>
            </div>

            {/* Interactive SVG Chart */}
            {loadingHistory ? (
              <div className="h-72 flex items-center justify-center text-gray-400">
                <RefreshCw className="w-6 h-6 animate-spin mr-2 text-blue-400" />
                <span>Loading chart data...</span>
              </div>
            ) : historyPoints.length === 0 ? (
              <div className="h-72 flex flex-col items-center justify-center text-gray-400 space-y-2">
                <Info className="w-8 h-8 text-blue-400" />
                <p className="text-sm font-semibold">No recorded intraday snapshots found for {selectedDate}.</p>
                <p className="text-xs text-gray-500">
                  Snapshots are automatically saved every 60 seconds while the page or market feed is active.
                </p>
              </div>
            ) : (
              <div>
                {/* Chart Summary Metrics */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4 text-xs font-mono">
                  <div className="p-3 rounded-xl bg-background border border-border">
                    <span className="text-gray-400 block">Snapshots Recorded</span>
                    <span className="text-lg font-bold text-white">{historyPoints.length}</span>
                  </div>
                  <div className="p-3 rounded-xl bg-background border border-border">
                    <span className="text-gray-400 block">Latest OI PCR</span>
                    <span className="text-lg font-bold text-emerald-400">
                      {historyPoints[historyPoints.length - 1]?.oi_pcr?.toFixed(2) || 'N/A'}
                    </span>
                  </div>
                  <div className="p-3 rounded-xl bg-background border border-border">
                    <span className="text-gray-400 block">Latest Volume PCR</span>
                    <span className="text-lg font-bold text-blue-400">
                      {historyPoints[historyPoints.length - 1]?.volume_pcr?.toFixed(2) || 'N/A'}
                    </span>
                  </div>
                  <div className="p-3 rounded-xl bg-background border border-border">
                    <span className="text-gray-400 block">Spot Price</span>
                    <span className="text-lg font-bold text-white">
                      {historyPoints[historyPoints.length - 1]?.spot_price?.toLocaleString() || 'N/A'}
                    </span>
                  </div>
                </div>

                {/* SVG Visual Lines Chart */}
                <div className="relative h-72 w-full bg-background rounded-xl border border-border p-4 overflow-hidden">
                  {/* Reference Neutral Zone (0.95 - 1.05) */}
                  <div className="absolute inset-x-0 top-1/2 -translate-y-1/2 h-10 bg-slate-800/20 border-y border-dashed border-gray-700/40 pointer-events-none flex items-center justify-end px-3">
                    <span className="text-[10px] font-mono text-gray-500">Neutral Band (0.95 - 1.05)</span>
                  </div>

                  <svg className="w-full h-full overflow-visible">
                    {/* Render OI PCR Polyline */}
                    {(() => {
                      const points = historyPoints.filter((p) => p.oi_pcr !== null);
                      if (points.length < 2) return null;
                      const maxPCR = Math.max(1.5, ...points.map((p) => p.oi_pcr || 1));
                      const minPCR = Math.min(0.6, ...points.map((p) => p.oi_pcr || 1));
                      const range = maxPCR - minPCR || 1;

                      const coords = points.map((p, idx) => {
                        const x = (idx / (points.length - 1)) * 100;
                        const y = 100 - (((p.oi_pcr || 1) - minPCR) / range) * 100;
                        return `${x}%,${y}%`;
                      });

                      return (
                        <polyline
                          fill="none"
                          stroke="#10b981"
                          strokeWidth="2.5"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          points={coords.join(' ')}
                        />
                      );
                    })()}

                    {/* Render Volume PCR Polyline */}
                    {(() => {
                      const points = historyPoints.filter((p) => p.volume_pcr !== null);
                      if (points.length < 2) return null;
                      const maxPCR = Math.max(1.5, ...points.map((p) => p.volume_pcr || 1));
                      const minPCR = Math.min(0.6, ...points.map((p) => p.volume_pcr || 1));
                      const range = maxPCR - minPCR || 1;

                      const coords = points.map((p, idx) => {
                        const x = (idx / (points.length - 1)) * 100;
                        const y = 100 - (((p.volume_pcr || 1) - minPCR) / range) * 100;
                        return `${x}%,${y}%`;
                      });

                      return (
                        <polyline
                          fill="none"
                          stroke="#3b82f6"
                          strokeWidth="2"
                          strokeDasharray="4 4"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          points={coords.join(' ')}
                        />
                      );
                    })()}
                  </svg>

                  {/* Chart Legend */}
                  <div className="absolute bottom-2 left-4 flex items-center space-x-4 text-xs font-mono bg-surface/90 px-3 py-1.5 rounded-lg border border-border">
                    <div className="flex items-center space-x-1.5">
                      <span className="w-3 h-0.5 bg-emerald-500 inline-block" />
                      <span className="text-emerald-400">OI PCR</span>
                    </div>
                    <div className="flex items-center space-x-1.5">
                      <span className="w-3 h-0.5 bg-blue-500 border-dashed inline-block" />
                      <span className="text-blue-400">Volume PCR</span>
                    </div>
                  </div>
                </div>

                {/* History Table below chart */}
                <div className="mt-4 overflow-x-auto rounded-xl border border-border">
                  <table className="w-full text-left text-xs font-mono">
                    <thead className="bg-surface text-gray-400 text-[11px] border-b border-border">
                      <tr>
                        <th className="py-2 px-3">Time (IST)</th>
                        <th className="py-2 px-3 text-right">Spot Price</th>
                        <th className="py-2 px-3 text-right">OI PCR</th>
                        <th className="py-2 px-3 text-right">Volume PCR</th>
                        <th className="py-2 px-3 text-right">Futures VWAP</th>
                        <th className="py-2 px-3 text-center">Bias</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/40">
                      {historyPoints.slice(-10).reverse().map((hp, idx) => (
                        <tr key={idx} className="hover:bg-surface/50">
                          <td className="py-2 px-3 text-gray-300">{hp.time_ist}</td>
                          <td className="py-2 px-3 text-right font-semibold text-white">{hp.spot_price.toLocaleString()}</td>
                          <td className="py-2 px-3 text-right font-bold text-emerald-400">{hp.oi_pcr?.toFixed(2) || 'N/A'}</td>
                          <td className="py-2 px-3 text-right font-bold text-blue-400">{hp.volume_pcr?.toFixed(2) || 'N/A'}</td>
                          <td className="py-2 px-3 text-right text-gray-300">{hp.futures_vwap ? hp.futures_vwap.toLocaleString() : 'N/A'}</td>
                          <td className="py-2 px-3 text-center">
                            <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-surface border border-border">
                              {hp.sentiment}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}

        {/* TAB 3: SUPPORT & RESISTANCE / SENTIMENT ENGINE */}
        {activeTab === 'levels' && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            {/* S&R Levels Card */}
            <div className="bg-surface/90 rounded-2xl border border-border p-5 shadow-xl flex flex-col space-y-4">
              <h3 className="text-base font-bold text-white flex items-center space-x-2">
                <ShieldCheck className="w-5 h-5 text-emerald-400" />
                <span>Options Open Interest Concentration Zones</span>
              </h3>
              <p className="text-xs text-gray-400 font-mono">
                Candidate Support and Resistance derived directly from highest CE and PE open interest strikes.
              </p>

              <div className="space-y-3 font-mono text-xs mt-2">
                <div className="p-3.5 rounded-xl bg-rose-950/20 border border-rose-800/40 flex items-center justify-between">
                  <div>
                    <span className="text-rose-400 font-bold block text-sm">Major Resistance (R1)</span>
                    <span className="text-gray-400 text-[11px]">Highest Call OI Concentration</span>
                  </div>
                  <div className="text-right">
                    <span className="text-lg font-bold text-white block">{data?.levels.resistance_1 || 0}</span>
                    <span className="text-rose-300 text-[11px]">{formatNumber(data?.levels.resistance_1_oi)} OI</span>
                  </div>
                </div>

                <div className="p-3.5 rounded-xl bg-amber-950/20 border border-amber-800/40 flex items-center justify-between">
                  <div>
                    <span className="text-amber-400 font-bold block text-sm">Active Call Writing</span>
                    <span className="text-gray-400 text-[11px]">Max Call OI Addition Today</span>
                  </div>
                  <div className="text-right">
                    <span className="text-lg font-bold text-white block">{data?.levels.resistance_addition_strike || 0}</span>
                    <span className="text-amber-300 text-[11px]">Heavy Resistance Building</span>
                  </div>
                </div>

                <div className="p-3.5 rounded-xl bg-blue-950/20 border border-blue-800/40 flex items-center justify-between">
                  <div>
                    <span className="text-blue-400 font-bold block text-sm">Current ATM Strike</span>
                    <span className="text-gray-400 text-[11px]">Equilibrium Pivot</span>
                  </div>
                  <div className="text-right">
                    <span className="text-lg font-bold text-white block">{data?.levels.atm_strike || 0}</span>
                    <span className="text-blue-300 text-[11px]">ATM Level</span>
                  </div>
                </div>

                <div className="p-3.5 rounded-xl bg-emerald-950/20 border border-emerald-800/40 flex items-center justify-between">
                  <div>
                    <span className="text-emerald-400 font-bold block text-sm">Active Put Writing</span>
                    <span className="text-gray-400 text-[11px]">Max Put OI Addition Today</span>
                  </div>
                  <div className="text-right">
                    <span className="text-lg font-bold text-white block">{data?.levels.support_addition_strike || 0}</span>
                    <span className="text-emerald-300 text-[11px]">Active Support Building</span>
                  </div>
                </div>

                <div className="p-3.5 rounded-xl bg-emerald-950/20 border border-emerald-800/40 flex items-center justify-between">
                  <div>
                    <span className="text-emerald-400 font-bold block text-sm">Major Support (S1)</span>
                    <span className="text-gray-400 text-[11px]">Highest Put OI Concentration</span>
                  </div>
                  <div className="text-right">
                    <span className="text-lg font-bold text-white block">{data?.levels.support_1 || 0}</span>
                    <span className="text-emerald-300 text-[11px]">{formatNumber(data?.levels.support_1_oi)} OI</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Rules-Based Sentiment Explanation Table */}
            <div className="bg-surface/90 rounded-2xl border border-border p-5 shadow-xl flex flex-col space-y-4">
              <h3 className="text-base font-bold text-white flex items-center space-x-2">
                <Info className="w-5 h-5 text-blue-400" />
                <span>Deterministic Sentiment Engine Breakdown</span>
              </h3>
              <p className="text-xs text-gray-400 font-mono">
                Transparent rules evaluating 5 independent metrics. No LLM or invented signals.
              </p>

              <div className="space-y-2.5 font-mono text-xs mt-2">
                <div className="p-3 rounded-xl bg-background border border-border flex items-center justify-between">
                  <div>
                    <span className="text-white font-semibold block">1. OI PCR Ratio</span>
                    <span className="text-gray-400 text-[11px]">
                      Value: {data?.cards.oi_pcr.value ?? 'N/A'} (Threshold: &gt;{settings.bullish_threshold} Bullish, &lt;{settings.bearish_threshold} Bearish)
                    </span>
                  </div>
                  <span className="px-2.5 py-1 rounded font-bold text-xs bg-surface border border-border">
                    {data?.cards.market_bias.breakdown.oi_pcr_bias}
                  </span>
                </div>

                <div className="p-3 rounded-xl bg-background border border-border flex items-center justify-between">
                  <div>
                    <span className="text-white font-semibold block">2. Volume PCR Ratio</span>
                    <span className="text-gray-400 text-[11px]">
                      Value: {data?.cards.volume_pcr.value ?? 'N/A'} (Threshold: &gt;1.05 Bullish, &lt;0.95 Bearish)
                    </span>
                  </div>
                  <span className="px-2.5 py-1 rounded font-bold text-xs bg-surface border border-border">
                    {data?.cards.market_bias.breakdown.volume_pcr_bias}
                  </span>
                </div>

                <div className="p-3 rounded-xl bg-background border border-border flex items-center justify-between">
                  <div>
                    <span className="text-white font-semibold block">3. OI Additions (Put vs Call Writing)</span>
                    <span className="text-gray-400 text-[11px]">
                      Put Chg: {formatNumber(data?.cards.put_oi.oi_change)} vs Call Chg: {formatNumber(data?.cards.call_oi.oi_change)}
                    </span>
                  </div>
                  <span className="px-2.5 py-1 rounded font-bold text-xs bg-surface border border-border">
                    {data?.cards.market_bias.breakdown.oi_addition_bias}
                  </span>
                </div>

                <div className="p-3 rounded-xl bg-background border border-border flex items-center justify-between">
                  <div>
                    <span className="text-white font-semibold block">4. Spot vs Futures VWAP</span>
                    <span className="text-gray-400 text-[11px]">
                      Spot: {data?.cards.price_vwap.spot_price} vs VWAP: {data?.cards.price_vwap.futures_vwap || 'N/A'}
                    </span>
                  </div>
                  <span className="px-2.5 py-1 rounded font-bold text-xs bg-surface border border-border">
                    {data?.cards.market_bias.breakdown.price_vwap_bias}
                  </span>
                </div>

                <div className="p-3 rounded-xl bg-background border border-border flex items-center justify-between">
                  <div>
                    <span className="text-white font-semibold block">5. Intraday PCR Trend</span>
                    <span className="text-gray-400 text-[11px]">Compared to previous snapshot reading</span>
                  </div>
                  <span className="px-2.5 py-1 rounded font-bold text-xs bg-surface border border-border">
                    {data?.cards.market_bias.breakdown.pcr_trend}
                  </span>
                </div>

                <div className="p-4 rounded-xl bg-blue-950/20 border border-blue-800/40 mt-3 text-xs">
                  <div className="flex justify-between font-bold text-white mb-1">
                    <span>Combined Outcome:</span>
                    <span className="text-blue-300">{data?.cards.market_bias.headline}</span>
                  </div>
                  <p className="text-gray-300 leading-relaxed">{data?.cards.market_bias.explanation}</p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* TAB 4: SETTINGS PANEL */}
        {activeTab === 'settings' && (
          <div className="max-w-2xl mx-auto bg-surface/90 rounded-2xl border border-border p-6 shadow-xl space-y-6">
            <div>
              <h3 className="text-base font-bold text-white flex items-center space-x-2">
                <Sliders className="w-5 h-5 text-blue-400" />
                <span>PCR &amp; Options Analytics Settings</span>
              </h3>
              <p className="text-xs text-gray-400 font-mono">
                Configure default thresholds, refresh cadence, and table display options.
              </p>
            </div>

            <div className="space-y-4 font-mono text-xs">
              <div className="flex items-center justify-between p-3 rounded-xl bg-background border border-border">
                <div>
                  <label className="text-white font-semibold block">Auto-Refresh Cadence (Seconds)</label>
                  <span className="text-gray-400 text-[11px]">Default: 60 seconds (prevents broker rate limits)</span>
                </div>
                <input
                  type="number"
                  min={15}
                  max={300}
                  value={settings.refresh_interval_sec}
                  onChange={(e) => updateSettings({ refresh_interval_sec: Number(e.target.value) })}
                  className="w-20 bg-surface border border-border rounded-lg px-2.5 py-1 text-right text-white focus:outline-none focus:border-blue-500 font-bold"
                />
              </div>

              <div className="flex items-center justify-between p-3 rounded-xl bg-background border border-border">
                <div>
                  <label className="text-white font-semibold block">OI PCR Bullish Threshold</label>
                  <span className="text-gray-400 text-[11px]">Values above this are classified as Bullish Lean</span>
                </div>
                <input
                  type="number"
                  step={0.05}
                  value={settings.bullish_threshold}
                  onChange={(e) => updateSettings({ bullish_threshold: Number(e.target.value) })}
                  className="w-20 bg-surface border border-border rounded-lg px-2.5 py-1 text-right text-emerald-400 focus:outline-none focus:border-blue-500 font-bold"
                />
              </div>

              <div className="flex items-center justify-between p-3 rounded-xl bg-background border border-border">
                <div>
                  <label className="text-white font-semibold block">OI PCR Bearish Threshold</label>
                  <span className="text-gray-400 text-[11px]">Values below this are classified as Bearish Lean</span>
                </div>
                <input
                  type="number"
                  step={0.05}
                  value={settings.bearish_threshold}
                  onChange={(e) => updateSettings({ bearish_threshold: Number(e.target.value) })}
                  className="w-20 bg-surface border border-border rounded-lg px-2.5 py-1 text-right text-rose-400 focus:outline-none focus:border-blue-500 font-bold"
                />
              </div>

              <div className="border-t border-border/60 pt-4 space-y-3">
                <span className="font-bold text-gray-300 block">Table Display Options</span>

                <label className="flex items-center space-x-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={settings.show_volume}
                    onChange={(e) => updateSettings({ show_volume: e.target.checked })}
                    className="rounded bg-surface border-border text-blue-600 focus:ring-0"
                  />
                  <span className="text-gray-300">Show Traded Volume columns in Option Chain table</span>
                </label>

                <label className="flex items-center space-x-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={settings.show_oi_change_pct}
                    onChange={(e) => updateSettings({ show_oi_change_pct: e.target.checked })}
                    className="rounded bg-surface border-border text-blue-600 focus:ring-0"
                  />
                  <span className="text-gray-300">Show OI Change Percentage (Chg %)</span>
                </label>

                <label className="flex items-center space-x-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={settings.show_strike_ratios}
                    onChange={(e) => updateSettings({ show_strike_ratios: e.target.checked })}
                    className="rounded bg-surface border-border text-blue-600 focus:ring-0"
                  />
                  <span className="text-gray-300">Show Strike-wise PCR &amp; Visual PE vs CE distribution bars</span>
                </label>
              </div>

              <div className="pt-3">
                <button
                  onClick={() => {
                    setSettings(DEFAULT_SETTINGS);
                    localStorage.removeItem('nextrade_pcr_settings');
                  }}
                  className="px-4 py-2 rounded-xl bg-surface border border-border hover:bg-surface/80 text-gray-300 transition"
                >
                  Reset to Default Settings
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
