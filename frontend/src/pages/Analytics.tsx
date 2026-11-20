import React, { useEffect, useState } from 'react';
import {
  PieChart,
  DollarSign,
  Percent,
  AlertTriangle,
  RotateCcw,
  Sliders,
  Layers,
  Activity,
  History,
  CheckCircle2,
  Calendar
} from 'lucide-react';
import { AnalyticsSummary, BacktestRunItem } from '../types';
import { api } from '../services/api';
import { StatCard } from '../components/StatCard';
import { formatCurrency, getPnlColor, normalizeDailyAnalytics } from '../utils/formatters';
import { PerformanceCalendar } from '../components/PerformanceCalendar';

interface AnalyticsProps {
  initialSource?: 'PAPER' | 'BACKTEST';
  initialRunId?: number;
}

export const Analytics: React.FC<AnalyticsProps> = ({
  initialSource = 'PAPER',
  initialRunId,
}) => {
  const [source, setSource] = useState<'PAPER' | 'BACKTEST'>(initialSource);
  const [selectedRunId, setSelectedRunId] = useState<number | undefined>(initialRunId);
  const [strategyFilter, setStrategyFilter] = useState<string>('ALL');
  const [executionModeFilter, setExecutionModeFilter] = useState<string>('ALL');

  const [data, setData] = useState<AnalyticsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const [backtestRuns, setBacktestRuns] = useState<BacktestRunItem[]>([]);
  const [loadingRuns, setLoadingRuns] = useState<boolean>(false);

  // Sync with prop changes when navigating from Backtesting page
  useEffect(() => {
    if (initialSource) setSource(initialSource);
    if (initialRunId) setSelectedRunId(initialRunId);
  }, [initialSource, initialRunId]);

  // Load available backtest runs for the selector dropdown
  const loadBacktestRuns = async () => {
    setLoadingRuns(true);
    try {
      const runs = await api.getAnalyticsBacktestRuns();
      setBacktestRuns(runs);
      // Auto-select latest run if in BACKTEST mode and no run is currently selected
      if (source === 'BACKTEST' && !selectedRunId && runs.length > 0) {
        setSelectedRunId(runs[0].id || runs[0].run_id);
      }
    } catch (e) {
      console.error('Failed to load backtest runs for analytics dropdown', e);
    } finally {
      setLoadingRuns(false);
    }
  };

  useEffect(() => {
    loadBacktestRuns();
  }, [source]);

  // Load analytics summary metrics for the selected source & filters
  const loadAnalytics = async () => {
    setLoading(true);
    setErrorMsg(null);
    try {
      const summary = await api.getAnalyticsSummary({
        source,
        run_id: source === 'BACKTEST' ? selectedRunId : undefined,
        strategy_id: strategyFilter !== 'ALL' ? strategyFilter : undefined,
        execution_mode: executionModeFilter !== 'ALL' ? executionModeFilter : undefined,
      });
      setData(summary);
    } catch (e: any) {
      console.error('Failed to load analytics summary:', e);
      setErrorMsg(e.message || 'Failed to load analytics summary');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAnalytics();
  }, [source, selectedRunId, strategyFilter, executionModeFilter]);

  // Active run details if in BACKTEST mode
  const currentRun = source === 'BACKTEST' && selectedRunId
    ? backtestRuns.find((r) => (r.id || r.run_id) === selectedRunId)
    : null;

  return (
    <div className="space-y-6">
      {/* Header & Source Control Toolbar */}
      <div className="bg-card border border-border rounded-xl p-5 shadow-lg space-y-4">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div className="flex items-center space-x-3">
            <div className="p-2.5 rounded-xl bg-purple-600/10 text-purple-400 border border-purple-500/30">
              <PieChart className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h2 className="text-lg font-bold text-white tracking-wide">Performance Analytics &amp; Risk Telemetry</h2>
                <span
                  className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold border ${
                    source === 'BACKTEST'
                      ? 'bg-purple-500/10 text-purple-300 border-purple-500/30'
                      : 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30'
                  }`}
                >
                  {source === 'BACKTEST' ? `BACKTEST REPLAY${selectedRunId ? ` #` + selectedRunId : ''}` : 'PAPER TRADING'}
                </span>
              </div>
              <p className="text-xs text-gray-400 font-mono">
                {source === 'BACKTEST'
                  ? 'Reconciled analytics from verified historical backtest execution run'
                  : 'Live paper trading executions, drawdowns, and real-time equity accounting'}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={loadAnalytics}
              disabled={loading}
              className="px-3 py-1.5 rounded-lg bg-surface border border-border hover:bg-surface/80 text-gray-300 hover:text-white text-xs font-mono flex items-center gap-1.5 transition-all"
            >
              <RotateCcw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-blue-400' : ''}`} />
              Refresh
            </button>
          </div>
        </div>

        {/* Source & Filter Controls Row */}
        <div className="flex flex-wrap items-center justify-between gap-3 pt-3 border-t border-border/50 text-xs font-mono">
          <div className="flex flex-wrap items-center gap-3">
            {/* Primary Source Toggle */}
            <div className="flex items-center space-x-1.5">
              <span className="text-gray-400">Source:</span>
              <div className="bg-surface rounded-lg border border-border p-0.5 flex">
                <button
                  onClick={() => setSource('PAPER')}
                  className={`px-3 py-1.5 rounded-md text-xs font-bold transition-all ${
                    source === 'PAPER'
                      ? 'bg-emerald-600/30 text-emerald-300 border border-emerald-500/40 shadow-sm'
                      : 'text-gray-400 hover:text-white'
                  }`}
                >
                  Paper Trading
                </button>
                <button
                  onClick={() => setSource('BACKTEST')}
                  className={`px-3 py-1.5 rounded-md text-xs font-bold transition-all ${
                    source === 'BACKTEST'
                      ? 'bg-purple-600/30 text-purple-300 border border-purple-500/40 shadow-sm'
                      : 'text-gray-400 hover:text-white'
                  }`}
                >
                  Backtest Replay
                </button>
              </div>
            </div>

            {/* Backtest Run Selector (Only when in BACKTEST mode) */}
            {source === 'BACKTEST' && (
              <div className="flex items-center space-x-1.5">
                <span className="text-gray-400">Run:</span>
                {backtestRuns.length === 0 ? (
                  <span className="text-amber-400 bg-surface px-2.5 py-1 rounded border border-border">
                    No runs found
                  </span>
                ) : (
                  <select
                    value={selectedRunId || ''}
                    onChange={(e) => setSelectedRunId(parseInt(e.target.value, 10))}
                    className="bg-surface border border-purple-500/40 text-purple-200 rounded-lg px-2.5 py-1.5 font-bold focus:outline-none focus:border-purple-400 shadow-sm"
                  >
                    {backtestRuns.map((r) => {
                      const runId = r.id || r.run_id || 0;
                      return (
                        <option key={runId} value={runId} className="bg-surface text-white">
                          Run #{runId} &mdash; {r.strategy_name || r.strategy_id} ({r.total_trades} trades &bull; {formatCurrency(r.net_profit)})
                        </option>
                      );
                    })}
                  </select>
                )}
              </div>
            )}

            {/* Strategy Filter */}
            <div className="flex items-center space-x-1.5">
              <span className="text-gray-400">Strategy:</span>
              <select
                value={strategyFilter}
                onChange={(e) => setStrategyFilter(e.target.value)}
                className="bg-surface border border-border rounded-lg px-2.5 py-1.5 text-white font-medium focus:outline-none focus:border-blue-500"
              >
                <option value="ALL">All Strategies</option>
                <option value="SUPERTREND_EMA">Supertrend EMA Scalper</option>
                <option value="UT_BOT">UT Bot ATM Option</option>
                <option value="EMA_RSI">NIFTY EMA / RSI</option>
              </select>
            </div>

            {/* Execution Mode Filter */}
            <div className="flex items-center space-x-1.5">
              <span className="text-gray-400">Mode:</span>
              <select
                value={executionModeFilter}
                onChange={(e) => setExecutionModeFilter(e.target.value)}
                className="bg-surface border border-border rounded-lg px-2.5 py-1.5 text-white font-medium focus:outline-none focus:border-blue-500"
              >
                <option value="ALL">All Modes</option>
                <option value="TRIGGER_PRICE">Trigger Price (Strict)</option>
                <option value="REALISTIC">Realistic (Slippage)</option>
              </select>
            </div>
          </div>

          {/* Active Run Telemetry Badge */}
          {currentRun && (
            <div className="hidden xl:flex items-center space-x-2 text-[11px] text-gray-400">
              <span className="text-gray-500">Contract:</span>
              <span className="text-white font-bold">{currentRun.instrument_symbol}</span>
              <span className="text-gray-500">&bull; Range:</span>
              <span className="text-gray-300">{currentRun.start_date} &rarr; {currentRun.end_date}</span>
            </div>
          )}
        </div>
      </div>

      {errorMsg && (
        <div className="p-4 rounded-xl bg-rose-950/40 border border-rose-800 text-rose-300 text-xs font-mono flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
            <span>{errorMsg}</span>
          </div>
          <button
            onClick={loadAnalytics}
            className="px-2.5 py-1 rounded bg-rose-800/60 hover:bg-rose-700 text-white text-[11px] font-bold"
          >
            Retry
          </button>
        </div>
      )}

      {/* Primary KPI Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <StatCard
          title="NET PROFIT"
          value={formatCurrency(data?.net_profit || 0)}
          trend={(data?.net_profit || 0) >= 0 ? 'up' : 'down'}
          icon={<DollarSign className="w-4 h-4" />}
        />
        <StatCard
          title="WIN RATE"
          value={`${data?.win_rate || 0}%`}
          subValue={`${data?.winning_trades || 0}W / ${data?.losing_trades || 0}L`}
          trend={(data?.win_rate || 0) >= 50 ? 'up' : 'down'}
          icon={<Percent className="w-4 h-4" />}
        />
        <StatCard
          title="PROFIT FACTOR"
          value={data?.profit_factor ? data.profit_factor.toFixed(2) : '0.00'}
          subValue={`Gross: ${formatCurrency(data?.gross_profit || 0)}`}
          trend={(data?.profit_factor || 0) >= 1.5 ? 'up' : 'neutral'}
        />
        <StatCard
          title="MAX DRAWDOWN"
          value={formatCurrency(data?.max_drawdown || 0)}
          subValue={`Drawdown: ${data?.max_drawdown_percent || 0}%`}
          trend="down"
          icon={<AlertTriangle className="w-4 h-4" />}
        />
        <StatCard
          title="AVG WIN TRADE"
          value={formatCurrency(data?.avg_profit_per_trade || 0)}
          trend="up"
        />
        <StatCard
          title="AVG LOSS TRADE"
          value={formatCurrency(data?.avg_loss_per_trade || 0)}
          trend="down"
        />
      </div>

      {/* Secondary Metrics */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-card border border-border rounded-xl p-4 font-mono text-xs space-y-1">
          <span className="text-gray-400 block mb-1">Largest Winning Trade</span>
          <div className="text-lg font-bold text-emerald-400">{formatCurrency(data?.largest_winning_trade || 0)}</div>
          <span className="text-[11px] text-gray-500">Max favorable run</span>
        </div>

        <div className="bg-card border border-border rounded-xl p-4 font-mono text-xs space-y-1">
          <span className="text-gray-400 block mb-1">Largest Losing Trade</span>
          <div className="text-lg font-bold text-rose-500">{formatCurrency(data?.largest_losing_trade || 0)}</div>
          <span className="text-[11px] text-gray-500">Capped at ₹1,000 / gap fill</span>
        </div>

        <div className="bg-card border border-border rounded-xl p-4 font-mono text-xs space-y-1">
          <span className="text-gray-400 block mb-1">Max Streaks</span>
          <div className="text-lg font-bold text-white">
            <span className="text-emerald-400">{data?.consecutive_wins_max || 0} Wins</span> /{' '}
            <span className="text-rose-400">{data?.consecutive_losses_max || 0} Losses</span>
          </div>
          <span className="text-[11px] text-gray-500">Consecutive runs</span>
        </div>

        <div className="bg-card border border-border rounded-xl p-4 font-mono text-xs space-y-1">
          <span className="text-gray-400 block mb-1">Statutory Charges</span>
          <div className="text-lg font-bold text-gray-300">{formatCurrency(data?.total_brokerage_charges || 0)}</div>
          <span className="text-[11px] text-gray-500">STT, Brokerage, GST, SEBI</span>
        </div>
      </div>

      {/* Performance Calendar — Monthly, Yearly & Custom Range */}
      <PerformanceCalendar
        key={`${source}-${selectedRunId}-${strategyFilter}-${executionModeFilter}`}
        embedded={true}
        initialSource={source}
        initialRunId={source === 'BACKTEST' ? selectedRunId : undefined}
      />

      {/* Daily Breakdown Table */}
      <div className="bg-card border border-border rounded-xl p-5 shadow-lg">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-bold text-white text-sm">
            Daily Performance Summary &bull; {source === 'BACKTEST' ? `Backtest Run #${selectedRunId || ''}` : 'Paper Trading'}
          </h3>
          <span className="text-xs text-gray-400 font-mono">
            {data?.daily_summary?.length || 0} Trading Session(s) Recorded
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-xs font-mono text-left min-w-[620px]">
            <thead>
              <tr className="bg-surface/60 border-b border-border text-gray-400 uppercase text-[11px] whitespace-nowrap">
                <th className="px-4 py-2">Date</th>
                <th className="px-4 py-2 text-right">Trades</th>
                <th className="px-4 py-2 text-right">Wins</th>
                <th className="px-4 py-2 text-right">Losses</th>
                <th className="px-4 py-2 text-right">Gross Profit (₹)</th>
                <th className="px-4 py-2 text-right">Gross Loss (₹)</th>
                <th className="px-4 py-2 text-right">Charges (₹)</th>
                <th className="px-4 py-2 text-right">Net P&amp;L</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/40 whitespace-nowrap">
              {!data?.daily_summary || data.daily_summary.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-6 text-center text-gray-500">
                    No daily trading data recorded for this selection.
                  </td>
                </tr>
              ) : (
                data.daily_summary.map((rawDay, i) => {
                  const day = normalizeDailyAnalytics(rawDay);
                  return (
                    <tr key={i} className="hover:bg-surface/40 transition-colors">
                      <td className="px-4 py-2 text-white font-bold">{day.date}</td>
                      <td className="px-4 py-2 text-right text-gray-300">{Number(day?.trades ?? 0)}</td>
                      <td className="px-4 py-2 text-right text-emerald-400">{Number(day?.wins ?? 0)}</td>
                      <td className="px-4 py-2 text-right text-rose-400">{Number(day?.losses ?? 0)}</td>
                      <td className="px-4 py-2 text-right text-emerald-400">₹{Number(day?.grossProfit ?? 0).toFixed(2)}</td>
                      <td className="px-4 py-2 text-right text-rose-400">₹{Number(day?.grossLoss ?? 0).toFixed(2)}</td>
                      <td className="px-4 py-2 text-right text-gray-400">₹{Number(day?.charges ?? 0).toFixed(2)}</td>
                      <td className={`px-4 py-2 text-right font-bold ${getPnlColor(Number(day?.pnl ?? 0))}`}>
                        {formatCurrency(Number(day?.pnl ?? 0))}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
