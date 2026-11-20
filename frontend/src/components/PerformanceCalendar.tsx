import React, { useEffect, useState, useMemo } from 'react';
import {
  Calendar as CalendarIcon,
  CalendarRange,
  Filter,
  ChevronLeft,
  ChevronRight,
  TrendingUp,
  TrendingDown,
  Download,
  Flame,
  ShieldCheck,
  RotateCcw,
  X,
  ExternalLink,
  Clock,
  Layers,
  Award,
  AlertTriangle,
  CheckCircle2,
  AlertCircle,
  DollarSign,
  Percent,
  Activity,
  ArrowRight,
  Maximize2
} from 'lucide-react';
import {
  MonthlyCalendarResponse,
  YearlyCalendarResponse,
  DailyDetailResponse,
  CustomRangeResponse,
  CalendarDayItem,
  YearlyMonthItem
} from '../types';
import { api } from '../services/api';
import { formatCurrency, formatIST, getPnlColor, getPnlBg } from '../utils/formatters';

interface PerformanceCalendarProps {
  initialSource?: 'PAPER' | 'BACKTEST';
  initialRunId?: number;
  embedded?: boolean;
  onClose?: () => void;
}

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'
];

const WEEKDAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
const WEEKDAY_SHORT = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

export const PerformanceCalendar: React.FC<PerformanceCalendarProps> = ({
  initialSource = 'PAPER',
  initialRunId,
  embedded = false,
  onClose,
}) => {
  // Navigation & View Mode State
  const now = new Date();
  const currentIstYear = now.getFullYear();
  const currentIstMonth = now.getMonth() + 1; // 1-12

  const [viewMode, setViewMode] = useState<'MONTHLY' | 'YEARLY' | 'CUSTOM'>(() => {
    const saved = localStorage.getItem('nextrade_calendar_view');
    return saved === 'YEARLY' || saved === 'CUSTOM' ? saved : 'MONTHLY';
  });

  const [year, setYear] = useState<number>(() => {
    const saved = localStorage.getItem('nextrade_calendar_year');
    return saved ? parseInt(saved, 10) : currentIstYear;
  });

  const [month, setMonth] = useState<number>(() => {
    const saved = localStorage.getItem('nextrade_calendar_month');
    return saved ? parseInt(saved, 10) : currentIstMonth;
  });

  // Filter States
  const [source, setSource] = useState<'PAPER' | 'BACKTEST'>(initialSource);
  const [runId, setRunId] = useState<number | undefined>(initialRunId);
  const [strategyFilter, setStrategyFilter] = useState<string>('ALL');
  const [executionModeFilter, setExecutionModeFilter] = useState<string>('ALL');

  // Custom Range State
  const [customStart, setCustomStart] = useState<string>(() => {
    const d = new Date();
    d.setDate(d.getDate() - 30);
    return d.toISOString().slice(0, 10);
  });
  const [customEnd, setCustomEnd] = useState<string>(() => {
    return new Date().toISOString().slice(0, 10);
  });

  // Data States
  const [monthlyData, setMonthlyData] = useState<MonthlyCalendarResponse | null>(null);
  const [yearlyData, setYearlyData] = useState<YearlyCalendarResponse | null>(null);
  const [customData, setCustomData] = useState<CustomRangeResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Daily Detail Drawer/Modal State
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [dailyDetail, setDailyDetail] = useState<DailyDetailResponse | null>(null);
  const [loadingDaily, setLoadingDaily] = useState<boolean>(false);
  const [expandedTradeIdx, setExpandedTradeIdx] = useState<number | null>(null);

  // Save persistent state
  useEffect(() => {
    localStorage.setItem('nextrade_calendar_view', viewMode);
  }, [viewMode]);

  useEffect(() => {
    localStorage.setItem('nextrade_calendar_year', year.toString());
  }, [year]);

  useEffect(() => {
    localStorage.setItem('nextrade_calendar_month', month.toString());
  }, [month]);

  // Load Monthly Calendar Data
  const loadMonthlyData = async () => {
    setLoading(true);
    setErrorMsg(null);
    try {
      const res = await api.getMonthlyCalendar({
        year,
        month,
        source,
        strategy_id: strategyFilter !== 'ALL' ? strategyFilter : undefined,
        execution_mode: executionModeFilter !== 'ALL' ? executionModeFilter : undefined,
        run_id: runId,
      });
      setMonthlyData(res);
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to load monthly calendar');
    } finally {
      setLoading(false);
    }
  };

  // Load Yearly Calendar Data
  const loadYearlyData = async () => {
    setLoading(true);
    setErrorMsg(null);
    try {
      const res = await api.getYearlyCalendar({
        year,
        source,
        strategy_id: strategyFilter !== 'ALL' ? strategyFilter : undefined,
        execution_mode: executionModeFilter !== 'ALL' ? executionModeFilter : undefined,
        run_id: runId,
      });
      setYearlyData(res);
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to load yearly overview');
    } finally {
      setLoading(false);
    }
  };

  // Load Custom Range Data
  const loadCustomData = async () => {
    setLoading(true);
    setErrorMsg(null);
    try {
      const res = await api.getCustomRangeCalendar({
        start_date: customStart,
        end_date: customEnd,
        source,
        strategy_id: strategyFilter !== 'ALL' ? strategyFilter : undefined,
        execution_mode: executionModeFilter !== 'ALL' ? executionModeFilter : undefined,
        run_id: runId,
      });
      setCustomData(res);
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to load custom range analytics');
    } finally {
      setLoading(false);
    }
  };

  // Load Daily Detail
  const loadDailyDetail = async (dateStr: string) => {
    setSelectedDate(dateStr);
    setLoadingDaily(true);
    try {
      const res = await api.getDailyCalendarDetail({
        date: dateStr,
        source,
        strategy_id: strategyFilter !== 'ALL' ? strategyFilter : undefined,
        run_id: runId,
      });
      setDailyDetail(res);
    } catch (err: any) {
      console.error(err);
      setDailyDetail(null);
    } finally {
      setLoadingDaily(false);
    }
  };

  // Trigger data fetches based on view mode and dependencies
  useEffect(() => {
    if (viewMode === 'MONTHLY') {
      loadMonthlyData();
    } else if (viewMode === 'YEARLY') {
      loadYearlyData();
    } else if (viewMode === 'CUSTOM') {
      loadCustomData();
    }
  }, [viewMode, year, month, source, strategyFilter, executionModeFilter, runId]);

  // Navigation Handlers
  const handlePrevMonth = () => {
    if (month === 1) {
      setMonth(12);
      setYear((y) => y - 1);
    } else {
      setMonth((m) => m - 1);
    }
  };

  const handleNextMonth = () => {
    if (month === 12) {
      setMonth(1);
      setYear((y) => y + 1);
    } else {
      setMonth((m) => m + 1);
    }
  };

  const handleToday = () => {
    setYear(currentIstYear);
    setMonth(currentIstMonth);
  };

  const handlePrevYear = () => {
    setYear((y) => y - 1);
  };

  const handleNextYear = () => {
    setYear((y) => y + 1);
  };

  // Jump from Yearly View month card to Monthly View
  const handleSelectMonthFromYearly = (selectedM: number) => {
    setMonth(selectedM);
    setViewMode('MONTHLY');
  };

  // CSV Export Handlers
  const handleExportDailyCsv = (dateStr: string) => {
    const url = api.getExportDailyTradesCsvUrl(dateStr, source, strategyFilter !== 'ALL' ? strategyFilter : undefined, runId);
    window.open(url, '_blank');
  };

  const handleExportMonthlyCsv = () => {
    const url = api.getExportMonthlyCsvUrl(year, month, source, strategyFilter !== 'ALL' ? strategyFilter : undefined, runId);
    window.open(url, '_blank');
  };

  const handleExportYearlyCsv = () => {
    const url = api.getExportYearlyCsvUrl(year, source, strategyFilter !== 'ALL' ? strategyFilter : undefined, runId);
    window.open(url, '_blank');
  };

  const handleExportCustomCsv = () => {
    const url = api.getExportCustomCsvUrl(customStart, customEnd, source, strategyFilter !== 'ALL' ? strategyFilter : undefined, runId);
    window.open(url, '_blank');
  };

  // Quick summary shortcuts
  const mSummary = monthlyData?.summary;
  const ySummary = yearlyData?.annual_summary;

  return (
    <div className="space-y-6">
      {/* Top Header & View Controls */}
      <div className="bg-card border border-border rounded-xl p-5 space-y-4">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-center space-x-3">
            <div className="p-2.5 rounded-xl bg-purple-600/10 text-purple-400 border border-purple-500/30">
              <CalendarIcon className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h2 className="text-lg font-bold text-white tracking-wide">Performance Calendar &amp; Trading Telemetry</h2>
                <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-blue-500/10 text-blue-400 border border-blue-500/20">
                  IST AUDITED
                </span>
                {runId && (
                  <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-amber-500/10 text-amber-300 border border-amber-500/20">
                    RUN #{runId}
                  </span>
                )}
              </div>
              <p className="text-xs text-gray-400 font-mono">
                Interactive daily, monthly &amp; yearly performance ledger powered by executed trade records
              </p>
            </div>
          </div>

          {/* View Mode Toggle & Actions */}
          <div className="flex flex-wrap items-center gap-2">
            <div className="bg-surface p-1 rounded-lg border border-border flex items-center space-x-1 text-xs font-mono font-bold">
              <button
                onClick={() => setViewMode('MONTHLY')}
                className={`px-3 py-1.5 rounded-md flex items-center gap-1.5 transition-all ${
                  viewMode === 'MONTHLY'
                    ? 'bg-purple-600 text-white shadow-sm'
                    : 'text-gray-400 hover:text-white hover:bg-surface/80'
                }`}
              >
                <CalendarIcon className="w-3.5 h-3.5" />
                MONTHLY
              </button>
              <button
                onClick={() => setViewMode('YEARLY')}
                className={`px-3 py-1.5 rounded-md flex items-center gap-1.5 transition-all ${
                  viewMode === 'YEARLY'
                    ? 'bg-purple-600 text-white shadow-sm'
                    : 'text-gray-400 hover:text-white hover:bg-surface/80'
                }`}
              >
                <CalendarRange className="w-3.5 h-3.5" />
                YEARLY
              </button>
              <button
                onClick={() => setViewMode('CUSTOM')}
                className={`px-3 py-1.5 rounded-md flex items-center gap-1.5 transition-all ${
                  viewMode === 'CUSTOM'
                    ? 'bg-purple-600 text-white shadow-sm'
                    : 'text-gray-400 hover:text-white hover:bg-surface/80'
                }`}
              >
                <Filter className="w-3.5 h-3.5" />
                CUSTOM
              </button>
            </div>

            {/* CSV Export Button */}
            {viewMode === 'MONTHLY' && (
              <button
                onClick={handleExportMonthlyCsv}
                className="px-3 py-2 rounded-lg bg-surface border border-border hover:bg-surface/80 text-gray-300 hover:text-white text-xs font-mono font-semibold flex items-center gap-1.5 transition-all"
                title="Export Monthly Summary CSV"
              >
                <Download className="w-3.5 h-3.5 text-blue-400" />
                Export CSV
              </button>
            )}
            {viewMode === 'YEARLY' && (
              <button
                onClick={handleExportYearlyCsv}
                className="px-3 py-2 rounded-lg bg-surface border border-border hover:bg-surface/80 text-gray-300 hover:text-white text-xs font-mono font-semibold flex items-center gap-1.5 transition-all"
                title="Export Yearly Summary CSV"
              >
                <Download className="w-3.5 h-3.5 text-blue-400" />
                Export CSV
              </button>
            )}
            {viewMode === 'CUSTOM' && (
              <button
                onClick={handleExportCustomCsv}
                className="px-3 py-2 rounded-lg bg-surface border border-border hover:bg-surface/80 text-gray-300 hover:text-white text-xs font-mono font-semibold flex items-center gap-1.5 transition-all"
                title="Export Custom Range CSV"
              >
                <Download className="w-3.5 h-3.5 text-blue-400" />
                Export CSV
              </button>
            )}

            {onClose && (
              <button
                onClick={onClose}
                className="p-2 rounded-lg bg-surface border border-border hover:bg-surface/80 text-gray-400 hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>

        {/* Filter Controls Row */}
        <div className="flex flex-wrap items-center justify-between gap-3 pt-3 border-t border-border/50 text-xs font-mono">
          <div className="flex flex-wrap items-center gap-3">
            {/* Source Selector */}
            <div className="flex items-center space-x-1.5">
              <span className="text-gray-500">Source:</span>
              <div className="bg-surface rounded-md border border-border p-0.5 flex">
                <button
                  onClick={() => setSource('PAPER')}
                  className={`px-2.5 py-1 rounded text-[11px] font-bold transition-all ${
                    source === 'PAPER' ? 'bg-emerald-600/30 text-emerald-300 border border-emerald-500/40' : 'text-gray-400 hover:text-white'
                  }`}
                >
                  Paper Trading
                </button>
                <button
                  onClick={() => setSource('BACKTEST')}
                  className={`px-2.5 py-1 rounded text-[11px] font-bold transition-all ${
                    source === 'BACKTEST' ? 'bg-blue-600/30 text-blue-300 border border-blue-500/40' : 'text-gray-400 hover:text-white'
                  }`}
                >
                  Backtesting
                </button>
              </div>
            </div>

            {/* Strategy Filter */}
            <div className="flex items-center space-x-1.5">
              <span className="text-gray-500">Strategy:</span>
              <select
                value={strategyFilter}
                onChange={(e) => setStrategyFilter(e.target.value)}
                className="bg-surface border border-border rounded px-2.5 py-1 text-white font-semibold focus:outline-none focus:border-purple-500"
              >
                <option value="ALL">All Strategies</option>
                <option value="SUPERTREND_EMA">Supertrend EMA Scalper</option>
                <option value="UT_BOT">UT Bot ATM Option</option>
                <option value="EMA_RSI">NIFTY EMA / RSI</option>
              </select>
            </div>

            {/* Execution Mode Filter */}
            <div className="flex items-center space-x-1.5">
              <span className="text-gray-500">Mode:</span>
              <select
                value={executionModeFilter}
                onChange={(e) => setExecutionModeFilter(e.target.value)}
                className="bg-surface border border-border rounded px-2.5 py-1 text-white font-semibold focus:outline-none focus:border-purple-500"
              >
                <option value="ALL">All Execution Modes</option>
                <option value="TRIGGER_PRICE">Trigger Price (Strict)</option>
                <option value="REALISTIC">Realistic (Slippage)</option>
              </select>
            </div>
          </div>

          {/* Breadcrumb Navigation Indicator */}
          <div className="flex items-center space-x-1 text-gray-400">
            <span
              onClick={() => setViewMode('YEARLY')}
              className="cursor-pointer hover:text-white font-bold transition-colors"
            >
              {year}
            </span>
            <ChevronRight className="w-3 h-3 text-gray-600" />
            <span
              onClick={() => setViewMode('MONTHLY')}
              className={`cursor-pointer font-bold transition-colors ${
                viewMode === 'MONTHLY' ? 'text-purple-400' : 'hover:text-white'
              }`}
            >
              {MONTH_NAMES[month - 1]}
            </span>
            {selectedDate && (
              <>
                <ChevronRight className="w-3 h-3 text-gray-600" />
                <span className="text-emerald-400 font-bold">{selectedDate}</span>
              </>
            )}
          </div>
        </div>
      </div>

      {errorMsg && (
        <div className="bg-rose-950/40 border border-rose-800/60 rounded-xl p-4 text-xs font-mono text-rose-300 flex items-center space-x-2">
          <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
          <span>{errorMsg}</span>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 1. MONTHLY VIEW */}
      {/* ========================================================================= */}
      {viewMode === 'MONTHLY' && (
        <div className="space-y-6">
          {/* Month Navigation & Year Selector Bar */}
          <div className="bg-card border border-border rounded-xl p-4 flex flex-col sm:flex-row items-center justify-between gap-4">
            <div className="flex items-center space-x-2 font-mono">
              <button
                onClick={handlePrevMonth}
                className="p-2 rounded-lg bg-surface border border-border hover:bg-surface/80 text-gray-300 hover:text-white transition-all"
                title="Previous Month"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>

              <div className="flex items-center space-x-2 bg-surface border border-border px-3 py-1.5 rounded-lg">
                <select
                  value={month}
                  onChange={(e) => setMonth(parseInt(e.target.value, 10))}
                  className="bg-transparent text-white font-bold text-sm focus:outline-none cursor-pointer"
                >
                  {MONTH_NAMES.map((name, i) => (
                    <option key={i} value={i + 1} className="bg-surface text-white">
                      {name}
                    </option>
                  ))}
                </select>

                <select
                  value={year}
                  onChange={(e) => setYear(parseInt(e.target.value, 10))}
                  className="bg-transparent text-purple-400 font-bold text-sm focus:outline-none cursor-pointer"
                >
                  {[2024, 2025, 2026, 2027].map((y) => (
                    <option key={y} value={y} className="bg-surface text-white">
                      {y}
                    </option>
                  ))}
                </select>
              </div>

              <button
                onClick={handleNextMonth}
                className="p-2 rounded-lg bg-surface border border-border hover:bg-surface/80 text-gray-300 hover:text-white transition-all"
                title="Next Month"
              >
                <ChevronRight className="w-4 h-4" />
              </button>

              <button
                onClick={handleToday}
                className="px-3 py-1.5 rounded-lg bg-surface border border-border hover:bg-surface/80 text-gray-300 hover:text-white text-xs font-semibold"
              >
                Today
              </button>
            </div>

            {/* Quick Math Reconciliation Banner */}
            {mSummary && (
              <div className="text-xs font-mono text-gray-400 flex flex-wrap items-center gap-3">
                <span>
                  Gross: <strong className="text-emerald-400">+₹{mSummary.gross_profit.toFixed(2)}</strong>
                </span>
                <span>•</span>
                <span>
                  Loss: <strong className="text-rose-400">-₹{mSummary.gross_loss.toFixed(2)}</strong>
                </span>
                <span>•</span>
                <span>
                  Charges: <strong className="text-gray-300">₹{mSummary.total_charges.toFixed(2)}</strong>
                </span>
                <span>•</span>
                <span>
                  Slippage: <strong className="text-gray-300">₹{mSummary.total_slippage.toFixed(2)}</strong>
                </span>
                <span>=</span>
                <span className={`px-2 py-0.5 rounded font-bold ${getPnlBg(mSummary.net_pnl)}`}>
                  Net {formatCurrency(mSummary.net_pnl)}
                </span>
              </div>
            )}
          </div>

          {/* Monthly KPI Summary Cards */}
          {mSummary && (
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
              {/* Card 1: Total Net P&L */}
              <div className="bg-card border border-border rounded-xl p-4 font-mono">
                <span className="text-[11px] text-gray-400 block mb-1">MONTHLY NET P&amp;L</span>
                <div className={`text-xl font-bold ${getPnlColor(mSummary.net_pnl)}`}>
                  {formatCurrency(mSummary.net_pnl)}
                </div>
                <span className="text-[10px] text-gray-500">
                  {mSummary.net_pnl >= 0 ? 'Profitable Month' : 'Net Loss Month'}
                </span>
              </div>

              {/* Card 2: Win Rate */}
              <div className="bg-card border border-border rounded-xl p-4 font-mono">
                <span className="text-[11px] text-gray-400 block mb-1">DAILY WIN RATE</span>
                <div className="text-xl font-bold text-blue-400">{mSummary.win_rate.toFixed(1)}%</div>
                <span className="text-[10px] text-gray-500">
                  {mSummary.winning_days}W / {mSummary.losing_days}L / {mSummary.no_trade_days} Off
                </span>
              </div>

              {/* Card 3: Total Trades & Charges */}
              <div className="bg-card border border-border rounded-xl p-4 font-mono">
                <span className="text-[11px] text-gray-400 block mb-1">TOTAL TRADES</span>
                <div className="text-xl font-bold text-white">{mSummary.total_trades}</div>
                <span className="text-[10px] text-gray-500">Flat Chg: ₹{mSummary.total_charges.toFixed(0)}</span>
              </div>

              {/* Card 4: Avg Daily P&L */}
              <div className="bg-card border border-border rounded-xl p-4 font-mono">
                <span className="text-[11px] text-gray-400 block mb-1">AVG DAILY P&amp;L</span>
                <div className={`text-xl font-bold ${getPnlColor(mSummary.avg_daily_pnl)}`}>
                  {formatCurrency(mSummary.avg_daily_pnl)}
                </div>
                <span className="text-[10px] text-gray-500">{mSummary.total_trading_days} active traded days</span>
              </div>

              {/* Card 5: Best Day */}
              <div className="bg-card border border-border rounded-xl p-4 font-mono">
                <span className="text-[11px] text-gray-400 block mb-1">BEST DAY</span>
                <div className="text-xl font-bold text-emerald-400">
                  {mSummary.best_day.net_pnl > 0 ? `+₹${mSummary.best_day.net_pnl.toFixed(0)}` : '₹0.00'}
                </div>
                <span className="text-[10px] text-gray-500 truncate block">
                  {mSummary.best_day.date || 'No trades'}
                </span>
              </div>

              {/* Card 6: Worst Day */}
              <div className="bg-card border border-border rounded-xl p-4 font-mono">
                <span className="text-[11px] text-gray-400 block mb-1">WORST DAY</span>
                <div className="text-xl font-bold text-rose-400">
                  {mSummary.worst_day.net_pnl < 0 ? `-₹${Math.abs(mSummary.worst_day.net_pnl).toFixed(0)}` : '₹0.00'}
                </div>
                <span className="text-[10px] text-gray-500 truncate block">
                  {mSummary.worst_day.date || 'No trades'}
                </span>
              </div>
            </div>
          )}

          {/* Consecutive Winning / Losing Day Analysis (Streaks) */}
          {mSummary?.streaks && (
            <div className="bg-card border border-border rounded-xl p-4 font-mono text-xs flex flex-wrap items-center justify-between gap-4">
              <div className="flex items-center space-x-3">
                <div className="p-2 rounded-lg bg-amber-500/10 text-amber-400 border border-amber-500/30">
                  <Flame className="w-4 h-4" />
                </div>
                <div>
                  <span className="text-gray-400 text-[11px] block">CURRENT ACTIVE STREAK</span>
                  <div className="text-sm font-bold flex items-center space-x-2">
                    {mSummary.streaks.current_streak_type === 'WIN' && (
                      <span className="text-emerald-400 flex items-center gap-1">
                        <TrendingUp className="w-3.5 h-3.5" />
                        {mSummary.streaks.current_streak_count} Consecutive Winning Day{mSummary.streaks.current_streak_count > 1 ? 's' : ''}
                      </span>
                    )}
                    {mSummary.streaks.current_streak_type === 'LOSS' && (
                      <span className="text-rose-400 flex items-center gap-1">
                        <TrendingDown className="w-3.5 h-3.5" />
                        {mSummary.streaks.current_streak_count} Consecutive Losing Day{mSummary.streaks.current_streak_count > 1 ? 's' : ''}
                      </span>
                    )}
                    {mSummary.streaks.current_streak_type === 'NONE' && (
                      <span className="text-gray-400">Neutral / No active streak</span>
                    )}
                  </div>
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-6">
                <div>
                  <span className="text-gray-500 text-[10px] block">MAX WIN STREAK</span>
                  <span className="text-emerald-400 font-bold text-sm">
                    {mSummary.streaks.max_consecutive_wins} Days
                  </span>
                </div>

                <div>
                  <span className="text-gray-500 text-[10px] block">MAX LOSS STREAK</span>
                  <span className="text-rose-400 font-bold text-sm">
                    {mSummary.streaks.max_consecutive_losses} Days
                  </span>
                </div>

                <div>
                  <span className="text-gray-500 text-[10px] block">LONGEST NO-TRADE GAP</span>
                  <span className="text-gray-300 font-bold text-sm">
                    {mSummary.streaks.longest_no_trade_period_days} Days
                  </span>
                </div>

                <div>
                  <span className="text-gray-500 text-[10px] block">AVG HOLDING TIME</span>
                  <span className="text-blue-400 font-bold text-sm">
                    {mSummary.holding_time?.avg_minutes || 0} mins
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* Calendar Grid — Monday to Sunday Columns */}
          <div className="bg-card border border-border rounded-xl p-3 sm:p-5 shadow-sm">
            <div className="overflow-x-auto pb-2">
              <div className="min-w-[620px]">
                {/* Weekday Column Headers */}
                <div className="grid grid-cols-7 gap-2 mb-2 font-mono text-center text-xs font-bold text-gray-400 uppercase tracking-wider">
                  {WEEKDAY_SHORT.map((wd, i) => (
                    <div
                      key={i}
                      className={`py-2 rounded-lg bg-surface/50 border border-border/40 ${
                        i >= 5 ? 'text-gray-500' : 'text-gray-300'
                      }`}
                    >
                      <span className="hidden sm:inline">{WEEKDAY_NAMES[i]}</span>
                      <span className="sm:hidden">{wd}</span>
                    </div>
                  ))}
                </div>

                {/* Days Grid */}
                {loading ? (
                  <div className="py-24 text-center font-mono text-xs text-gray-500">
                    <Activity className="w-6 h-6 text-purple-400 animate-spin mx-auto mb-2" />
                    Aggregating trade records for {MONTH_NAMES[month - 1]} {year}...
                  </div>
                ) : !monthlyData || monthlyData.days.length === 0 ? (
                  <div className="py-24 text-center font-mono text-xs text-gray-500">
                    No calendar data available for this month.
                  </div>
                ) : (
                  <div className="grid grid-cols-7 gap-2">
                    {/* Empty cells before month start (Monday = 0 ... Sunday = 6) */}
                    {Array.from({ length: monthlyData.first_weekday }).map((_, idx) => (
                      <div
                        key={`blank-${idx}`}
                        className="min-h-[105px] rounded-xl border border-dashed border-border/20 bg-surface/10 opacity-30"
                      />
                    ))}

                    {/* Actual Month Days */}
                    {monthlyData.days.map((d: CalendarDayItem) => {
                      const isPositive = d.net_pnl > 0;
                      const isNegative = d.net_pnl < 0;
                      const isNeutral = d.has_trades && d.net_pnl === 0;
                      const isToday =
                        d.date === `${currentIstYear}-${String(currentIstMonth).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;

                      return (
                        <div
                          key={d.date}
                          onClick={() => d.has_trades && loadDailyDetail(d.date)}
                          className={`min-h-[105px] p-2.5 rounded-xl border flex flex-col justify-between transition-all font-mono select-none ${
                            d.is_future
                              ? 'border-border/20 bg-surface/10 opacity-30 pointer-events-none'
                              : d.has_trades
                              ? isPositive
                                ? 'border-emerald-600/40 bg-emerald-950/20 hover:bg-emerald-950/40 hover:border-emerald-500 cursor-pointer shadow-sm'
                                : isNegative
                                ? 'border-rose-600/40 bg-rose-950/20 hover:bg-rose-950/40 hover:border-rose-500 cursor-pointer shadow-sm'
                                : 'border-border bg-surface/40 hover:bg-surface/80 cursor-pointer'
                              : 'border-border/40 bg-surface/20 opacity-60 hover:opacity-100 hover:border-border'
                          } ${isToday ? 'ring-2 ring-purple-500 shadow-purple-500/20' : ''}`}
                        >
                          {/* Top Row: Date Number & Badge */}
                          <div className="flex items-center justify-between">
                            <span
                              className={`text-xs font-bold ${
                                isToday
                                  ? 'px-1.5 py-0.5 rounded bg-purple-600 text-white font-extrabold'
                                  : d.has_trades
                                  ? 'text-white'
                                  : 'text-gray-400'
                              }`}
                            >
                              {d.day_number}
                            </span>

                            {d.has_trades && (
                              <span
                                className={`w-2 h-2 rounded-full ${
                                  isPositive
                                    ? 'bg-emerald-400 ring-4 ring-emerald-400/20'
                                    : isNegative
                                    ? 'bg-rose-500 ring-4 ring-rose-500/20'
                                    : 'bg-gray-400'
                                }`}
                              />
                            )}
                          </div>

                          {/* Middle: Net P&L Amount */}
                          <div className="my-1">
                            {d.has_trades ? (
                              <div>
                                <div className={`text-xs sm:text-sm font-extrabold ${getPnlColor(d.net_pnl)}`}>
                                  {formatCurrency(d.net_pnl)}
                                </div>
                                <div className="text-[10px] text-gray-400">
                                  {d.wins}W • {d.losses}L
                                </div>
                              </div>
                            ) : d.is_future ? (
                              <div className="text-[10px] text-gray-600 italic">Upcoming</div>
                            ) : (
                              <div className="text-[10px] text-gray-500">No trades</div>
                            )}
                          </div>

                          {/* Bottom Row: Trades count & charges */}
                          <div className="flex items-center justify-between text-[9px] text-gray-500 pt-1 border-t border-border/30">
                            {d.has_trades ? (
                              <>
                                <span className="font-semibold text-gray-300">
                                  {d.trades_count} trade{d.trades_count > 1 ? 's' : ''}
                                </span>
                                <span className="text-gray-500">Chg ₹{d.total_charges.toFixed(0)}</span>
                              </>
                            ) : (
                              <span className="text-gray-600">--</span>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>

            {/* Calendar Legend */}
            <div className="flex flex-wrap items-center justify-between gap-4 mt-6 pt-4 border-t border-border/50 text-[11px] font-mono text-gray-400">
              <div className="flex flex-wrap items-center gap-4">
                <div className="flex items-center space-x-1.5">
                  <span className="w-2.5 h-2.5 rounded bg-emerald-500" />
                  <span>Net Profitable Day (Gross - Charges - Slippage &gt; 0)</span>
                </div>
                <div className="flex items-center space-x-1.5">
                  <span className="w-2.5 h-2.5 rounded bg-rose-500" />
                  <span>Net Loss Day (&lt; 0)</span>
                </div>
                <div className="flex items-center space-x-1.5">
                  <span className="w-2.5 h-2.5 rounded bg-gray-500" />
                  <span>No Trades / Neutral (Breaks streak; never counts as loss)</span>
                </div>
                <div className="flex items-center space-x-1.5">
                  <span className="w-2.5 h-2.5 rounded bg-purple-500" />
                  <span>Today</span>
                </div>
              </div>

              <div className="text-gray-500 text-[10px]">
                Click any trading day to inspect trade-by-trade ledger with all 26 audited parameters
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 2. YEARLY VIEW */}
      {/* ========================================================================= */}
      {viewMode === 'YEARLY' && (
        <div className="space-y-6">
          {/* Year Navigation Bar */}
          <div className="bg-card border border-border rounded-xl p-4 flex flex-col sm:flex-row items-center justify-between gap-4">
            <div className="flex items-center space-x-2 font-mono">
              <button
                onClick={handlePrevYear}
                className="p-2 rounded-lg bg-surface border border-border hover:bg-surface/80 text-gray-300 hover:text-white transition-all"
                title="Previous Year"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>

              <div className="flex items-center space-x-2 bg-surface border border-border px-3 py-1.5 rounded-lg">
                <select
                  value={year}
                  onChange={(e) => setYear(parseInt(e.target.value, 10))}
                  className="bg-transparent text-purple-400 font-bold text-sm focus:outline-none cursor-pointer"
                >
                  {[2024, 2025, 2026, 2027].map((y) => (
                    <option key={y} value={y} className="bg-surface text-white">
                      {y} Full Year
                    </option>
                  ))}
                </select>
              </div>

              <button
                onClick={handleNextYear}
                className="p-2 rounded-lg bg-surface border border-border hover:bg-surface/80 text-gray-300 hover:text-white transition-all"
                title="Next Year"
              >
                <ChevronRight className="w-4 h-4" />
              </button>

              <button
                onClick={() => setYear(currentIstYear)}
                className="px-3 py-1.5 rounded-lg bg-surface border border-border hover:bg-surface/80 text-gray-300 hover:text-white text-xs font-semibold"
              >
                Current Year
              </button>
            </div>

            {/* Annual Reconciliation Math */}
            {ySummary && (
              <div className="text-xs font-mono text-gray-400 flex flex-wrap items-center gap-3">
                <span>
                  Gross: <strong className="text-emerald-400">+₹{ySummary.annual_gross_profit.toFixed(2)}</strong>
                </span>
                <span>•</span>
                <span>
                  Loss: <strong className="text-rose-400">-₹{ySummary.annual_gross_loss.toFixed(2)}</strong>
                </span>
                <span>•</span>
                <span>
                  Charges: <strong className="text-gray-300">₹{ySummary.annual_charges.toFixed(2)}</strong>
                </span>
                <span>=</span>
                <span className={`px-2 py-0.5 rounded font-bold ${getPnlBg(ySummary.annual_net_pnl)}`}>
                  Net {formatCurrency(ySummary.annual_net_pnl)}
                </span>
              </div>
            )}
          </div>

          {/* Annual Summary Top Banner */}
          {ySummary && (
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
              <div className="bg-card border border-border rounded-xl p-4 font-mono">
                <span className="text-[11px] text-gray-400 block mb-1">ANNUAL NET P&amp;L</span>
                <div className={`text-xl font-bold ${getPnlColor(ySummary.annual_net_pnl)}`}>
                  {formatCurrency(ySummary.annual_net_pnl)}
                </div>
                <span className="text-[10px] text-gray-500">
                  {ySummary.profitable_months} Green / {ySummary.losing_months} Red Months
                </span>
              </div>

              <div className="bg-card border border-border rounded-xl p-4 font-mono">
                <span className="text-[11px] text-gray-400 block mb-1">TRADING DAYS</span>
                <div className="text-xl font-bold text-white">
                  {ySummary.winning_days + ySummary.losing_days} Traded
                </div>
                <span className="text-[10px] text-gray-500">
                  <span className="text-emerald-400">{ySummary.winning_days}W</span> •{' '}
                  <span className="text-rose-400">{ySummary.losing_days}L</span>
                </span>
              </div>

              <div className="bg-card border border-border rounded-xl p-4 font-mono">
                <span className="text-[11px] text-gray-400 block mb-1">TOTAL TRADES</span>
                <div className="text-xl font-bold text-white">{ySummary.total_trades}</div>
                <span className="text-[10px] text-gray-500">Charges: ₹{ySummary.annual_charges.toFixed(0)}</span>
              </div>

              <div className="bg-card border border-border rounded-xl p-4 font-mono">
                <span className="text-[11px] text-gray-400 block mb-1">BEST MONTH</span>
                <div className="text-xl font-bold text-emerald-400">
                  {ySummary.best_month?.net_pnl > 0 ? `+₹${ySummary.best_month.net_pnl.toFixed(0)}` : '₹0.00'}
                </div>
                <span className="text-[10px] text-gray-500 truncate block">
                  {ySummary.best_month?.month_name || 'N/A'}
                </span>
              </div>

              <div className="bg-card border border-border rounded-xl p-4 font-mono">
                <span className="text-[11px] text-gray-400 block mb-1">WORST MONTH</span>
                <div className="text-xl font-bold text-rose-400">
                  {ySummary.worst_month?.net_pnl < 0 ? `-₹${Math.abs(ySummary.worst_month.net_pnl).toFixed(0)}` : '₹0.00'}
                </div>
                <span className="text-[10px] text-gray-500 truncate block">
                  {ySummary.worst_month?.month_name || 'N/A'}
                </span>
              </div>

              <div className="bg-card border border-border rounded-xl p-4 font-mono">
                <span className="text-[11px] text-gray-400 block mb-1">MAX DRAWDOWN STREAK</span>
                <div className="text-xl font-bold text-rose-400">
                  {ySummary.max_consecutive_losing_days} Days
                </div>
                <span className="text-[10px] text-gray-500">Max win: {ySummary.max_consecutive_winning_days} days</span>
              </div>
            </div>
          )}

          {/* 12-Month Cards Grid */}
          <div className="bg-card border border-border rounded-xl p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-bold text-white text-sm font-mono flex items-center gap-2">
                <CalendarRange className="w-4 h-4 text-purple-400" />
                {year} Annual Performance by Month (Click any card to inspect daily calendar)
              </h3>
            </div>

            {loading ? (
              <div className="py-24 text-center font-mono text-xs text-gray-500">
                <Activity className="w-6 h-6 text-purple-400 animate-spin mx-auto mb-2" />
                Aggregating 12 months for {year}...
              </div>
            ) : !yearlyData || yearlyData.months.length === 0 ? (
              <div className="py-24 text-center font-mono text-xs text-gray-500">
                No annual trade data recorded for {year}.
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 font-mono">
                {yearlyData.months.map((m: YearlyMonthItem) => {
                  const isPositive = m.net_pnl > 0;
                  const isNegative = m.net_pnl < 0;
                  const hasActivity = m.trades_count > 0;

                  return (
                    <div
                      key={m.month}
                      onClick={() => handleSelectMonthFromYearly(m.month)}
                      className={`p-4 rounded-xl border flex flex-col justify-between transition-all cursor-pointer select-none group ${
                        m.is_future
                          ? 'border-border/30 bg-surface/10 opacity-35 hover:opacity-50'
                          : hasActivity
                          ? isPositive
                            ? 'border-emerald-600/40 bg-emerald-950/20 hover:bg-emerald-950/40 hover:border-emerald-500'
                            : isNegative
                            ? 'border-rose-600/40 bg-rose-950/20 hover:bg-rose-950/40 hover:border-rose-500'
                            : 'border-border bg-surface/40 hover:bg-surface/80'
                          : 'border-border/40 bg-surface/20 hover:bg-surface/50 opacity-60'
                      }`}
                    >
                      {/* Top Row: Month Name & Status Badge */}
                      <div className="flex items-center justify-between mb-2">
                        <span className="font-bold text-white text-sm group-hover:text-purple-400 transition-colors">
                          {m.month_name}
                        </span>
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                            m.is_future
                              ? 'bg-gray-800 text-gray-500'
                              : hasActivity
                              ? isPositive
                                ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                                : isNegative
                                ? 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                                : 'bg-gray-700/30 text-gray-400'
                              : 'bg-surface text-gray-500'
                          }`}
                        >
                          {m.status}
                        </span>
                      </div>

                      {/* Middle: Net P&L */}
                      <div className="my-2">
                        <div className={`text-lg font-extrabold ${getPnlColor(m.net_pnl)}`}>
                          {hasActivity ? formatCurrency(m.net_pnl) : '₹0.00'}
                        </div>
                        {hasActivity ? (
                          <div className="text-[11px] text-gray-400 mt-1 flex items-center justify-between">
                            <span>Win Rate: {m.win_rate.toFixed(0)}%</span>
                            <span>
                              {m.winning_days}W • {m.losing_days}L
                            </span>
                          </div>
                        ) : (
                          <div className="text-[11px] text-gray-600 mt-1 italic">
                            {m.is_future ? 'Upcoming' : 'No recorded trades'}
                          </div>
                        )}
                      </div>

                      {/* Bottom: Trades & Charges */}
                      <div className="pt-2 border-t border-border/40 flex items-center justify-between text-[10px] text-gray-500">
                        <span>{m.trades_count} Trades</span>
                        <span className="text-purple-400 group-hover:translate-x-0.5 transition-transform flex items-center gap-1 font-semibold">
                          Open <ArrowRight className="w-3 h-3" />
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 3. CUSTOM DATE RANGE VIEW */}
      {/* ========================================================================= */}
      {viewMode === 'CUSTOM' && (
        <div className="space-y-6">
          {/* Custom Date Range Picker Bar */}
          <div className="bg-card border border-border rounded-xl p-5">
            <h3 className="font-bold text-white text-sm font-mono mb-3 flex items-center gap-2">
              <Filter className="w-4 h-4 text-purple-400" />
              Custom Date Range Filter &amp; Audit
            </h3>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 font-mono text-xs">
              <div>
                <label className="text-gray-400 block mb-1">Start Date (IST):</label>
                <input
                  type="date"
                  value={customStart}
                  onChange={(e) => setCustomStart(e.target.value)}
                  className="w-full bg-surface border border-border rounded px-3 py-1.5 text-white font-bold focus:outline-none focus:border-purple-500"
                />
              </div>

              <div>
                <label className="text-gray-400 block mb-1">End Date (IST):</label>
                <input
                  type="date"
                  value={customEnd}
                  onChange={(e) => setCustomEnd(e.target.value)}
                  className="w-full bg-surface border border-border rounded px-3 py-1.5 text-white font-bold focus:outline-none focus:border-purple-500"
                />
              </div>

              <div className="flex items-end space-x-2">
                <button
                  onClick={loadCustomData}
                  className="flex-1 bg-purple-600 hover:bg-purple-500 text-white font-bold py-2 px-4 rounded transition-all shadow-sm flex items-center justify-center gap-2"
                >
                  <Filter className="w-3.5 h-3.5" /> Apply Filter
                </button>
                <button
                  onClick={() => {
                    const d = new Date();
                    d.setDate(d.getDate() - 30);
                    setCustomStart(d.toISOString().slice(0, 10));
                    setCustomEnd(new Date().toISOString().slice(0, 10));
                  }}
                  className="bg-surface hover:bg-surface/80 border border-border text-gray-300 py-2 px-3 rounded"
                  title="Reset to Last 30 Days"
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                </button>
              </div>

              <div className="flex items-end">
                <button
                  onClick={handleExportCustomCsv}
                  className="w-full bg-surface hover:bg-surface/80 border border-border text-gray-300 hover:text-white font-bold py-2 px-4 rounded flex items-center justify-center gap-2"
                >
                  <Download className="w-3.5 h-3.5 text-blue-400" /> Export Range CSV
                </button>
              </div>
            </div>
          </div>

          {/* Custom Range Summary Strip */}
          {customData && (
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
              <div className="bg-card border border-border rounded-xl p-4 font-mono">
                <span className="text-[11px] text-gray-400 block mb-1">PERIOD NET P&amp;L</span>
                <div className={`text-xl font-bold ${getPnlColor(customData.net_pnl)}`}>
                  {formatCurrency(customData.net_pnl)}
                </div>
                <span className="text-[10px] text-gray-500">
                  Gross: ₹{customData.gross_profit.toFixed(0)} | Loss: ₹{customData.gross_loss.toFixed(0)}
                </span>
              </div>

              <div className="bg-card border border-border rounded-xl p-4 font-mono">
                <span className="text-[11px] text-gray-400 block mb-1">WIN RATE</span>
                <div className="text-xl font-bold text-blue-400">{customData.win_rate.toFixed(1)}%</div>
                <span className="text-[10px] text-gray-500">
                  {customData.winning_days}W / {customData.losing_days}L Trading Days
                </span>
              </div>

              <div className="bg-card border border-border rounded-xl p-4 font-mono">
                <span className="text-[11px] text-gray-400 block mb-1">TOTAL TRADES</span>
                <div className="text-xl font-bold text-white">{customData.total_trades}</div>
                <span className="text-[10px] text-gray-500">{customData.total_trading_days} Days Active</span>
              </div>

              <div className="bg-card border border-border rounded-xl p-4 font-mono">
                <span className="text-[11px] text-gray-400 block mb-1">TOTAL CHARGES</span>
                <div className="text-xl font-bold text-gray-300">₹{customData.total_charges.toFixed(2)}</div>
                <span className="text-[10px] text-gray-500">₹10 entry + ₹10 exit flat</span>
              </div>

              <div className="bg-card border border-border rounded-xl p-4 font-mono">
                <span className="text-[11px] text-gray-400 block mb-1">TOTAL SLIPPAGE</span>
                <div className="text-xl font-bold text-gray-300">₹{customData.total_slippage.toFixed(2)}</div>
                <span className="text-[10px] text-gray-500">Audited execution cost</span>
              </div>

              <div className="bg-card border border-border rounded-xl p-4 font-mono">
                <span className="text-[11px] text-gray-400 block mb-1">MAX WIN STREAK</span>
                <div className="text-xl font-bold text-emerald-400">
                  {customData.streaks?.max_consecutive_wins || 0} Days
                </div>
                <span className="text-[10px] text-gray-500">
                  Max loss: {customData.streaks?.max_consecutive_losses || 0} days
                </span>
              </div>
            </div>
          )}

          {/* Daily Breakdown for Custom Range */}
          {customData?.daily_summary && customData.daily_summary.length > 0 && (
            <div className="bg-card border border-border rounded-xl p-5">
              <h3 className="font-bold text-white text-sm font-mono mb-3">Daily Breakdown in Selected Range</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-xs font-mono text-left">
                  <thead>
                    <tr className="bg-surface/60 border-b border-border text-gray-400 uppercase text-[11px]">
                      <th className="px-3 py-2">Trading Date</th>
                      <th className="px-3 py-2 text-right">Trades</th>
                      <th className="px-3 py-2 text-right">Wins</th>
                      <th className="px-3 py-2 text-right">Losses</th>
                      <th className="px-3 py-2 text-right">Win Rate</th>
                      <th className="px-3 py-2 text-right">Gross Profit</th>
                      <th className="px-3 py-2 text-right">Gross Loss</th>
                      <th className="px-3 py-2 text-right">Charges</th>
                      <th className="px-3 py-2 text-right">Net P&amp;L</th>
                      <th className="px-3 py-2 text-center">Inspect</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/40">
                    {customData.daily_summary.map((d: any, idx: number) => (
                      <tr key={idx} className="hover:bg-surface/40">
                        <td className="px-3 py-2 text-white font-bold">{d.date}</td>
                        <td className="px-3 py-2 text-right">{d.trades_count}</td>
                        <td className="px-3 py-2 text-right text-emerald-400">{d.wins}</td>
                        <td className="px-3 py-2 text-right text-rose-400">{d.losses}</td>
                        <td className="px-3 py-2 text-right text-blue-400">{d.win_rate.toFixed(1)}%</td>
                        <td className="px-3 py-2 text-right text-emerald-400">+₹{d.gross_profit.toFixed(2)}</td>
                        <td className="px-3 py-2 text-right text-rose-400">-₹{d.gross_loss.toFixed(2)}</td>
                        <td className="px-3 py-2 text-right text-gray-400">₹{d.total_charges.toFixed(2)}</td>
                        <td className={`px-3 py-2 text-right font-bold ${getPnlColor(d.net_pnl)}`}>
                          {formatCurrency(d.net_pnl)}
                        </td>
                        <td className="px-3 py-2 text-center">
                          <button
                            onClick={() => loadDailyDetail(d.date)}
                            className="px-2 py-1 rounded bg-surface border border-border hover:bg-surface/80 text-purple-400 hover:text-purple-300 text-[10px] font-bold"
                          >
                            Inspect
                          </button>
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

      {/* ========================================================================= */}
      {/* 4. DAILY DETAIL DRAWER / MODAL */}
      {/* ========================================================================= */}
      {selectedDate && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-card border border-border rounded-2xl w-full max-w-5xl max-h-[90vh] flex flex-col shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            {/* Modal Header */}
            <div className="px-6 py-4 border-b border-border flex items-center justify-between bg-surface/40">
              <div className="flex items-center space-x-3">
                <div className="p-2 rounded-xl bg-purple-600/10 text-purple-400 border border-purple-500/30">
                  <CalendarIcon className="w-5 h-5" />
                </div>
                <div>
                  <div className="flex items-center space-x-2">
                    <h3 className="text-base font-bold text-white font-mono">Daily Performance Audit: {selectedDate}</h3>
                    {dailyDetail && (
                      <span className={`px-2 py-0.5 rounded text-xs font-bold font-mono ${getPnlBg(dailyDetail.net_pnl)}`}>
                        {formatCurrency(dailyDetail.net_pnl)}
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-gray-400 font-mono">
                    All 26 audited trade ledger parameters for trades executed on this date
                  </p>
                </div>
              </div>

              <div className="flex items-center space-x-2">
                <button
                  onClick={() => handleExportDailyCsv(selectedDate)}
                  className="px-3 py-1.5 rounded-lg bg-surface border border-border hover:bg-surface/80 text-gray-300 hover:text-white text-xs font-mono font-semibold flex items-center gap-1.5"
                  title="Export Day Trades CSV"
                >
                  <Download className="w-3.5 h-3.5 text-blue-400" />
                  Export Day CSV
                </button>
                <button
                  onClick={() => {
                    setSelectedDate(null);
                    setDailyDetail(null);
                  }}
                  className="p-1.5 rounded-lg bg-surface border border-border text-gray-400 hover:text-white transition-colors"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            {/* Modal Body */}
            <div className="p-6 overflow-y-auto space-y-6">
              {loadingDaily ? (
                <div className="py-24 text-center font-mono text-xs text-gray-500">
                  <Activity className="w-6 h-6 text-purple-400 animate-spin mx-auto mb-2" />
                  Loading trade ledger for {selectedDate}...
                </div>
              ) : !dailyDetail || !dailyDetail.has_trades ? (
                <div className="py-12 px-6 text-center font-mono space-y-3">
                  <div className="inline-flex p-3 rounded-xl bg-amber-500/10 text-amber-300 border border-amber-500/30">
                    <AlertCircle className="w-6 h-6" />
                  </div>
                  <h4 className="text-sm font-bold text-white">
                    {dailyDetail?.status === 'NO_TRADE'
                      ? 'No strategy entries generated on this trading day.'
                      : dailyDetail?.status === 'HOLIDAY'
                      ? `Exchange Holiday: ${dailyDetail?.status_description || 'Closed'}`
                      : dailyDetail?.status === 'WEEKEND'
                      ? 'Exchange Closed: Weekend'
                      : dailyDetail?.status_description || `No completed trades found for ${selectedDate}.`}
                  </h4>
                  <p className="text-xs text-gray-400 max-w-md mx-auto">
                    {dailyDetail?.status === 'NO_TRADE'
                      ? 'All historical market data was evaluated during exchange session hours (09:20 - 15:15 IST), but no strategy indicators satisfied entry conditions.'
                      : 'No position activity recorded in the trading ledger for this date.'}
                  </p>
                </div>
              ) : (
                <>
                  {/* Daily KPI Strip */}
                  <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 font-mono">
                    <div className="bg-surface/60 border border-border rounded-xl p-3">
                      <span className="text-[10px] text-gray-400 block">NET P&amp;L</span>
                      <div className={`text-base font-bold ${getPnlColor(dailyDetail.net_pnl)}`}>
                        {formatCurrency(dailyDetail.net_pnl)}
                      </div>
                      <span className="text-[9px] text-gray-500">After ₹{dailyDetail.total_charges.toFixed(0)} chgs</span>
                    </div>

                    <div className="bg-surface/60 border border-border rounded-xl p-3">
                      <span className="text-[10px] text-gray-400 block">GROSS P&amp;L</span>
                      <div className="text-base font-bold text-white">
                        <span className="text-emerald-400">+₹{dailyDetail.gross_profit.toFixed(0)}</span> /{' '}
                        <span className="text-rose-400">-₹{dailyDetail.gross_loss.toFixed(0)}</span>
                      </div>
                      <span className="text-[9px] text-gray-500">Before charges/slippage</span>
                    </div>

                    <div className="bg-surface/60 border border-border rounded-xl p-3">
                      <span className="text-[10px] text-gray-400 block">WIN RATE</span>
                      <div className="text-base font-bold text-blue-400">{dailyDetail.win_rate.toFixed(1)}%</div>
                      <span className="text-[9px] text-gray-500">
                        {dailyDetail.wins} Wins / {dailyDetail.losses} Losses
                      </span>
                    </div>

                    <div className="bg-surface/60 border border-border rounded-xl p-3">
                      <span className="text-[10px] text-gray-400 block">AVG WIN / LOSS</span>
                      <div className="text-base font-bold text-white">
                        <span className="text-emerald-400">+₹{dailyDetail.avg_win.toFixed(0)}</span> /{' '}
                        <span className="text-rose-400">-₹{dailyDetail.avg_loss.toFixed(0)}</span>
                      </div>
                      <span className="text-[9px] text-gray-500">Per traded contract</span>
                    </div>

                    <div className="bg-surface/60 border border-border rounded-xl p-3">
                      <span className="text-[10px] text-gray-400 block">LARGEST WIN / LOSS</span>
                      <div className="text-base font-bold text-white">
                        <span className="text-emerald-400">+₹{dailyDetail.largest_win.toFixed(0)}</span> /{' '}
                        <span className="text-rose-400">-₹{dailyDetail.largest_loss.toFixed(0)}</span>
                      </div>
                      <span className="text-[9px] text-gray-500">Single trade peak</span>
                    </div>

                    <div className="bg-surface/60 border border-border rounded-xl p-3">
                      <span className="text-[10px] text-gray-400 block">AVG HOLDING TIME</span>
                      <div className="text-base font-bold text-purple-400">
                        {dailyDetail.avg_holding_time.toFixed(1)} mins
                      </div>
                      <span className="text-[9px] text-gray-500">
                        Max: {dailyDetail.max_holding_time}m | Min: {dailyDetail.min_holding_time}m
                      </span>
                    </div>
                  </div>

                  {/* Trade Ledger Table */}
                  <div className="border border-border rounded-xl overflow-hidden">
                    <div className="bg-surface/80 px-4 py-2.5 border-b border-border flex items-center justify-between text-xs font-mono">
                      <span className="font-bold text-white">
                        Executed Trades on {selectedDate} ({dailyDetail.trades.length} positions closed)
                      </span>
                      <span className="text-gray-400 text-[11px]">
                        Reconciliation: Initial Capital + Net P&amp;L = Final Capital
                      </span>
                    </div>

                    <div className="overflow-x-auto max-h-[420px]">
                      <table className="w-full text-xs font-mono text-left">
                        <thead className="sticky top-0 bg-surface z-10 border-b border-border text-gray-400 uppercase text-[10px]">
                          <tr>
                            <th className="px-3 py-2">#</th>
                            <th className="px-3 py-2">Entry IST</th>
                            <th className="px-3 py-2">Exit IST</th>
                            <th className="px-3 py-2 text-right">Hold</th>
                            <th className="px-3 py-2">Contract</th>
                            <th className="px-3 py-2">Strategy</th>
                            <th className="px-3 py-2 text-right">Entry (₹)</th>
                            <th className="px-3 py-2 text-right">SL (Trigger)</th>
                            <th className="px-3 py-2 text-right">Target (Trigger)</th>
                            <th className="px-3 py-2 text-right">Exit (₹)</th>
                            <th className="px-3 py-2 text-right">Qty</th>
                            <th className="px-3 py-2">Exit Reason</th>
                            <th className="px-3 py-2 text-right">Gross (₹)</th>
                            <th className="px-3 py-2 text-right">Charges</th>
                            <th className="px-3 py-2 text-right">Net P&amp;L</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-border/40">
                          {dailyDetail.trades.map((t: any, idx: number) => {
                            const isExpanded = expandedTradeIdx === idx;
                            return (
                              <React.Fragment key={idx}>
                                <tr
                                  onClick={() => setExpandedTradeIdx(isExpanded ? null : idx)}
                                  className="hover:bg-surface/50 cursor-pointer transition-colors"
                                >
                                  <td className="px-3 py-2 text-gray-400">#{t.trade_num || idx + 1}</td>
                                  <td className="px-3 py-2 text-gray-300">
                                    {formatIST(t.entry_time)}
                                  </td>
                                  <td className="px-3 py-2 text-gray-300">
                                    {formatIST(t.exit_time)}
                                  </td>
                                  <td className="px-3 py-2 text-right text-gray-400">{t.holding_time_minutes}m</td>
                                  <td className="px-3 py-2 font-bold text-white">{t.option_symbol}</td>
                                  <td className="px-3 py-2">
                                    <span className="px-1.5 py-0.5 rounded text-[9px] bg-purple-500/10 text-purple-300 border border-purple-500/20">
                                      {t.strategy_id}
                                    </span>
                                  </td>
                                  <td className="px-3 py-2 text-right text-white">₹{t.entry_price.toFixed(2)}</td>
                                  <td className="px-3 py-2 text-right text-rose-300">
                                    ₹{(t.sl_trigger_price ?? t.stop_price ?? 0).toFixed(2)}
                                  </td>
                                  <td className="px-3 py-2 text-right text-emerald-300">
                                    ₹{(t.target_trigger_price ?? t.target_price ?? 0).toFixed(2)}
                                  </td>
                                  <td className="px-3 py-2 text-right text-blue-400 font-bold">
                                    ₹{t.exit_price.toFixed(2)}
                                  </td>
                                  <td className="px-3 py-2 text-right">{t.quantity}</td>
                                  <td className="px-3 py-2">
                                    <span
                                      className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                                        t.exit_reason === 'TARGET'
                                          ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                                          : t.exit_reason === 'AUTO_CLOSE_3_20_PM'
                                          ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                                          : t.exit_reason === 'UT_SELL_SIGNAL'
                                          ? 'bg-blue-500/20 text-blue-300 border border-blue-500/30'
                                          : 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
                                      }`}
                                    >
                                      {t.exit_reason}
                                    </span>
                                  </td>
                                  <td className={`px-3 py-2 text-right font-semibold ${getPnlColor(t.gross_pnl)}`}>
                                    {formatCurrency(t.gross_pnl)}
                                  </td>
                                  <td className="px-3 py-2 text-right text-gray-400">
                                    ₹{Number(t.charges ?? 20.0).toFixed(2)}
                                  </td>
                                  <td className={`px-3 py-2 text-right font-bold ${getPnlColor(t.net_pnl)}`}>
                                    {formatCurrency(t.net_pnl)}
                                  </td>
                                </tr>

                                {/* Expanded Trade Inspector */}
                                {isExpanded && (
                                  <tr className="bg-surface/90">
                                    <td colSpan={15} className="px-4 py-3 border-t border-b border-purple-500/30">
                                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs font-mono">
                                        <div>
                                          <span className="text-gray-500 block text-[10px]">ENTRY ORDER</span>
                                          <span className="text-white">ID: #{t.entry_order_id || t.id || 'N/A'}</span>
                                          <span className="text-gray-400 block text-[10px]">
                                            Entry Chg: ₹{Number(t.entry_charges ?? 10.0).toFixed(2)}
                                          </span>
                                        </div>
                                        <div>
                                          <span className="text-gray-500 block text-[10px]">EXIT ORDER</span>
                                          <span className="text-white">ID: #{t.exit_order_id || 'N/A'}</span>
                                          <span className="text-gray-400 block text-[10px]">
                                            Exit Chg: ₹{Number(t.exit_charges ?? 10.0).toFixed(2)}
                                          </span>
                                        </div>
                                        <div>
                                          <span className="text-gray-500 block text-[10px]">SLIPPAGE AUDIT</span>
                                          <span className="text-white">₹{Number(t.slippage_cost || 0).toFixed(2)}</span>
                                          <span className="text-gray-400 block text-[10px]">
                                            Mode: {t.execution_mode || 'TRIGGER_PRICE'}
                                          </span>
                                        </div>
                                        <div>
                                          <span className="text-gray-500 block text-[10px]">P&amp;L RECONCILIATION</span>
                                          <span className="text-emerald-400">
                                            ₹{t.gross_pnl.toFixed(2)} - ₹{t.charges.toFixed(2)} ={' '}
                                            <strong className={getPnlColor(t.net_pnl)}>₹{t.net_pnl.toFixed(2)}</strong>
                                          </span>
                                        </div>
                                      </div>
                                    </td>
                                  </tr>
                                )}
                              </React.Fragment>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </>
              )}
            </div>

            {/* Modal Footer */}
            <div className="px-6 py-3 border-t border-border flex items-center justify-between bg-surface/30 font-mono text-xs text-gray-500">
              <span>Timezone: Asia/Kolkata (IST, UTC+5:30)</span>
              <button
                onClick={() => {
                  setSelectedDate(null);
                  setDailyDetail(null);
                }}
                className="px-4 py-1.5 rounded-lg bg-surface border border-border hover:bg-surface/80 text-white font-semibold"
              >
                Close Audit
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
