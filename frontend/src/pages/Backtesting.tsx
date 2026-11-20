import React, { useEffect, useState } from 'react';
import {
  PlayCircle,
  BarChart3,
  AlertCircle,
  Download,
  Zap,
  Layers,
  Sliders,
  TrendingUp,
  TrendingDown,
  Calendar,
  Clock,
  ShieldCheck,
  Database,
  CheckCircle2,
  HelpCircle,
  RotateCcw,
  History,
  PieChart,
  Scale,
  Eye,
  X,
  Activity
} from 'lucide-react';
import { BacktestResult, StrategyType, Timeframe, BacktestRunItem, Candle, ChartTradeMarker, DateWiseSummaryItem } from '../types';
import { api } from '../services/api';
import { StatCard } from '../components/StatCard';
import { formatCurrency, formatIST, formatISTDate, getPnlColor, normalizeDailyAnalytics, formatCharges } from '../utils/formatters';
import { PerformanceCalendar } from '../components/PerformanceCalendar';
import { ComparisonAuditView } from '../components/ComparisonAuditView';
import { ChartComponent } from '../components/ChartComponent';
import { wsClient } from '../services/websocket';

interface BacktestingProps {
  onNavigateToAnalytics?: (runId: number) => void;
}

export const Backtesting: React.FC<BacktestingProps> = ({ onNavigateToAnalytics }) => {
  const [strategyId, setStrategyId] = useState<StrategyType>('UT_BOT');
  const [instrument, setInstrument] = useState<string>('NIFTY ATM CE');
  const [timeframe, setTimeframe] = useState<Timeframe>('1m');
  const [durationOption, setDurationOption] = useState<string>('5');
  const [startDate, setStartDate] = useState<string>('2026-11-09');
  const [endDate, setEndDate] = useState<string>('2026-11-13');
  const [dataSource, setDataSource] = useState<'SYNTHETIC_TEST' | 'REAL_MARKET'>('SYNTHETIC_TEST');
  const [initialCapital, setInitialCapital] = useState<number>(100000.0);
  const [slippage, setSlippage] = useState<number>(0.10);
  const [activePageTab, setActivePageTab] = useState<'BACKTEST' | 'COMPARISON_AUDIT'>('BACKTEST');
  const [resultsTab, setResultsTab] = useState<'METRICS' | 'CALENDAR'>('METRICS');

  // Past Backtest Runs History State
  const [pastRuns, setPastRuns] = useState<BacktestRunItem[]>([]);
  const [loadingRuns, setLoadingRuns] = useState<boolean>(false);

  // Day Inspection Modal State
  const [inspectDate, setInspectDate] = useState<string | null>(null);
  const [inspectItem, setInspectItem] = useState<DateWiseSummaryItem | null>(null);
  const [inspectCandles, setInspectCandles] = useState<Candle[]>([]);
  const [inspectMarkers, setInspectMarkers] = useState<ChartTradeMarker[]>([]);
  const [loadingInspectChart, setLoadingInspectChart] = useState<boolean>(false);

  // UT Bot Specific Settings
  const [utLots, setUtLots] = useState<number>(5);
  const [utLotSize, setUtLotSize] = useState<number>(65);
  const [utKeyValue, setUtKeyValue] = useState<number>(1.0);
  const [utAtrPeriod, setUtAtrPeriod] = useState<number>(10);
  const [utUseHA, setUtUseHA] = useState<boolean>(false);
  const [utTarget, setUtTarget] = useState<number>(4.0);
  const [utStop, setUtStop] = useState<number>(2.0);
  const [utRiskCap, setUtRiskCap] = useState<boolean>(true);
  const [utSignalSource, setUtSignalSource] = useState<'CHART_INSTRUMENT' | 'NIFTY_INDEX'>('CHART_INSTRUMENT');
  const [exitOnUtSell, setExitOnUtSell] = useState<boolean>(true);
  const [executionMode, setExecutionMode] = useState<'TRIGGER_PRICE' | 'REALISTIC'>('TRIGGER_PRICE');

  // EMA Specific Settings
  const [emaLots, setEmaLots] = useState<number>(1);

  // Supertrend EMA Scalper Specific Settings
  const [stAtrPeriod, setStAtrPeriod] = useState<number>(10);
  const [stMultiplier, setStMultiplier] = useState<number>(3.0);
  const [stEmaFast, setStEmaFast] = useState<number>(9);
  const [stEmaSlow, setStEmaSlow] = useState<number>(21);
  const [stLots, setStLots] = useState<number>(5);
  const [stLotSize, setStLotSize] = useState<number>(65);
  const [stTargetNetProfit, setStTargetNetProfit] = useState<number>(200.0);
  const [stMaxLoss, setStMaxLoss] = useState<number>(1000.0);
  const [stDailyProfitTarget, setStDailyProfitTarget] = useState<number>(1000.0);
  const [stDailyLossLimit, setStDailyLossLimit] = useState<number>(-2000.0);

  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [showDiagnostics, setShowDiagnostics] = useState<boolean>(false);

  const isCustomRange = durationOption === 'custom';
  const effectiveDays = isCustomRange
    ? undefined
    : durationOption === 'today'
    ? 1
    : parseInt(durationOption, 10);

  const handleInspectDay = async (item: DateWiseSummaryItem) => {
    setInspectDate(item.date);
    setInspectItem(item);
    setLoadingInspectChart(true);
    try {
      const sym = result?.contract_symbol || result?.instrument || instrument;
      const runId = result?.run_id;
      const cRes = await api.getCandles({
        symbol: sym,
        timeframe: timeframe,
        mode: 'BACKTEST',
        runId: runId,
        startDate: item.date,
        endDate: item.date,
        limit: 1000
      });
      setInspectCandles(cRes.candles || []);

      const mRes = await api.getChartTradeMarkers({
        mode: 'BACKTEST',
        runId: runId,
        symbol: sym,
        startDate: item.date,
        endDate: item.date
      });
      setInspectMarkers(mRes.markers || []);
    } catch (err) {
      console.error('Failed to load day chart or markers', err);
      setInspectCandles([]);
      setInspectMarkers([]);
    } finally {
      setLoadingInspectChart(false);
    }
  };

  const loadRunDetails = async (runId: number) => {
    setLoading(true);
    setErrorMsg(null);
    try {
      const data = await api.getBacktestRunDetails(runId);
      if (data && data.run) {
        const r = data.run;
        const resObj: BacktestResult = {
          run_id: r.id,
          strategy_name: r.strategy_name,
          strategy_id: r.strategy_id || 'UT_BOT',
          instrument: r.instrument_symbol,
          contract_symbol: r.instrument_symbol,
          timeframe: r.timeframe || '1m',
          start_date: r.start_date,
          end_date: r.end_date,
          data_source: r.data_source,
          initial_capital: r.initial_capital,
          final_capital: r.final_capital,
          net_profit: r.net_profit,
          gross_profit: r.gross_profit || 0,
          gross_loss: r.gross_loss || 0,
          total_charges: r.total_charges || 0,
          total_trades: r.total_trades,
          winning_trades: r.winning_trades || 0,
          losing_trades: r.losing_trades || 0,
          win_rate: r.win_rate,
          profit_factor: r.profit_factor || 0,
          avg_profit: r.avg_profit || 0,
          avg_loss: r.avg_loss || 0,
          largest_win: r.largest_win || 0,
          largest_loss: r.largest_loss || 0,
          max_drawdown: r.max_drawdown || 0,
          max_drawdown_pct: r.max_drawdown_pct || 0,
          execution_mode: r.execution_mode || 'TRIGGER_PRICE',
          trades: data.trades || [],
          daily_summary: [],
          equity_curve: [],
        };
        setResult(resObj);
        localStorage.setItem('nextrade_active_backtest_run_id', String(runId));
        const url = new URL(window.location.href);
        url.searchParams.set('runId', String(runId));
        window.history.replaceState({}, '', url);
      }
    } catch (err: any) {
      console.error('Failed to load run details:', err);
      setErrorMsg(err.message || 'Failed to load run details');
    } finally {
      setLoading(false);
    }
  };

  const loadPastRuns = async () => {
    setLoadingRuns(true);
    try {
      const runs = await api.getBacktestRuns();
      setPastRuns(runs);

      // Auto-load saved run or latest run if none is currently displayed
      const urlParams = new URLSearchParams(window.location.search);
      const qRunId = urlParams.get('runId') || localStorage.getItem('nextrade_active_backtest_run_id');
      if (qRunId && !isNaN(Number(qRunId))) {
        await loadRunDetails(Number(qRunId));
      } else if (!result && runs && runs.length > 0) {
        const firstId = runs[0].id || runs[0].run_id;
        if (firstId) await loadRunDetails(firstId);
      }
    } catch (err) {
      console.error('Failed to load past backtest runs', err);
    } finally {
      setLoadingRuns(false);
    }
  };

  useEffect(() => {
    loadPastRuns();

    const unsub = wsClient.subscribe((msg: any) => {
      if (msg && msg.type === 'BACKTEST_COMPLETED') {
        loadPastRuns();
      }
    });
    return () => unsub();
  }, []);

  const handleRunBacktest = async () => {
    if (loading) return; // Prevent duplicate requests
    setLoading(true);
    setErrorMsg(null);
    try {
      const res = await api.runBacktest({
        strategy_id: strategyId,
        timeframe,
        instrument_symbol: instrument,
        days: effectiveDays,
        start_date: isCustomRange ? startDate : undefined,
        end_date: isCustomRange ? endDate : undefined,
        data_source: dataSource,
        use_synthetic_data: dataSource === 'SYNTHETIC_TEST',
        initial_capital: initialCapital,
        lots: strategyId === 'SUPERTREND_EMA' ? stLots : strategyId === 'UT_BOT' ? utLots : emaLots,
        lot_size: strategyId === 'SUPERTREND_EMA' ? stLotSize : utLotSize,
        target_points: strategyId === 'SUPERTREND_EMA' ? (stTargetNetProfit + 20) / (stLots * stLotSize) : utTarget,
        stop_points: strategyId === 'SUPERTREND_EMA' ? (stMaxLoss - 20) / (stLots * stLotSize) : utStop,
        max_loss_per_trade: strategyId === 'SUPERTREND_EMA' ? stMaxLoss : (utRiskCap ? 1000.0 : undefined),
        use_risk_cap: strategyId === 'SUPERTREND_EMA' ? true : utRiskCap,
        execution_mode: executionMode,
        exit_on_ut_sell_signal: exitOnUtSell,
        slippage_points: slippage,
        seed: 42,
        ut_bot: {
          key_value: utKeyValue,
          atr_period: utAtrPeriod,
          use_heikin_ashi: utUseHA,
          lots: utLots,
          lot_size: utLotSize,
          target_points: utTarget,
          stop_points: utStop,
          max_loss_per_trade: utRiskCap ? 1000.0 : null,
          signal_source: utSignalSource,
          exit_on_ut_sell_signal: exitOnUtSell,
          execution_mode: executionMode,
        },
        supertrend_ema: {
          atr_period: stAtrPeriod,
          multiplier: stMultiplier,
          ema_fast: stEmaFast,
          ema_slow: stEmaSlow,
          lots: stLots,
          lot_size: stLotSize,
          target_net_profit: stTargetNetProfit,
          max_loss_per_trade: stMaxLoss,
          daily_profit_target: stDailyProfitTarget,
          daily_loss_limit: stDailyLossLimit,
        },
      });
      setResult(res);
      if (res && res.run_id) {
        localStorage.setItem('nextrade_active_backtest_run_id', String(res.run_id));
        const url = new URL(window.location.href);
        url.searchParams.set('runId', String(res.run_id));
        window.history.replaceState({}, '', url);
      }
      loadPastRuns();
    } catch (e: any) {
      setErrorMsg(e.message || 'Backtest failed');
    } finally {
      setLoading(false);
    }
  };

  const handleExportCsv = () => {
    if (!result || !result.run_id) {
      alert('Please run a backtest first.');
      return;
    }
    const url = api.getBacktestCsvUrl(result.run_id);
    window.open(url, '_blank');
  };

  // Preview Calculations
  const previewQty =
    (strategyId === 'SUPERTREND_EMA' ? stLots : strategyId === 'UT_BOT' ? utLots : emaLots) *
    (strategyId === 'SUPERTREND_EMA' ? stLotSize : utLotSize);
  const stTheoreticalTargetPts = ((stTargetNetProfit + 20) / Math.max(1, previewQty)).toFixed(2);
  const stTheoreticalStopPts = ((stMaxLoss - 20) / Math.max(1, previewQty)).toFixed(2);

  const configuredStopPts = strategyId === 'SUPERTREND_EMA' ? parseFloat(stTheoreticalStopPts) : utStop;
  const effectiveStopPts =
    strategyId === 'SUPERTREND_EMA'
      ? parseFloat(stTheoreticalStopPts)
      : utRiskCap
      ? Math.min(configuredStopPts, 1000.0 / Math.max(1, previewQty))
      : configuredStopPts;
  const normalRisk = configuredStopPts * previewQty;
  const isCapped = utRiskCap && normalRisk > 1000.0;

  return (
    <div className="space-y-6">
      {/* Top View Selector Bar */}
      <div className="bg-card border border-border rounded-xl p-3 flex flex-wrap items-center justify-between gap-3 shadow-sm">
        <div className="bg-surface p-1 rounded-lg border border-border flex items-center space-x-1 text-xs font-mono font-bold">
          <button
            onClick={() => setActivePageTab('BACKTEST')}
            className={`px-3.5 py-1.5 rounded-md flex items-center gap-1.5 transition-all ${
              activePageTab === 'BACKTEST'
                ? 'bg-blue-600 text-white shadow-sm'
                : 'text-gray-400 hover:text-white hover:bg-surface/80'
            }`}
          >
            <PlayCircle className="w-3.5 h-3.5" />
            BACKTEST RUNNER
          </button>
          <button
            onClick={() => setActivePageTab('COMPARISON_AUDIT')}
            className={`px-3.5 py-1.5 rounded-md flex items-center gap-2 transition-all ${
              activePageTab === 'COMPARISON_AUDIT'
                ? 'bg-purple-600 text-white shadow-sm'
                : 'text-gray-400 hover:text-white hover:bg-surface/80'
            }`}
          >
            <Scale className="w-3.5 h-3.5 text-purple-300" />
            SYNTHETIC VS REAL AUDIT
            <span className="px-1.5 py-0.2 rounded text-[9px] bg-purple-950 text-purple-300 border border-purple-800">
              4-WAY MATRIX
            </span>
          </button>
        </div>

        <div className="text-xs font-mono text-gray-400 hidden sm:block">
          {activePageTab === 'BACKTEST'
            ? 'Interactive Single-Run Parameter & Strategy Engine'
            : 'Comparative 4-Way Root Cause & Market Dynamics Audit'}
        </div>
      </div>

      {activePageTab === 'COMPARISON_AUDIT' ? (
        <ComparisonAuditView />
      ) : (
        <>
          {/* Parameters Header */}
          <div className="bg-card border border-border rounded-xl p-5 shadow-lg">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
          <div className="flex items-center space-x-3">
            <div className="p-2.5 rounded-xl bg-purple-600/10 text-purple-400 border border-purple-500/30">
              <PlayCircle className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-white">Deterministic Multi-Strategy Backtesting Engine</h2>
              <p className="text-xs text-gray-400 font-mono">
                Execute reproducible simulations against historical NIFTY option premium candles with full charge accounting
              </p>
            </div>
          </div>

          {result && (
            <div className="flex items-center space-x-2">
              <span
                className={`text-xs px-3 py-1 rounded font-mono font-bold border ${
                  result.data_source === 'REAL_MARKET' || result.data_source === 'HISTORICAL_DATA'
                    ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                    : 'bg-purple-500/10 text-purple-400 border-purple-500/30'
                }`}
              >
                DATA: {result.data_source}
              </span>

              {result.run_id && (
                <button
                  onClick={handleExportCsv}
                  className="px-3 py-1 rounded bg-blue-600 hover:bg-blue-500 text-white font-mono text-xs font-bold flex items-center gap-1.5 transition-colors shadow-sm"
                >
                  <Download className="w-3.5 h-3.5" />
                  Export CSV
                </button>
              )}
            </div>
          )}
        </div>

        {/* Data Source Mode Selection */}
        <div className="mb-4 p-3 rounded-lg bg-surface/50 border border-border">
          <div className="flex items-center justify-between flex-wrap gap-2 mb-2">
            <span className="text-xs font-mono font-bold text-gray-300 flex items-center gap-1.5">
              <Database className="w-3.5 h-3.5 text-blue-400" /> Historical Data Feed Mode:
            </span>
            <span className="text-[11px] font-mono text-gray-400">
              {dataSource === 'SYNTHETIC_TEST'
                ? 'Deterministic Seeded Mode (Reproducible, No Broker Dependency)'
                : 'Kotak Neo Real Historical Mode (Authentic Broker Candles, Strict Zero-Fabrication)'}
            </span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs font-mono">
            <button
              type="button"
              disabled={loading}
              onClick={() => setDataSource('SYNTHETIC_TEST')}
              className={`p-2.5 rounded-lg border text-left transition-all ${
                dataSource === 'SYNTHETIC_TEST'
                  ? 'bg-purple-500/20 border-purple-500 text-purple-200 shadow-sm'
                  : 'bg-surface border-border text-gray-400 hover:text-white'
              }`}
            >
              <div className="font-bold flex items-center justify-between">
                <span>Deterministic Synthetic Test</span>
                {dataSource === 'SYNTHETIC_TEST' && <CheckCircle2 className="w-4 h-4 text-purple-400" />}
              </div>
              <p className="text-[11px] text-gray-400 mt-1">
                Fixed-seed realistic 1-minute NIFTY spot &amp; option candles. Always reproducible.
              </p>
            </button>

            <button
              type="button"
              disabled={loading}
              onClick={() => setDataSource('REAL_MARKET')}
              className={`p-2.5 rounded-lg border text-left transition-all ${
                dataSource === 'REAL_MARKET'
                  ? 'bg-emerald-500/20 border-emerald-500 text-emerald-200 shadow-sm'
                  : 'bg-surface border-border text-gray-400 hover:text-white'
              }`}
            >
              <div className="font-bold flex items-center justify-between">
                <span>Real Kotak Neo Historical Data</span>
                {dataSource === 'REAL_MARKET' && <CheckCircle2 className="w-4 h-4 text-emerald-400" />}
              </div>
              <p className="text-[11px] text-gray-400 mt-1">
                Fetches genuine historical 1-minute OHLCV candles from Kotak Neo API. Stops if unavailable.
              </p>
            </button>
          </div>
        </div>

        {/* Execution Mode Selection: Trigger-Price Mode vs Realistic Mode */}
        <div className="mb-4 p-3 rounded-lg bg-surface/50 border border-border">
          <div className="flex items-center justify-between flex-wrap gap-2 mb-2">
            <span className="text-xs font-mono font-bold text-gray-300 flex items-center gap-1.5">
              <Sliders className="w-3.5 h-3.5 text-amber-400" /> Execution Mode &amp; Slippage Model:
            </span>
            <span className="text-[11px] font-mono text-gray-400">
              {executionMode === 'TRIGGER_PRICE'
                ? 'Trigger-Price Mode: Exact SL/Target price fills, zero artificial slippage'
                : 'Realistic Execution: Limit-order target, stop-market SL with slippage on fill'}
            </span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs font-mono">
            <button
              type="button"
              disabled={loading}
              onClick={() => setExecutionMode('TRIGGER_PRICE')}
              className={`p-2.5 rounded-lg border text-left transition-all ${
                executionMode === 'TRIGGER_PRICE'
                  ? 'bg-blue-500/20 border-blue-500 text-blue-200 shadow-sm'
                  : 'bg-surface border-border text-gray-400 hover:text-white'
              }`}
            >
              <div className="font-bold flex items-center justify-between">
                <span>Trigger-Price Mode (Idealized)</span>
                {executionMode === 'TRIGGER_PRICE' && <CheckCircle2 className="w-4 h-4 text-blue-400" />}
              </div>
              <p className="text-[11px] text-gray-400 mt-1">
                SL fills at exact stop trigger (e.g. ₹148.00); Target fills at exact target trigger (e.g. ₹154.00). Entry fills at candle open.
              </p>
            </button>

            <button
              type="button"
              disabled={loading}
              onClick={() => setExecutionMode('REALISTIC')}
              className={`p-2.5 rounded-lg border text-left transition-all ${
                executionMode === 'REALISTIC'
                  ? 'bg-amber-500/20 border-amber-500 text-amber-200 shadow-sm'
                  : 'bg-surface border-border text-gray-400 hover:text-white'
              }`}
            >
              <div className="font-bold flex items-center justify-between">
                <span>Realistic Execution Mode</span>
                {executionMode === 'REALISTIC' && <CheckCircle2 className="w-4 h-4 text-amber-400" />}
              </div>
              <p className="text-[11px] text-gray-400 mt-1">
                Entry at open + slippage; Limit target fills at trigger; Stop fills via stop-market (or gap open minus slippage).
              </p>
            </button>
          </div>
        </div>

        {/* Global Configuration Controls */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 pt-3 border-t border-border/50 text-xs font-mono">
          <div>
            <label className="text-gray-400 block mb-1">Strategy Algorithm:</label>
            <div className="flex items-center space-x-1.5">
              <button
                type="button"
                disabled={loading}
                onClick={() => setStrategyId('SUPERTREND_EMA')}
                className={`flex-1 py-1.5 px-2 rounded-lg border text-center font-bold flex items-center justify-center gap-1 transition-all ${
                  strategyId === 'SUPERTREND_EMA'
                    ? 'bg-emerald-500/20 border-emerald-500 text-emerald-300'
                    : 'bg-surface border-border text-gray-400 hover:text-white'
                }`}
              >
                <TrendingUp className="w-3.5 h-3.5 text-emerald-400" /> Supertrend
              </button>
              <button
                type="button"
                disabled={loading}
                onClick={() => setStrategyId('UT_BOT')}
                className={`flex-1 py-1.5 px-2 rounded-lg border text-center font-bold flex items-center justify-center gap-1 transition-all ${
                  strategyId === 'UT_BOT'
                    ? 'bg-amber-500/20 border-amber-500 text-amber-300'
                    : 'bg-surface border-border text-gray-400 hover:text-white'
                }`}
              >
                <Zap className="w-3.5 h-3.5 text-amber-400" /> UT Bot
              </button>
              <button
                type="button"
                disabled={loading}
                onClick={() => setStrategyId('EMA_RSI')}
                className={`flex-1 py-1.5 px-2 rounded-lg border text-center font-bold flex items-center justify-center gap-1 transition-all ${
                  strategyId === 'EMA_RSI'
                    ? 'bg-purple-500/20 border-purple-500 text-purple-300'
                    : 'bg-surface border-border text-gray-400 hover:text-white'
                }`}
              >
                <Layers className="w-3.5 h-3.5 text-purple-400" /> EMA/RSI
              </button>
            </div>
          </div>

          <div>
            <label className="text-gray-400 block mb-1">Trading Instrument:</label>
            <select
              value={instrument}
              disabled={loading}
              onChange={(e) => setInstrument(e.target.value)}
              className="w-full bg-surface border border-border rounded-lg px-3 py-1.5 text-white font-bold focus:outline-none focus:border-blue-500 disabled:opacity-50"
            >
              <option value="NIFTY ATM CE">NIFTY ATM CE (Option Premium)</option>
              <option value="NIFTY ATM PE">NIFTY ATM PE (Option Premium)</option>
              <option value="NIFTY 50">NIFTY 50 Index (Direct)</option>
            </select>
          </div>

          <div>
            <label className="text-gray-400 block mb-1">Timeframe:</label>
            <select
              value={timeframe}
              disabled={loading}
              onChange={(e) => setTimeframe(e.target.value as Timeframe)}
              className="w-full bg-surface border border-border rounded-lg px-3 py-1.5 text-white font-bold focus:outline-none focus:border-blue-500 disabled:opacity-50"
            >
              <option value="1m">1 Minute (Default)</option>
              <option value="3m">3 Minutes</option>
              <option value="5m">5 Minutes</option>
              <option value="15m">15 Minutes</option>
            </select>
          </div>

          <div>
            <label className="text-gray-400 block mb-1">Backtest Period / Duration:</label>
            <select
              value={durationOption}
              disabled={loading}
              onChange={(e) => setDurationOption(e.target.value)}
              className="w-full bg-surface border border-border rounded-lg px-3 py-1.5 text-white font-bold focus:outline-none focus:border-blue-500 disabled:opacity-50"
            >
              <option value="today">Today</option>
              <option value="3">Last 3 Trading Days</option>
              <option value="5">Last 5 Trading Days</option>
              <option value="10">Last 10 Trading Days</option>
              <option value="30">Last 30 Trading Days</option>
              <option value="60">Last 60 Trading Days</option>
              <option value="90">Last 90 Trading Days</option>
              <option value="180">Last 6 Months</option>
              <option value="365">Last 1 Year</option>
              <option value="custom">Custom Date Range</option>
            </select>
          </div>
        </div>

        {/* Custom Date Range Pickers (shown when custom is selected) */}
        {isCustomRange && (
          <div className="mt-3 pt-3 border-t border-border/40 text-xs font-mono bg-blue-950/20 p-3 rounded-lg border border-blue-900/30">
            <div className="flex items-center gap-2 mb-2 text-blue-300 font-bold">
              <Calendar className="w-3.5 h-3.5" />
              <span>Custom Date Range Selection:</span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 items-end">
              <div>
                <label className="text-gray-400 block mb-1">Start Date:</label>
                <input
                  type="date"
                  value={startDate}
                  disabled={loading}
                  onChange={(e) => setStartDate(e.target.value)}
                  className="w-full bg-surface border border-border rounded px-3 py-1.5 text-white font-bold focus:outline-none focus:border-blue-500"
                />
              </div>
              <div>
                <label className="text-gray-400 block mb-1">End Date:</label>
                <input
                  type="date"
                  value={endDate}
                  disabled={loading}
                  onChange={(e) => setEndDate(e.target.value)}
                  className="w-full bg-surface border border-border rounded px-3 py-1.5 text-white font-bold focus:outline-none focus:border-blue-500"
                />
              </div>
              <div>
                <button
                  onClick={handleRunBacktest}
                  disabled={loading}
                  className="w-full py-1.5 rounded bg-blue-600 hover:bg-blue-500 text-white font-bold transition-all flex items-center justify-center gap-1.5 shadow-sm disabled:opacity-50"
                >
                  <PlayCircle className="w-4 h-4" />
                  <span>Run Custom Backtest</span>
                </button>
              </div>
            </div>
            <p className="text-[11px] text-gray-400 mt-2">
              The backtest engine will test strictly between {startDate} and {endDate}. All trading days will be evaluated without truncation.
            </p>
          </div>
        )}

        {/* Strategy Specific Detailed Controls */}
        {strategyId === 'SUPERTREND_EMA' && (
          <div className="mt-4 pt-4 border-t border-border/50">
            <div className="text-xs font-mono font-bold text-emerald-300 mb-2 flex items-center justify-between">
              <span className="flex items-center gap-1.5">
                <Sliders className="w-3.5 h-3.5 text-emerald-400" /> Supertrend EMA Scalper Parameters:
              </span>
              <span className="text-[11px] text-gray-400">
                Quantity: <span className="text-white font-bold">{stLots * stLotSize}</span> ({stLots} lots × {stLotSize}) | Target: <span className="text-emerald-400 font-bold">+{stTheoreticalTargetPts} pts</span> (+₹{stTargetNetProfit} net) | Stop: <span className="text-red-400 font-bold">-{stTheoreticalStopPts} pts</span> (-₹{stMaxLoss} net)
              </span>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 text-xs font-mono">
              <div>
                <label className="text-gray-500 block mb-1">ATR Period:</label>
                <input
                  type="number"
                  disabled={loading}
                  value={stAtrPeriod}
                  onChange={(e) => setStAtrPeriod(parseInt(e.target.value) || 10)}
                  className="w-full bg-surface border border-border rounded px-2 py-1 text-white font-bold disabled:opacity-50"
                />
              </div>

              <div>
                <label className="text-gray-500 block mb-1">Multiplier:</label>
                <input
                  type="number"
                  step="0.1"
                  disabled={loading}
                  value={stMultiplier}
                  onChange={(e) => setStMultiplier(parseFloat(e.target.value) || 3.0)}
                  className="w-full bg-surface border border-border rounded px-2 py-1 text-white font-bold disabled:opacity-50"
                />
              </div>

              <div>
                <label className="text-gray-500 block mb-1">Fast EMA:</label>
                <input
                  type="number"
                  disabled={loading}
                  value={stEmaFast}
                  onChange={(e) => setStEmaFast(parseInt(e.target.value) || 9)}
                  className="w-full bg-surface border border-border rounded px-2 py-1 text-white font-bold disabled:opacity-50"
                />
              </div>

              <div>
                <label className="text-gray-500 block mb-1">Slow EMA:</label>
                <input
                  type="number"
                  disabled={loading}
                  value={stEmaSlow}
                  onChange={(e) => setStEmaSlow(parseInt(e.target.value) || 21)}
                  className="w-full bg-surface border border-border rounded px-2 py-1 text-white font-bold disabled:opacity-50"
                />
              </div>

              <div>
                <label className="text-gray-500 block mb-1">Lots (Default 5):</label>
                <input
                  type="number"
                  min="1"
                  disabled={loading}
                  value={stLots}
                  onChange={(e) => setStLots(parseInt(e.target.value) || 5)}
                  className="w-full bg-surface border border-border rounded px-2 py-1 text-white font-bold disabled:opacity-50"
                />
              </div>

              <div>
                <label className="text-gray-500 block mb-1">Lot Size:</label>
                <input
                  type="number"
                  min="1"
                  disabled={loading}
                  value={stLotSize}
                  onChange={(e) => setStLotSize(parseInt(e.target.value) || 65)}
                  className="w-full bg-surface border border-border rounded px-2 py-1 text-white font-bold disabled:opacity-50"
                />
              </div>

              <div>
                <label className="text-gray-500 block mb-1">Target Net P&amp;L (₹):</label>
                <input
                  type="number"
                  step="50"
                  disabled={loading}
                  value={stTargetNetProfit}
                  onChange={(e) => setStTargetNetProfit(parseFloat(e.target.value) || 200.0)}
                  className="w-full bg-surface border border-border rounded px-2 py-1 text-emerald-400 font-bold disabled:opacity-50"
                />
              </div>

              <div>
                <label className="text-gray-500 block mb-1">Max Loss Budget (₹):</label>
                <input
                  type="number"
                  step="100"
                  disabled={loading}
                  value={stMaxLoss}
                  onChange={(e) => setStMaxLoss(parseFloat(e.target.value) || 1000.0)}
                  className="w-full bg-surface border border-border rounded px-2 py-1 text-red-400 font-bold disabled:opacity-50"
                />
              </div>

              <div>
                <label className="text-gray-500 block mb-1">Daily Profit Target (₹):</label>
                <input
                  type="number"
                  step="100"
                  disabled={loading}
                  value={stDailyProfitTarget}
                  onChange={(e) => setStDailyProfitTarget(parseFloat(e.target.value) || 1000.0)}
                  className="w-full bg-surface border border-border rounded px-2 py-1 text-emerald-300 font-bold disabled:opacity-50"
                />
              </div>

              <div>
                <label className="text-gray-500 block mb-1">Daily Loss Limit (₹):</label>
                <input
                  type="number"
                  step="100"
                  disabled={loading}
                  value={stDailyLossLimit}
                  onChange={(e) => setStDailyLossLimit(parseFloat(e.target.value) || -2000.0)}
                  className="w-full bg-surface border border-border rounded px-2 py-1 text-rose-300 font-bold disabled:opacity-50"
                />
              </div>
            </div>
          </div>
        )}

        {/* Strategy Specific Detailed Controls */}
        {strategyId === 'UT_BOT' && (
          <div className="mt-4 pt-4 border-t border-border/50">
            <div className="text-xs font-mono font-bold text-amber-300 mb-2 flex items-center gap-1.5">
              <Sliders className="w-3.5 h-3.5" /> UT Bot Specific Parameters:
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 text-xs font-mono">
              <div>
                <label className="text-gray-500 block mb-1">Sensitivity (a):</label>
                <input
                  type="number"
                  step="0.1"
                  disabled={loading}
                  value={utKeyValue}
                  onChange={(e) => setUtKeyValue(parseFloat(e.target.value) || 1.0)}
                  className="w-full bg-surface border border-border rounded px-2 py-1 text-white font-bold disabled:opacity-50"
                />
              </div>

              <div>
                <label className="text-gray-500 block mb-1">ATR Period (c):</label>
                <input
                  type="number"
                  disabled={loading}
                  value={utAtrPeriod}
                  onChange={(e) => setUtAtrPeriod(parseInt(e.target.value) || 10)}
                  className="w-full bg-surface border border-border rounded px-2 py-1 text-white font-bold disabled:opacity-50"
                />
              </div>

              <div>
                <label className="text-gray-500 block mb-1">Lots (Default 5):</label>
                <input
                  type="number"
                  min="1"
                  disabled={loading}
                  value={utLots}
                  onChange={(e) => setUtLots(parseInt(e.target.value) || 5)}
                  className="w-full bg-surface border border-border rounded px-2 py-1 text-white font-bold disabled:opacity-50"
                />
              </div>

              <div>
                <label className="text-gray-500 block mb-1">Target Pts (+4.0):</label>
                <input
                  type="number"
                  step="0.5"
                  disabled={loading}
                  value={utTarget}
                  onChange={(e) => setUtTarget(parseFloat(e.target.value) || 4.0)}
                  className="w-full bg-surface border border-border rounded px-2 py-1 text-white font-bold disabled:opacity-50"
                />
              </div>

              <div>
                <label className="text-gray-500 block mb-1">Stop Pts (-2.0):</label>
                <input
                  type="number"
                  step="0.5"
                  disabled={loading}
                  value={utStop}
                  onChange={(e) => setUtStop(parseFloat(e.target.value) || 2.0)}
                  className="w-full bg-surface border border-border rounded px-2 py-1 text-white font-bold disabled:opacity-50"
                />
              </div>

              <div>
                <label className="text-gray-500 block mb-1">Slippage (pts):</label>
                <input
                  type="number"
                  step="0.05"
                  disabled={loading}
                  value={slippage}
                  onChange={(e) => setSlippage(parseFloat(e.target.value) || 0.10)}
                  className="w-full bg-surface border border-border rounded px-2 py-1 text-white font-bold disabled:opacity-50"
                />
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-6 mt-3 pt-2 text-xs font-mono">
              <label className="flex items-center space-x-2 cursor-pointer">
                <input
                  type="checkbox"
                  disabled={loading}
                  checked={utRiskCap}
                  onChange={(e) => setUtRiskCap(e.target.checked)}
                  className="rounded bg-surface border-border text-amber-500 disabled:opacity-50"
                />
                <span className="text-amber-300 font-bold">Apply ₹1,000 Max Loss Risk Cap Overlay</span>
              </label>

              <label className="flex items-center space-x-2 cursor-pointer">
                <input
                  type="checkbox"
                  disabled={loading}
                  checked={exitOnUtSell}
                  onChange={(e) => setExitOnUtSell(e.target.checked)}
                  className="rounded bg-surface border-border text-red-500 disabled:opacity-50"
                />
                <span className={exitOnUtSell ? "text-blue-300 font-bold" : "text-gray-300"}>
                  Exit on UT Sell Signal (Enabled: BUY opens, SELL closes position)
                </span>
              </label>

              <label className="flex items-center space-x-2 cursor-pointer">
                <input
                  type="checkbox"
                  disabled={loading}
                  checked={utUseHA}
                  onChange={(e) => setUtUseHA(e.target.checked)}
                  className="rounded bg-surface border-border text-blue-500 disabled:opacity-50"
                />
                <span className="text-gray-300">Heikin Ashi Candle Calculations</span>
              </label>

              <div className="flex items-center space-x-2 text-gray-400">
                <span>Signal Source:</span>
                <select
                  value={utSignalSource}
                  disabled={loading}
                  onChange={(e) => setUtSignalSource(e.target.value as any)}
                  className="bg-surface border border-border rounded px-2 py-0.5 text-white font-bold disabled:opacity-50"
                >
                  <option value="CHART_INSTRUMENT">Chart Instrument (Option)</option>
                  <option value="NIFTY_INDEX">NIFTY Spot Index</option>
                </select>
              </div>

              <div className="w-full bg-surface/50 p-2.5 rounded-lg border border-border/60 flex flex-wrap items-center justify-between gap-2 text-[11px] text-gray-300 mt-1">
                <div>
                  Configured: <span className="text-white font-bold">{utStop} pts SL</span> / <span className="text-white font-bold">{utTarget} pts Target</span>
                </div>
                <div>
                  Quantity: <span className="text-white font-bold">{previewQty}</span> ({strategyId === 'UT_BOT' ? utLots : emaLots} lots × {utLotSize})
                </div>
                <div>
                  Effective SL:{' '}
                  <span className={isCapped ? "text-amber-400 font-bold" : "text-emerald-400 font-bold"}>
                    {effectiveStopPts.toFixed(2)} pts
                  </span>
                  {isCapped && <span className="text-amber-300 ml-1">(Tightened by ₹1,000 risk cap: ₹1,000 / {previewQty} qty)</span>}
                  {!isCapped && utRiskCap && <span className="text-gray-400 ml-1">(Normal risk ₹{normalRisk.toFixed(0)} ≤ ₹1,000 cap)</span>}
                </div>
                <div>
                  Execution:{' '}
                  <span className="font-bold text-blue-400">{executionMode === 'TRIGGER_PRICE' ? 'Trigger-Price (Zero Slippage)' : 'Realistic (Slippage + Stop-Market)'}</span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Action Button */}
        <div className="mt-5 pt-3 border-t border-border flex justify-end">
          <button
            onClick={handleRunBacktest}
            disabled={loading}
            className="py-2.5 px-6 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:bg-blue-800 disabled:cursor-not-allowed text-white font-mono font-bold text-xs transition-colors flex items-center justify-center gap-2 shadow-lg shadow-blue-500/20"
          >
            <PlayCircle className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            {loading ? 'Simulating High-Fidelity Backtest...' : `Run ${strategyId === 'SUPERTREND_EMA' ? 'Supertrend EMA' : strategyId === 'UT_BOT' ? 'UT Bot' : 'EMA'} Backtest`}
          </button>
        </div>
      </div>

      {errorMsg && (
        <div className="p-4 rounded-xl bg-rose-950/50 border border-rose-800 text-rose-300 text-xs font-mono leading-relaxed space-y-3 shadow-lg">
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-start gap-3">
              <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5 text-rose-400" />
              <div>
                <div className="font-bold uppercase tracking-wider text-rose-200 mb-1 flex items-center gap-2">
                  <span>Backtest Data Error</span>
                  <span className="text-[10px] px-2 py-0.5 rounded bg-rose-900/60 border border-rose-700/80 font-normal">
                    Kotak Neo Broker API
                  </span>
                </div>
                <div className="text-gray-200">{errorMsg}</div>
              </div>
            </div>
            <button
              onClick={handleRunBacktest}
              disabled={loading}
              className="px-3 py-1.5 rounded-lg bg-rose-700 hover:bg-rose-600 border border-rose-500 text-white font-bold text-xs transition-colors shrink-0 flex items-center gap-1.5"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>Retry Backtest</span>
            </button>
          </div>
          <div className="p-2.5 rounded-lg bg-black/40 border border-rose-900/40 text-[11px] text-gray-400 space-y-1">
            <div className="text-gray-300 font-semibold">Historical Data Availability & Guidelines:</div>
            <div>• NIFTY 50 Index 1-minute historical data is available across all past trading dates (e.g. 2026-11-09 to 2026-11-13).</div>
            <div>• Active weekly/monthly derivative option contracts support 1-minute historical data for their trading lifespan.</div>
            <div>• Kotak Neo API allows up to 30 days per 1-minute request (automatically batched by the backend).</div>
            <div>• If testing custom scenarios without active broker contracts, select <span className="text-cyan-400 font-semibold">"Deterministic Synthetic Test Data"</span>.</div>
          </div>
        </div>
      )}

      {/* Execution Progress Indicator */}
      {loading && (
        <div className="bg-card border border-blue-500/40 rounded-xl p-8 flex flex-col items-center justify-center space-y-4 shadow-xl shadow-blue-500/5 transition-all">
          <div className="relative">
            <div className="w-16 h-16 rounded-full border-4 border-blue-500/20 border-t-blue-500 animate-spin" />
            <Activity className="w-6 h-6 text-blue-400 absolute inset-0 m-auto animate-pulse" />
          </div>
          <div className="text-center space-y-1">
            <h3 className="font-bold text-white text-base">Running Historical Backtest Simulation...</h3>
            <p className="text-xs text-gray-400 font-mono">
              Loading 1-minute historical data &bull; Evaluating strategy signals &bull; Simulating slippage &amp; risk
            </p>
          </div>
          <div className="w-full max-w-md bg-surface/80 rounded-full h-1.5 overflow-hidden border border-border">
            <div className="bg-blue-500 h-full w-2/3 rounded-full animate-pulse" />
          </div>
        </div>
      )}

      {/* Results Display */}
      {result && (
        <div className="space-y-6">
          {/* Results Navigation Tabs */}
          <div className="bg-card border border-border rounded-xl p-3 flex flex-wrap items-center justify-between gap-3">
            <div className="bg-surface p-1 rounded-lg border border-border flex items-center space-x-1 text-xs font-mono font-bold">
              <button
                onClick={() => setResultsTab('METRICS')}
                className={`px-3 py-1.5 rounded-md flex items-center gap-1.5 transition-all ${
                  resultsTab === 'METRICS'
                    ? 'bg-blue-600 text-white shadow-sm'
                    : 'text-gray-400 hover:text-white hover:bg-surface/80'
                }`}
              >
                <BarChart3 className="w-3.5 h-3.5" />
                METRICS &amp; EQUITY CURVE
              </button>
              <button
                onClick={() => setResultsTab('CALENDAR')}
                className={`px-3 py-1.5 rounded-md flex items-center gap-1.5 transition-all ${
                  resultsTab === 'CALENDAR'
                    ? 'bg-purple-600 text-white shadow-sm'
                    : 'text-gray-400 hover:text-white hover:bg-surface/80'
                }`}
              >
                <Calendar className="w-3.5 h-3.5" />
                PERFORMANCE CALENDAR
              </button>
              <button
                onClick={() => setActivePageTab('COMPARISON_AUDIT')}
                className="px-3 py-1.5 rounded-md flex items-center gap-1.5 transition-all text-purple-300 hover:text-white hover:bg-surface/80"
                title="Open 4-Way Synthetic vs Real Comparison Audit"
              >
                <Scale className="w-3.5 h-3.5 text-purple-400" />
                SYNTHETIC VS REAL AUDIT
              </button>
            </div>

            <div className="flex items-center space-x-2 text-xs font-mono">
              <span className="text-gray-400">Run ID:</span>
              <span className="font-bold text-white bg-surface px-2 py-0.5 rounded border border-border">
                #{result.run_id}
              </span>
              {result.run_id && onNavigateToAnalytics && (
                <button
                  onClick={() => onNavigateToAnalytics(result.run_id!)}
                  className="px-3 py-1 rounded-lg bg-purple-600 hover:bg-purple-500 text-white font-bold flex items-center gap-1.5 shadow-sm transition-all border border-purple-400/40"
                  title="Open comprehensive Analytics for this backtest run"
                >
                  <PieChart className="w-3.5 h-3.5 text-purple-200" />
                  View Analytics
                </button>
              )}
            </div>
          </div>

          {resultsTab === 'CALENDAR' ? (
            <PerformanceCalendar
              embedded={true}
              initialSource="BACKTEST"
              initialRunId={result.run_id}
            />
          ) : (
            <>
              {/* Exact Backtest Period & Coverage Audit Card (Section 5) */}
              {result.period_summary && (
                <div className="bg-card border border-border rounded-xl p-4 text-xs font-mono space-y-3 shadow-md">
                  <div className="flex flex-wrap items-center justify-between gap-2 pb-2.5 border-b border-border/40">
                    <div className="flex items-center space-x-2">
                      <Calendar className="w-4 h-4 text-blue-400" />
                      <span className="font-bold text-white uppercase tracking-wider">
                        Exact Backtest Period &amp; Coverage Audit
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="px-2.5 py-0.5 rounded text-[11px] font-bold bg-blue-500/10 text-blue-300 border border-blue-500/30">
                        {result.period_summary.trading_days_tested} Trading Days Tested
                      </span>
                      {result.period_summary.missing_data_count > 0 ? (
                        <span className="px-2.5 py-0.5 rounded text-[11px] font-bold bg-rose-500/20 text-rose-300 border border-rose-500/40">
                          {result.period_summary.missing_data_count} Missing Days
                        </span>
                      ) : (
                        <span className="px-2.5 py-0.5 rounded text-[11px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                          100% Data Complete
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2.5 pt-1 text-gray-400">
                    <div className="bg-surface/60 p-2.5 rounded-lg border border-border/40">
                      <span className="text-[10px] text-gray-500 block uppercase">Selected Start</span>
                      <span className="text-white font-bold">{result.period_summary.selected_start_date}</span>
                    </div>
                    <div className="bg-surface/60 p-2.5 rounded-lg border border-border/40">
                      <span className="text-[10px] text-gray-500 block uppercase">Selected End</span>
                      <span className="text-white font-bold">{result.period_summary.selected_end_date}</span>
                    </div>
                    <div className="bg-surface/60 p-2.5 rounded-lg border border-border/40">
                      <span className="text-[10px] text-gray-500 block uppercase">First Candle</span>
                      <span className="text-cyan-400 font-bold">{result.period_summary.actual_first_candle_date}</span>
                    </div>
                    <div className="bg-surface/60 p-2.5 rounded-lg border border-border/40">
                      <span className="text-[10px] text-gray-500 block uppercase">Last Candle</span>
                      <span className="text-cyan-400 font-bold">{result.period_summary.actual_last_candle_date}</span>
                    </div>
                    <div className="bg-surface/60 p-2.5 rounded-lg border border-border/40">
                      <span className="text-[10px] text-gray-500 block uppercase">Days Available</span>
                      <span className="text-emerald-400 font-bold">{result.period_summary.trading_days_available} Days</span>
                    </div>
                    <div className="bg-surface/60 p-2.5 rounded-lg border border-border/40">
                      <span className="text-[10px] text-gray-500 block uppercase">Days Tested</span>
                      <span className="text-white font-bold">{result.period_summary.trading_days_tested} Days</span>
                    </div>
                    <div className="bg-surface/60 p-2.5 rounded-lg border border-border/40">
                      <span className="text-[10px] text-gray-500 block uppercase">With Trades</span>
                      <span className="text-emerald-400 font-bold">{result.period_summary.trading_days_with_trades} Days</span>
                    </div>
                    <div className="bg-surface/60 p-2.5 rounded-lg border border-border/40">
                      <span className="text-[10px] text-gray-500 block uppercase">Without Trades</span>
                      <span className="text-amber-400 font-bold">{result.period_summary.trading_days_without_trades} Days</span>
                    </div>
                  </div>

                  {result.period_summary.missing_data_count > 0 && (
                    <div className="p-2.5 rounded-lg bg-rose-950/40 border border-rose-800 text-rose-300 text-[11px] flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <AlertCircle className="w-4 h-4 text-rose-400 flex-shrink-0" />
                        <span>
                          <strong>Missing Historical Data:</strong> The following expected trading dates had 0 broker candles:{" "}
                          {result.period_summary.missing_data_days.join(", ")}. These are NOT treated as no-trade days.
                        </span>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Data Quality & Audit Metadata Banner */}
          <div className="bg-surface/60 border border-border rounded-xl p-4 text-xs font-mono">
            <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-border/40">
              <div className="flex items-center space-x-2">
                <ShieldCheck className="w-4 h-4 text-emerald-400" />
                <span className="font-bold text-white">Backtest Dataset &amp; Audit Metadata</span>
              </div>
              <span
                className={`px-2.5 py-0.5 rounded text-[11px] font-bold border ${
                  result.data_source === 'REAL_MARKET'
                    ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                    : 'bg-purple-500/10 text-purple-400 border-purple-500/30'
                }`}
              >
                {result.data_quality_status || result.data_source}
              </span>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 pt-3 text-gray-400">
              <div>
                <span className="text-[10px] text-gray-500 block uppercase">Signal Instrument</span>
                <span className="text-cyan-400 font-bold">{result.signal_instrument || 'NIFTY 50 Index'}</span>
              </div>
              <div>
                <span className="text-[10px] text-gray-500 block uppercase">Execution Instrument</span>
                <span className="text-white font-bold">{result.execution_instrument || result.contract_symbol || result.instrument}</span>
              </div>
              <div>
                <span className="text-[10px] text-gray-500 block uppercase">Coverage Date Range</span>
                <span className="text-white font-bold">{result.start_date} to {result.end_date}</span>
              </div>
              <div>
                <span className="text-[10px] text-gray-500 block uppercase">Execution Mode</span>
                <span className="text-amber-400 font-bold">{result.execution_mode || "TRIGGER_PRICE"}</span>
              </div>
              <div>
                <span className="text-[10px] text-gray-500 block uppercase">Valid 1M Candles</span>
                <span className="text-emerald-400 font-bold">{result.valid_candles_count || result.total_trades * 5} bars</span>
              </div>
              <div>
                <span className="text-[10px] text-gray-500 block uppercase">Missing Candles</span>
                <span className="text-white font-bold">{result.missing_candles_count || 0} bars</span>
              </div>
            </div>
          </div>

          {/* Mathematical Reconciliation Banner */}
          <div className="bg-blue-950/20 border border-blue-900/50 rounded-xl p-3 px-4 text-xs font-mono flex flex-wrap items-center justify-between gap-2 text-blue-200">
            <div className="flex items-center gap-2">
              <span className="font-bold text-white">P&amp;L Accounting Reconciliation:</span>
              <span>
                Gross (+₹{result.gross_profit.toFixed(2)}) - Loss (-₹{result.gross_loss.toFixed(2)}) - Charges (₹{result.total_charges.toFixed(2)}) ={' '}
                <strong className={getPnlColor(result.net_profit)}>Net ₹{result.net_profit.toFixed(2)}</strong>
              </span>
            </div>
            <div className="text-gray-400">
              Initial Capital ₹{result.initial_capital.toLocaleString()} + Net ₹{result.net_profit.toFixed(2)} ={' '}
              <strong className="text-white">Final ₹{result.final_capital.toLocaleString()}</strong>
            </div>
          </div>

          {/* Order Execution Breakdown Banner */}
          <div className="bg-surface/80 border border-border rounded-xl p-3 px-4 text-xs font-mono flex flex-wrap items-center justify-between gap-3 shadow-sm">
            <div className="flex flex-wrap items-center gap-2.5">
              <span className="text-gray-400 font-bold">Signal &amp; Order Execution Breakdown:</span>
              <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-blue-500/20 text-blue-300 border border-blue-500/30">
                BUY Entries: {result.buy_entries_count ?? result.total_trades}
              </span>
              <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-purple-500/20 text-purple-300 border border-purple-500/30">
                UT Sell Exits: {result.sell_exits_count ?? 0}
              </span>
              <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                Target Exits: {result.target_exits_count ?? 0}
              </span>
              <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-rose-500/20 text-rose-300 border border-rose-500/30">
                SL Exits: {result.stop_loss_exits_count ?? 0}
              </span>
              <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30">
                Auto-Close (15:20): {result.auto_close_exits_count ?? 0}
              </span>
            </div>
            {result.execution_diagnostics && result.execution_diagnostics.length > 0 && (
              <button
                onClick={() => setShowDiagnostics(!showDiagnostics)}
                className="px-2.5 py-1 rounded text-[11px] font-bold bg-surface border border-border text-cyan-400 hover:text-cyan-300 hover:border-cyan-500/50 transition-all flex items-center gap-1.5"
              >
                <Activity className="w-3.5 h-3.5" />
                {showDiagnostics ? "Hide Signal Diagnostics" : `View Diagnostics Log (${result.execution_diagnostics.length} Events)`}
              </button>
            )}
          </div>

          {/* Expandable Execution Diagnostics Table */}
          {showDiagnostics && result.execution_diagnostics && result.execution_diagnostics.length > 0 && (
            <div className="bg-card border border-border rounded-xl p-4 font-mono text-xs space-y-3 shadow-md">
              <div className="flex items-center justify-between pb-2 border-b border-border/40">
                <span className="font-bold text-white flex items-center gap-2">
                  <Activity className="w-4 h-4 text-cyan-400" />
                  Strategy Signal &amp; Order Execution Diagnostics Log
                </span>
                <span className="text-gray-400 text-[11px]">
                  All detected BUY/SELL signals, actions taken, position states, and suppressions
                </span>
              </div>
              <div className="overflow-x-auto max-h-[360px]">
                <table className="w-full text-xs font-mono text-left">
                  <thead className="sticky top-0 bg-surface border-b border-border text-gray-400 uppercase text-[10px]">
                    <tr>
                      <th className="px-3 py-2">Signal Time</th>
                      <th className="px-3 py-2">Signal Type</th>
                      <th className="px-3 py-2">Position State</th>
                      <th className="px-3 py-2">Action</th>
                      <th className="px-3 py-2">Reason / Details</th>
                      <th className="px-3 py-2 text-right">Entry (₹)</th>
                      <th className="px-3 py-2 text-right">Exit (₹)</th>
                      <th className="px-3 py-2 text-right">Net P&amp;L (₹)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/40">
                    {result.execution_diagnostics.map((diag, dIdx) => (
                      <tr key={dIdx} className="hover:bg-surface/50">
                        <td className="px-3 py-1.5 text-gray-300">{diag.signal_time.slice(0, 19)}</td>
                        <td className="px-3 py-1.5">
                          <span
                            className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                              diag.signal_type === 'BUY'
                                ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                                : diag.signal_type === 'SELL'
                                ? 'bg-blue-500/20 text-blue-300 border border-blue-500/30'
                                : 'bg-purple-500/20 text-purple-300 border border-purple-500/30'
                            }`}
                          >
                            {diag.signal_type}
                          </span>
                        </td>
                        <td className="px-3 py-1.5 text-gray-400">{diag.position_before_signal}</td>
                        <td className="px-3 py-1.5">
                          <span
                            className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                              diag.action_taken === 'ENTRY'
                                ? 'bg-emerald-600/30 text-emerald-300 border border-emerald-500/30'
                                : diag.action_taken === 'EXIT'
                                ? 'bg-blue-600/30 text-blue-300 border border-blue-500/30'
                                : 'bg-gray-700/40 text-gray-400 border border-gray-600/30'
                            }`}
                          >
                            {diag.action_taken}
                          </span>
                        </td>
                        <td className="px-3 py-1.5 text-gray-300 text-[11px]">{diag.action_reason}</td>
                        <td className="px-3 py-1.5 text-right text-white">
                          {diag.entry_price ? `₹${diag.entry_price.toFixed(2)}` : '—'}
                        </td>
                        <td className="px-3 py-1.5 text-right text-cyan-300">
                          {diag.exit_price ? `₹${diag.exit_price.toFixed(2)}` : '—'}
                        </td>
                        <td className={`px-3 py-1.5 text-right font-bold ${getPnlColor(diag.net_pnl)}`}>
                          {diag.action_taken === 'EXIT' ? formatCurrency(diag.net_pnl) : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Key Metric Stat Cards */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            <StatCard
              title="TOTAL TRADES"
              value={result.total_trades}
              subValue={`Wins: ${result.winning_trades} | Losses: ${result.losing_trades}`}
            />
            <StatCard
              title="WIN RATE"
              value={`${result.win_rate}%`}
              trend={result.win_rate >= 50 ? 'up' : 'down'}
            />
            <StatCard
              title="NET PROFIT"
              value={formatCurrency(result.net_profit)}
              subValue={`Gross: ₹${result.gross_profit.toFixed(0)} | Loss: ₹${result.gross_loss.toFixed(0)}`}
              trend={result.net_profit >= 0 ? 'up' : 'down'}
            />
            <StatCard
              title="PROFIT FACTOR"
              value={result.profit_factor.toFixed(2)}
              trend={result.profit_factor >= 1.5 ? 'up' : 'neutral'}
            />
            <StatCard
              title="MAX DRAWDOWN"
              value={formatCurrency(result.max_drawdown)}
              subValue={result.max_drawdown_percent ? `${result.max_drawdown_percent.toFixed(1)}% of Peak` : undefined}
              trend="down"
            />
            <StatCard
              title="FINAL CAPITAL"
              value={formatCurrency(result.final_capital)}
              subValue={`Initial: ₹${result.initial_capital.toLocaleString()}`}
            />
          </div>

          {/* Secondary Analytics Strip */}
          <div className="bg-surface/50 border border-border rounded-xl p-4 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 text-xs font-mono">
            <div>
              <span className="text-gray-500 text-[10px] block">AVG WIN / LOSS</span>
              <span className="text-emerald-400 font-bold">+₹{result.avg_profit.toFixed(0)}</span>
              <span className="text-gray-500"> / </span>
              <span className="text-red-400 font-bold">-₹{result.avg_loss.toFixed(0)}</span>
            </div>
            <div>
              <span className="text-gray-500 text-[10px] block">LARGEST WIN</span>
              <span className="text-emerald-400 font-bold">+₹{result.largest_win.toFixed(2)}</span>
            </div>
            <div>
              <span className="text-gray-500 text-[10px] block">LARGEST LOSS</span>
              <span className="text-red-400 font-bold">-₹{Math.abs(result.largest_loss).toFixed(2)}</span>
            </div>
            <div>
              <span className="text-gray-500 text-[10px] block">TOTAL CHARGES</span>
              <span className="text-gray-300 font-bold">₹{result.total_charges.toFixed(2)}</span>
            </div>
            <div>
              <span className="text-gray-500 text-[10px] block">TOTAL SLIPPAGE</span>
              <span className="text-gray-300 font-bold">₹{result.total_slippage?.toFixed(2) || '0.00'}</span>
            </div>
            <div>
              <span className="text-gray-500 text-[10px] block">AVG HOLDING TIME</span>
              <span className="text-blue-400 font-bold">
                {result.avg_holding_time ?? result.avg_holding_time_minutes ?? 0} mins
              </span>
            </div>
          </div>

          {/* Visual Equity Curve */}
          {result.equity_curve && result.equity_curve.length > 1 && (
            <div className="bg-card border border-border rounded-xl p-5">
              <h3 className="font-bold text-white text-sm mb-3 flex items-center gap-2">
                <TrendingUp className="w-4 h-4 text-emerald-400" />
                Simulated Equity Progression Curve
              </h3>
              <div className="h-44 w-full flex items-end gap-1 pt-6 px-2 border-b border-border">
                {result.equity_curve.map((pt, idx) => {
                  const minEq = Math.min(...result.equity_curve!.map((p) => p.equity));
                  const maxEq = Math.max(...result.equity_curve!.map((p) => p.equity));
                  const range = Math.max(100, maxEq - minEq);
                  const hPct = Math.max(8, Math.min(100, ((pt.equity - minEq) / range) * 100));
                  return (
                    <div
                      key={idx}
                      className="flex-1 bg-blue-600/70 hover:bg-blue-400 rounded-t transition-all cursor-pointer group relative"
                      style={{ height: `${hPct}%` }}
                      title={`Trade #${pt.trade}: ₹${pt.equity.toFixed(2)}`}
                    />
                  );
                })}
              </div>
              <div className="flex justify-between text-[10px] font-mono text-gray-500 mt-2">
                <span>Start: ₹{result.initial_capital.toLocaleString()}</span>
                <span>Trades: {result.total_trades}</span>
                <span>Final: ₹{result.final_capital.toLocaleString()}</span>
              </div>
            </div>
          )}

          {/* Date-Wise Results Breakdown (Section 2 & 3) */}
          {((result.date_wise_summary && result.date_wise_summary.length > 0) || (result.daily_summary && result.daily_summary.length > 0)) && (
            <div className="bg-card border border-border rounded-xl p-5 shadow-lg space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center space-x-2">
                  <Calendar className="w-4 h-4 text-purple-400" />
                  <h3 className="font-bold text-white text-sm">
                    Date-Wise Performance Breakdown (All Trading Dates)
                  </h3>
                </div>
                <div className="text-xs font-mono text-gray-400">
                  Click any date row to inspect its exact historical chart and execution markers
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-xs font-mono text-left">
                  <thead>
                    <tr className="bg-surface/70 border-b border-border text-gray-400 uppercase text-[10px]">
                      <th className="px-3 py-2.5">Date &amp; Day</th>
                      <th className="px-3 py-2.5">Status</th>
                      <th className="px-3 py-2.5 text-right">Trades</th>
                      <th className="px-3 py-2.5 text-right">Win Rate</th>
                      <th className="px-3 py-2.5 text-right">Gross P&amp;L</th>
                      <th className="px-3 py-2.5 text-right">Charges</th>
                      <th className="px-3 py-2.5 text-right">Slippage</th>
                      <th className="px-3 py-2.5 text-right">Net P&amp;L</th>
                      <th className="px-3 py-2.5 text-right">Best</th>
                      <th className="px-3 py-2.5 text-right">Worst</th>
                      <th className="px-3 py-2.5 text-right">Drawdown</th>
                      <th className="px-3 py-2.5 text-center">Chart &amp; Ledger</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/40">
                    {(result.date_wise_summary || (result.daily_summary as any[]) || []).map((day: any, idx: number) => {
                      const isTraded = day.status === 'TRADED' || Number(day.trades || day.trades_count || 0) > 0;
                      const status = day.status || (isTraded ? 'TRADED' : 'NO_TRADE');
                      const tradesCnt = Number(day.trades || day.trades_count || 0);
                      const netPnl = Number(day.net_pnl ?? day.pnl ?? 0);
                      const grossPnl = Number(day.gross_pnl ?? (day.grossProfit - day.grossLoss) ?? 0);
                      const charges = Number(day.charges ?? 0);
                      const slippage = Number(day.slippage ?? day.slippage_cost ?? 0);
                      const winRate = Number(day.win_rate ?? 0);
                      const bestTrade = Number(day.best_trade ?? 0);
                      const worstTrade = Number(day.worst_trade ?? 0);
                      const dd = Number(day.daily_drawdown ?? 0);

                      return (
                        <tr
                          key={idx}
                          onClick={() => handleInspectDay(day)}
                          className="hover:bg-surface/60 cursor-pointer transition-colors group"
                        >
                          <td className="px-3 py-2.5 text-white font-bold flex items-center gap-1.5">
                            <span>{day.date}</span>
                            <span className="text-[10px] text-gray-500 font-normal">
                              ({day.day_name ? day.day_name.slice(0, 3) : ''})
                            </span>
                          </td>
                          <td className="px-3 py-2.5">
                            <span
                              className={`px-2 py-0.5 rounded text-[10px] font-bold border ${
                                status === 'TRADED'
                                  ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30'
                                  : status === 'NO_TRADE'
                                  ? 'bg-amber-500/15 text-amber-300 border-amber-500/30'
                                  : status === 'HOLIDAY'
                                  ? 'bg-purple-500/15 text-purple-300 border-purple-500/30'
                                  : status === 'WEEKEND'
                                  ? 'bg-slate-500/15 text-slate-400 border-slate-500/30'
                                  : 'bg-rose-500/15 text-rose-300 border-rose-500/30'
                              }`}
                            >
                              {status === 'TRADED'
                                ? 'Traded'
                                : status === 'NO_TRADE'
                                ? 'No Trade'
                                : status === 'HOLIDAY'
                                ? 'Holiday'
                                : status === 'WEEKEND'
                                ? 'Weekend'
                                : 'Missing Data'}
                            </span>
                          </td>
                          <td className="px-3 py-2.5 text-right font-semibold text-gray-300">{tradesCnt}</td>
                          <td className="px-3 py-2.5 text-right text-blue-400">
                            {tradesCnt > 0 ? `${winRate.toFixed(1)}%` : '-'}
                          </td>
                          <td className={`px-3 py-2.5 text-right font-medium ${getPnlColor(grossPnl)}`}>
                            {tradesCnt > 0 ? formatCurrency(grossPnl) : '₹0.00'}
                          </td>
                          <td className="px-3 py-2.5 text-right text-gray-400">
                            {tradesCnt > 0 ? `₹${charges.toFixed(2)}` : '₹0.00'}
                          </td>
                          <td className="px-3 py-2.5 text-right text-gray-400">
                            {tradesCnt > 0 ? `₹${slippage.toFixed(2)}` : '₹0.00'}
                          </td>
                          <td className={`px-3 py-2.5 text-right font-bold ${getPnlColor(netPnl)}`}>
                            {tradesCnt > 0 ? formatCurrency(netPnl) : '₹0.00'}
                          </td>
                          <td className="px-3 py-2.5 text-right text-emerald-400">
                            {tradesCnt > 0 && bestTrade !== 0 ? `+₹${bestTrade.toFixed(0)}` : '-'}
                          </td>
                          <td className="px-3 py-2.5 text-right text-rose-400">
                            {tradesCnt > 0 && worstTrade !== 0 ? `-₹${Math.abs(worstTrade).toFixed(0)}` : '-'}
                          </td>
                          <td className="px-3 py-2.5 text-right text-amber-400">
                            {tradesCnt > 0 && dd > 0 ? `₹${dd.toFixed(0)}` : '-'}
                          </td>
                          <td className="px-3 py-2.5 text-center">
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                handleInspectDay(day);
                              }}
                              className="px-2.5 py-1 rounded bg-surface hover:bg-blue-600 hover:text-white border border-border text-gray-300 text-[11px] font-semibold transition-all inline-flex items-center gap-1 group-hover:border-blue-500/50"
                            >
                              <Eye className="w-3 h-3 text-blue-400 group-hover:text-white" />
                              <span>Inspect Chart</span>
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Day Inspection Modal (Section 4) */}
          {inspectDate && (
            <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-3 sm:p-6 overflow-y-auto">
              <div className="bg-card border border-border rounded-2xl w-full max-w-5xl shadow-2xl overflow-hidden max-h-[90vh] flex flex-col">
                {/* Modal Header */}
                <div className="px-6 py-4 border-b border-border flex items-center justify-between bg-surface/50">
                  <div className="flex items-center space-x-3">
                    <div className="p-2 rounded-xl bg-blue-600/10 text-blue-400 border border-blue-500/30">
                      <Calendar className="w-5 h-5" />
                    </div>
                    <div>
                      <div className="flex items-center space-x-2">
                        <h3 className="text-base font-bold text-white font-mono">
                          Backtest Day Inspection: {inspectDate}
                        </h3>
                        {inspectItem && (
                          <span
                            className={`px-2 py-0.5 rounded text-xs font-bold font-mono border ${
                              inspectItem.status === 'TRADED'
                                ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/40'
                                : inspectItem.status === 'NO_TRADE'
                                ? 'bg-amber-500/20 text-amber-300 border-amber-500/40'
                                : inspectItem.status === 'HOLIDAY'
                                ? 'bg-purple-500/20 text-purple-300 border-purple-500/40'
                                : inspectItem.status === 'WEEKEND'
                                ? 'bg-slate-500/20 text-slate-400 border-slate-500/40'
                                : 'bg-rose-500/20 text-rose-300 border-rose-500/40'
                            }`}
                          >
                            {inspectItem.status === 'TRADED'
                              ? `Traded (${formatCurrency(inspectItem.net_pnl)})`
                              : inspectItem.status === 'NO_TRADE'
                              ? 'No Trade'
                              : inspectItem.status === 'HOLIDAY'
                              ? 'Market Holiday'
                              : inspectItem.status === 'WEEKEND'
                              ? 'Weekend'
                              : 'Missing Data'}
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-gray-400 font-mono">
                        {inspectItem?.reason || 'Historical chart candles and execution markers for this date'}
                      </p>
                    </div>
                  </div>

                  <button
                    onClick={() => {
                      setInspectDate(null);
                      setInspectItem(null);
                      setInspectCandles([]);
                      setInspectMarkers([]);
                    }}
                    className="p-1.5 rounded-lg bg-surface border border-border text-gray-400 hover:text-white transition-colors"
                  >
                    <X className="w-5 h-5" />
                  </button>
                </div>

                {/* Modal Body */}
                <div className="p-6 overflow-y-auto space-y-5">
                  {/* Status Banner */}
                  {inspectItem?.status === 'NO_TRADE' && (
                    <div className="p-3.5 bg-amber-500/10 border border-amber-500/30 rounded-xl text-amber-300 text-xs font-mono flex items-center gap-2.5">
                      <AlertCircle className="w-4 h-4 text-amber-400 flex-shrink-0" />
                      <div>
                        <strong className="text-amber-200">No strategy entries generated on this trading day.</strong>
                        <span className="block text-[11px] text-amber-400/80 mt-0.5">
                          Strategy entry indicators did not satisfy trigger criteria during this session. The full historical chart is displayed below for audit verification.
                        </span>
                      </div>
                    </div>
                  )}

                  {inspectItem?.status === 'HOLIDAY' && (
                    <div className="p-3.5 bg-purple-500/10 border border-purple-500/30 rounded-xl text-purple-300 text-xs font-mono flex items-center gap-2.5">
                      <Calendar className="w-4 h-4 text-purple-400 flex-shrink-0" />
                      <div>
                        <strong>Official Exchange Holiday: {inspectItem.reason || 'Closed'}</strong>
                        <span className="block text-[11px] text-purple-400/80 mt-0.5">
                          The National Stock Exchange was closed on this date.
                        </span>
                      </div>
                    </div>
                  )}

                  {inspectItem?.status === 'WEEKEND' && (
                    <div className="p-3.5 bg-slate-500/10 border border-slate-500/30 rounded-xl text-slate-300 text-xs font-mono flex items-center gap-2.5">
                      <Calendar className="w-4 h-4 text-slate-400 flex-shrink-0" />
                      <div>
                        <strong>Exchange Closed: Weekend ({inspectItem.day_name})</strong>
                        <span className="block text-[11px] text-slate-400/80 mt-0.5">
                          Regular equity and derivatives trading is closed on Saturdays and Sundays.
                        </span>
                      </div>
                    </div>
                  )}

                  {inspectItem?.status === 'MISSING_DATA' && (
                    <div className="p-3.5 bg-rose-500/10 border border-rose-500/30 rounded-xl text-rose-300 text-xs font-mono flex items-center gap-2.5">
                      <AlertCircle className="w-4 h-4 text-rose-400 flex-shrink-0" />
                      <div>
                        <strong>Missing Historical Candles from Data Provider</strong>
                        <span className="block text-[11px] text-rose-400/80 mt-0.5">
                          Broker REST API returned 0 historical bars for this date. It is flagged as missing data and never marked as a no-trade day.
                        </span>
                      </div>
                    </div>
                  )}

                  {/* Historical Candlestick Chart */}
                  <div className="border border-border rounded-xl p-4 bg-surface/40 space-y-2">
                    <div className="flex items-center justify-between text-xs font-mono">
                      <span className="font-bold text-white flex items-center gap-1.5">
                        <TrendingUp className="w-4 h-4 text-blue-400" />
                        Historical Backtest Candlestick Chart ({result.contract_symbol || result.instrument})
                      </span>
                      <span className="text-gray-400 text-[11px]">
                        {inspectCandles.length} Bars | {inspectMarkers.length} Markers (BUY / EXIT / SL / TARGET)
                      </span>
                    </div>

                    {loadingInspectChart ? (
                      <div className="py-24 text-center font-mono text-xs text-gray-400 flex flex-col items-center justify-center gap-2">
                        <RotateCcw className="w-6 h-6 text-blue-400 animate-spin" />
                        Loading 1-minute historical candles for {inspectDate}...
                      </div>
                    ) : inspectCandles.length === 0 ? (
                      <div className="py-16 text-center font-mono text-xs text-gray-500 border border-dashed border-border rounded-xl">
                        No historical candle bars available for {inspectDate}.
                      </div>
                    ) : (
                      <ChartComponent
                        candles={inspectCandles}
                        tradeMarkers={inspectMarkers}
                        symbolName={result.contract_symbol || result.instrument || 'NIFTY ATM CE'}
                        height={380}
                      />
                    )}
                  </div>

                  {/* Executed Trades on this Date */}
                  <div className="border border-border rounded-xl overflow-hidden font-mono text-xs">
                    <div className="bg-surface/80 px-4 py-2.5 border-b border-border flex items-center justify-between">
                      <span className="font-bold text-white">
                        Executed Trades on {inspectDate} (
                        {result.trades.filter((t) => t.exit_time.startsWith(inspectDate) || t.entry_time.startsWith(inspectDate)).length} positions)
                      </span>
                      <span className="text-gray-400 text-[11px]">
                        Net P&amp;L: {inspectItem ? formatCurrency(inspectItem.net_pnl) : '₹0.00'}
                      </span>
                    </div>

                    {result.trades.filter((t) => t.exit_time.startsWith(inspectDate) || t.entry_time.startsWith(inspectDate)).length === 0 ? (
                      <div className="py-10 text-center font-mono text-xs text-gray-500">
                        No strategy entries generated on this trading day.
                      </div>
                    ) : (
                      <div className="overflow-x-auto max-h-[280px]">
                        <table className="w-full text-xs font-mono text-left">
                          <thead className="sticky top-0 bg-surface border-b border-border text-gray-400 uppercase text-[10px]">
                            <tr>
                              <th className="px-3 py-2">#</th>
                              <th className="px-3 py-2">Entry Time</th>
                              <th className="px-3 py-2">Exit Time</th>
                              <th className="px-3 py-2 text-right">Entry (₹)</th>
                              <th className="px-3 py-2 text-right">SL (₹)</th>
                              <th className="px-3 py-2 text-right">Target (₹)</th>
                              <th className="px-3 py-2 text-right">Exit (₹)</th>
                              <th className="px-3 py-2 text-right">Qty</th>
                              <th className="px-3 py-2">Reason</th>
                              <th className="px-3 py-2 text-right">Gross</th>
                              <th className="px-3 py-2 text-right">Charges</th>
                              <th className="px-3 py-2 text-right">Slippage</th>
                              <th className="px-3 py-2 text-right">Net P&amp;L</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-border/40">
                            {result.trades
                              .filter((t) => t.exit_time.startsWith(inspectDate) || t.entry_time.startsWith(inspectDate))
                              .map((t, idx) => (
                                <tr key={idx} className="hover:bg-surface/50">
                                  <td className="px-3 py-2 text-gray-500">#{t.trade_num || idx + 1}</td>
                                  <td className="px-3 py-2 text-gray-300">{t.entry_time.slice(11, 16)}</td>
                                  <td className="px-3 py-2 text-gray-300">{t.exit_time.slice(11, 16)}</td>
                                  <td className="px-3 py-2 text-right text-white font-bold">₹{t.entry_price.toFixed(2)}</td>
                                  <td className="px-3 py-2 text-right text-rose-300">
                                    ₹{(t.sl_trigger_price ?? t.stop).toFixed(2)}
                                  </td>
                                  <td className="px-3 py-2 text-right text-emerald-300">
                                    ₹{(t.target_trigger_price ?? t.target).toFixed(2)}
                                  </td>
                                  <td className="px-3 py-2 text-right text-blue-400 font-bold">₹{t.exit_price.toFixed(2)}</td>
                                  <td className="px-3 py-2 text-right">{t.quantity}</td>
                                  <td className="px-3 py-2">
                                    <span
                                      className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                                        t.exit_reason === 'TARGET'
                                          ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                                          : 'bg-rose-500/20 text-red-400 border border-red-500/30'
                                      }`}
                                    >
                                      {t.exit_reason}
                                    </span>
                                  </td>
                                  <td className={`px-3 py-2 text-right font-semibold ${getPnlColor(t.gross_pnl)}`}>
                                    {formatCurrency(t.gross_pnl)}
                                  </td>
                                  <td className="px-3 py-2 text-right text-gray-400">₹{t.charges.toFixed(2)}</td>
                                  <td className="px-3 py-2 text-right text-gray-400">
                                    ₹{Number(t.slippage_cost || 0).toFixed(2)}
                                  </td>
                                  <td className={`px-3 py-2 text-right font-bold ${getPnlColor(t.net_pnl)}`}>
                                    {formatCurrency(t.net_pnl)}
                                  </td>
                                </tr>
                              ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Trade-by-trade Table */}
          <div className="bg-card border border-border rounded-xl p-5">
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-bold text-white text-sm">Detailed Trade Log ({result.trades.length} Executions)</h3>
              <button
                onClick={handleExportCsv}
                className="text-xs text-blue-400 hover:text-blue-300 font-mono flex items-center gap-1"
              >
                <Download className="w-3.5 h-3.5" /> Download Full CSV
              </button>
            </div>

            <div className="overflow-x-auto max-h-[500px]">
              <table className="w-full text-xs font-mono text-left">
                <thead className="sticky top-0 bg-surface z-10">
                  <tr className="border-b border-border text-gray-400 uppercase text-[11px]">
                    <th className="px-3 py-2">#</th>
                    <th className="px-3 py-2">Entry Time</th>
                    <th className="px-3 py-2">Exit Time</th>
                    <th className="px-3 py-2 text-right">Hold (m)</th>
                    <th className="px-3 py-2">Contract</th>
                    <th className="px-3 py-2">Mode</th>
                    <th className="px-3 py-2 text-right">Entry (₹)</th>
                    <th className="px-3 py-2 text-right">SL Trigger (₹)</th>
                    <th className="px-3 py-2 text-right">Target Trigger (₹)</th>
                    <th className="px-3 py-2 text-right">Exit (₹)</th>
                    <th className="px-3 py-2 text-right">Slippage (₹)</th>
                    <th className="px-3 py-2 text-right">Qty</th>
                    <th className="px-3 py-2">Exit Reason</th>
                    <th className="px-3 py-2 text-right">Gross</th>
                    <th className="px-3 py-2 text-right">Charges</th>
                    <th className="px-3 py-2 text-right">Net P&amp;L</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/40">
                  {result.trades.map((t, idx) => (
                    <tr key={idx} className="hover:bg-surface/40">
                      <td className="px-3 py-2 text-gray-500">#{t.trade_num || idx + 1}</td>
                      <td className="px-3 py-2 text-gray-400">{t.entry_time.slice(0, 16)}</td>
                      <td className="px-3 py-2 text-gray-400">{t.exit_time.slice(0, 16)}</td>
                      <td className="px-3 py-2 text-right text-gray-400">{t.holding_time_minutes || 1}</td>
                      <td className="px-3 py-2 font-bold text-white">{t.option_symbol}</td>
                      <td className="px-3 py-2">
                        <span className="px-1.5 py-0.5 rounded text-[9px] font-mono bg-surface border border-border text-gray-300">
                          {t.execution_mode || "TRIGGER_PRICE"}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-right text-white">₹{t.entry_price.toFixed(2)}</td>
                      <td className="px-3 py-2 text-right text-red-300">
                        ₹{(t.sl_trigger_price ?? t.stop).toFixed(2)}
                        <span className="text-[10px] text-gray-500 block">
                          -{t.effective_sl_points ? t.effective_sl_points.toFixed(2) : (t.configured_sl_points ?? 2.0).toFixed(2)} pts
                        </span>
                      </td>
                      <td className="px-3 py-2 text-right text-emerald-300">
                        ₹{(t.target_trigger_price ?? t.target).toFixed(2)}
                        <span className="text-[10px] text-gray-500 block">
                          +{(t.effective_target_points ?? t.configured_target_points ?? 4.0).toFixed(2)} pts
                        </span>
                      </td>
                      <td className="px-3 py-2 text-right text-blue-400 font-bold">₹{t.exit_price.toFixed(2)}</td>
                      <td className="px-3 py-2 text-right text-gray-400">
                        ₹{Number(t.slippage_cost || 0).toFixed(2)}
                      </td>
                      <td className="px-3 py-2 text-right">{t.quantity}</td>
                      <td className="px-3 py-2">
                        <div className="flex items-center gap-1">
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                              t.exit_reason === 'TARGET'
                                ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                                : t.exit_reason === 'UT_SELL_SIGNAL'
                                ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30'
                                : 'bg-red-500/20 text-red-400 border border-red-500/30'
                            }`}
                          >
                            {t.exit_reason}
                          </span>
                          {t.is_ambiguous && (
                            <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30" title="Both SL and Target touched within same candle; conservative stop loss applied">
                              AMBIGUOUS
                            </span>
                          )}
                        </div>
                      </td>
                      <td className={`px-3 py-2 text-right font-semibold ${getPnlColor(t.gross_pnl)}`}>
                        {formatCurrency(t.gross_pnl)}
                      </td>
                      <td className="px-3 py-2 text-right text-gray-400">₹{t.charges.toFixed(2)}</td>
                      <td className={`px-3 py-2 text-right font-bold ${getPnlColor(t.net_pnl)}`}>
                        {formatCurrency(t.net_pnl)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
            </>
          )}
        </div>
      )}

      {/* Backtest Run History Section */}
      <div className="bg-card border border-border rounded-xl p-5 shadow-lg space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center space-x-3">
            <div className="p-2 rounded-lg bg-blue-600/10 text-blue-400 border border-blue-500/30">
              <History className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-bold text-white text-base">Backtest Run History</h3>
              <p className="text-xs text-gray-400 font-mono">
                Saved historical runs with audited performance and direct Analytics inspection
              </p>
            </div>
          </div>
          <button
            onClick={loadPastRuns}
            disabled={loadingRuns}
            className="px-3 py-1.5 rounded-lg bg-surface border border-border hover:bg-surface/80 text-gray-300 hover:text-white text-xs font-mono flex items-center gap-1.5 transition-all"
          >
            <RotateCcw className={`w-3.5 h-3.5 ${loadingRuns ? 'animate-spin text-blue-400' : ''}`} />
            Refresh Runs
          </button>
        </div>

        {pastRuns.length === 0 ? (
          <div className="py-8 text-center border border-dashed border-border rounded-xl text-xs font-mono text-gray-500">
            No completed backtest runs found. Configure parameters above and click "Run Backtest".
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs font-mono text-left">
              <thead>
                <tr className="bg-surface/60 border-b border-border text-gray-400 uppercase text-[11px]">
                  <th className="px-3 py-2.5">Run</th>
                  <th className="px-3 py-2.5">Strategy</th>
                  <th className="px-3 py-2.5">Instrument</th>
                  <th className="px-3 py-2.5">Date Range</th>
                  <th className="px-3 py-2.5">Timeframe</th>
                  <th className="px-3 py-2.5 text-right">Trades</th>
                  <th className="px-3 py-2.5 text-right">Win Rate</th>
                  <th className="px-3 py-2.5 text-right">Net P&amp;L</th>
                  <th className="px-3 py-2.5 text-right">Profit Factor</th>
                  <th className="px-3 py-2.5 text-right">Max DD</th>
                  <th className="px-3 py-2.5">Run Time</th>
                  <th className="px-3 py-2.5 text-center">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/40">
                {pastRuns.map((r) => {
                  const runId = r.id || r.run_id || 0;
                  return (
                    <tr key={runId} className="hover:bg-surface/40 transition-colors">
                      <td className="px-3 py-2.5 font-bold text-blue-400">#{runId}</td>
                      <td className="px-3 py-2.5 text-white font-medium">{r.strategy_name || r.strategy_id}</td>
                      <td className="px-3 py-2.5 text-gray-300">{r.instrument_symbol}</td>
                      <td className="px-3 py-2.5 text-gray-400">{r.start_date} &rarr; {r.end_date}</td>
                      <td className="px-3 py-2.5 text-gray-400">{r.timeframe || '1m'}</td>
                      <td className="px-3 py-2.5 text-right text-gray-200">{r.total_trades}</td>
                      <td className="px-3 py-2.5 text-right text-blue-300 font-semibold">{r.win_rate.toFixed(1)}%</td>
                      <td className={`px-3 py-2.5 text-right font-bold ${getPnlColor(r.net_profit)}`}>
                        {formatCurrency(r.net_profit)}
                      </td>
                      <td className="px-3 py-2.5 text-right text-gray-300">
                        {r.profit_factor !== undefined ? r.profit_factor.toFixed(2) : '-'}
                      </td>
                      <td className="px-3 py-2.5 text-right text-rose-400">
                        {r.max_drawdown !== undefined ? formatCurrency(r.max_drawdown) : '-'}
                      </td>
                      <td className="px-3 py-2.5 text-gray-500 text-[10px]">
                        {r.created_at ? formatIST(r.created_at) : '-'}
                      </td>
                      <td className="px-3 py-2.5 text-center">
                        <div className="flex items-center justify-center gap-1.5">
                          <button
                            onClick={() => loadRunDetails(runId)}
                            className="px-2.5 py-1 rounded bg-blue-600/20 hover:bg-blue-600/30 text-blue-300 border border-blue-500/30 hover:border-blue-400 text-[11px] font-bold flex items-center gap-1 transition-all"
                            title="Load this backtest run into results view"
                          >
                            <Eye className="w-3 h-3 text-blue-400" />
                            View
                          </button>
                          {onNavigateToAnalytics && (
                            <button
                              onClick={() => onNavigateToAnalytics(runId)}
                              className="px-2.5 py-1 rounded bg-purple-600/20 hover:bg-purple-600/30 text-purple-300 border border-purple-500/30 hover:border-purple-400 text-[11px] font-bold flex items-center gap-1 transition-all"
                              title="Open in Analytics with this Run ID"
                            >
                              <PieChart className="w-3 h-3 text-purple-400" />
                              View Analytics
                            </button>
                          )}
                          <a
                            href={api.getBacktestCsvUrl(runId)}
                            download
                            className="p-1 rounded bg-surface hover:bg-surface/80 text-gray-400 hover:text-white border border-border"
                            title="Download Run CSV"
                          >
                            <Download className="w-3.5 h-3.5 text-gray-400" />
                          </a>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
        </>
      )}
    </div>
  );
};
