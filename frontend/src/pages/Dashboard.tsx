import React, { useEffect, useState } from 'react';
import {
  Activity,
  DollarSign,
  TrendingUp,
  Percent,
  CheckCircle2,
  XCircle,
  Clock,
  Layers,
  ArrowUpRight,
  ShieldAlert,
  Calendar,
  Timer,
  AlertTriangle,
} from 'lucide-react';
import { MarketStatus, PaperAccountStatus, StrategyStatus, Candle, DailyAnalytics, AutoExitSettings } from '../types';
import { StatCard } from '../components/StatCard';
import { ChartComponent } from '../components/ChartComponent';
import { formatCurrency, formatIST, getPnlColor, getPnlBg, normalizeDailyAnalytics, formatCharges } from '../utils/formatters';
import { api } from '../services/api';

interface DashboardProps {
  marketStatus: MarketStatus | null;
  paperStatus: PaperAccountStatus | null;
  strategyStatus: StrategyStatus | null;
  candles: Candle[];
  onOpenTrade: () => void;
  onCloseTrade: () => void;
  onNavigateTab: (tab: string) => void;
}

export const Dashboard: React.FC<DashboardProps> = ({
  marketStatus,
  paperStatus,
  strategyStatus,
  candles,
  onOpenTrade,
  onCloseTrade,
  onNavigateTab,
}) => {
  const isBuy = strategyStatus?.is_buy ?? false;
  const activePos = paperStatus?.active_position;

  const [dailySummary, setDailySummary] = useState<DailyAnalytics[]>([]);
  const [autoExit, setAutoExit] = useState<AutoExitSettings | null>(paperStatus?.auto_exit_settings || null);

  useEffect(() => {
    if (paperStatus?.auto_exit_settings) {
      setAutoExit(paperStatus.auto_exit_settings);
    }
  }, [paperStatus?.auto_exit_settings]);

  useEffect(() => {
    const fetchAutoExit = () => {
      api.getAutoExitSettings()
        .then(setAutoExit)
        .catch(() => {});
    };
    fetchAutoExit();
    const interval = setInterval(fetchAutoExit, 15000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    api
      .getAnalyticsSummary()
      .then((res) => {
        if (res && Array.isArray(res.daily_summary)) {
          const normalized = res.daily_summary.map((day) => normalizeDailyAnalytics(day));
          setDailySummary(normalized);
        } else {
          setDailySummary([]);
        }
      })
      .catch(() => {
        setDailySummary([]);
      });
  }, [paperStatus?.total_trades]);

  return (
    <div className="space-y-5">
      {/* Critical Paper Trading Notice Banner */}
      <div className="bg-amber-500/10 border border-amber-500/30 rounded-xl p-3 flex flex-col sm:flex-row sm:items-center justify-between gap-2.5">
        <div className="flex items-center space-x-3 text-xs text-amber-200">
          <ShieldAlert className="w-4 h-4 text-amber-400 shrink-0" />
          <span>
            <strong>VIRTUAL PAPER TRADING ENVIRONMENT:</strong> All orders, executions, and positions are simulated.
            Real-money order routing to Kotak Neo is strictly prohibited and disabled in software.
          </span>
        </div>
        <span className="text-[11px] font-mono font-semibold px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 shrink-0 self-start sm:self-auto">
          MAX LOSS PER TRADE: ₹1,000
        </span>
      </div>

      {/* Row 1: Key Metrics Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <StatCard
          title="NIFTY 50 SPOT"
          value={marketStatus?.nifty_price ? marketStatus.nifty_price.toFixed(2) : '24,500.00'}
          subValue="NSE Index"
          icon={<Activity className="w-4 h-4" />}
          trend="up"
        />

        <StatCard
          title={marketStatus?.option_symbol || 'ATM CE PREMIUM'}
          value={marketStatus?.option_premium ? `₹${marketStatus.option_premium.toFixed(2)}` : '₹145.00'}
          subValue={`Strike: ${marketStatus?.atm_strike || 24500}`}
          icon={<Layers className="w-4 h-4" />}
          trend="neutral"
        />

        <StatCard
          title="PAPER CAPITAL"
          value={formatCurrency(paperStatus?.cash_balance || 100000)}
          subValue={`Init: ₹1,00,000`}
          icon={<DollarSign className="w-4 h-4" />}
        />

        <StatCard
          title="DAILY P&L (NET)"
          value={formatCurrency(paperStatus?.daily_pnl || 0)}
          subValue={`Realized: ${formatCurrency(paperStatus?.realized_pnl || 0)}`}
          icon={<TrendingUp className="w-4 h-4" />}
          trend={(paperStatus?.daily_pnl || 0) >= 0 ? 'up' : 'down'}
        />

        <StatCard
          title="WIN RATE"
          value={`${paperStatus?.win_rate || 0}%`}
          subValue={`Total Trades: ${paperStatus?.total_trades || 0}`}
          icon={<Percent className="w-4 h-4" />}
        />

        <StatCard
          title="CURRENT SIGNAL"
          value={strategyStatus?.signal || 'NONE'}
          subValue={strategyStatus?.time_ist ? `Candle: ${strategyStatus.time_ist} IST` : 'Evaluating...'}
          trend={isBuy ? 'up' : 'neutral'}
          badge={isBuy ? 'BUY ATM CE' : 'WAITING'}
        />
      </div>

      {/* Auto Exit Status & Telemetry Card */}
      <div className="bg-card border border-border rounded-xl p-4">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border/50 pb-3">
          <div className="flex items-center space-x-3">
            <div className="p-2 rounded-lg bg-amber-500/10 text-amber-400 border border-amber-500/30">
              <Clock className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-bold text-sm text-white">Auto Close Telemetry</span>
                <span
                  className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded border ${
                    autoExit?.enabled
                      ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
                      : 'bg-gray-800 text-gray-400 border-gray-700'
                  }`}
                >
                  {autoExit?.enabled ? 'AUTO CLOSE: ENABLED' : 'AUTO CLOSE: DISABLED'}
                </span>
                {autoExit?.session_cutoff_active && (
                  <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-rose-500/20 text-rose-300 border border-rose-500/30">
                    SESSION CUTOFF ACTIVE
                  </span>
                )}
              </div>
              <span className="text-xs text-gray-400 font-mono">
                Mandatory square-off at {autoExit?.auto_close_time_display || '03:20 PM IST'} to eliminate overnight gap risk
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => onNavigateTab('settings')}
              className="px-3 py-1.5 rounded-lg bg-surface border border-border hover:border-blue-500/50 text-xs font-mono text-blue-400 hover:text-blue-300 transition-colors flex items-center gap-1.5"
            >
              Configure Time &rarr;
            </button>
          </div>
        </div>

        {autoExit?.awaiting_valid_data && autoExit?.execution_warning && (
          <div className="mt-3 p-3 rounded-lg bg-amber-950/40 border border-amber-500/40 text-amber-300 text-xs font-mono flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0 text-amber-400 mt-0.5" />
            <div className="space-y-0.5">
              <span className="font-bold">Execution Warning: Feed Disconnected or Stale</span>
              <p className="text-[11px] text-amber-200/80">{autoExit.execution_warning}</p>
            </div>
          </div>
        )}

        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-5 gap-3 mt-3 text-xs font-mono">
          <div className="p-2.5 rounded-lg bg-surface/60 border border-border">
            <span className="text-gray-500 text-[10px] uppercase block mb-0.5">Scheduled Exit</span>
            <div className="text-sm font-bold text-white">
              {autoExit?.auto_close_time_display || '03:20 PM IST'}
            </div>
            <span className="text-[10px] text-gray-400">({autoExit?.auto_close_time || '15:20'} 24h)</span>
          </div>

          <div className="p-2.5 rounded-lg bg-surface/60 border border-border">
            <span className="text-gray-500 text-[10px] uppercase block mb-0.5">Time Remaining</span>
            <div className="text-sm font-bold text-amber-400 flex items-center gap-1">
              <Timer className="w-3.5 h-3.5 shrink-0" />
              {autoExit?.time_remaining_display || '0m 0s'}
            </div>
            <span className="text-[10px] text-gray-400">Live countdown</span>
          </div>

          <div className="p-2.5 rounded-lg bg-surface/60 border border-border">
            <span className="text-gray-500 text-[10px] uppercase block mb-0.5">Open Positions</span>
            <div className="text-sm font-bold text-white">
              {activePos ? '1 Active Position' : '0 Open Positions'}
            </div>
            <span className="text-[10px] text-gray-400">
              {activePos ? activePos.symbol : 'Clean ledger'}
            </span>
          </div>

          <div className="p-2.5 rounded-lg bg-surface/60 border border-border">
            <span className="text-gray-500 text-[10px] uppercase block mb-0.5">Unrealized P&amp;L</span>
            <div className={`text-sm font-bold ${activePos ? getPnlColor(activePos.net_pnl) : 'text-gray-400'}`}>
              {activePos ? formatCurrency(activePos.net_pnl) : '₹0.00'}
            </div>
            <span className="text-[10px] text-gray-400">After charges</span>
          </div>

          <div className="col-span-2 sm:col-span-4 lg:col-span-1 p-2.5 rounded-lg bg-surface/60 border border-border">
            <span className="text-gray-500 text-[10px] uppercase block mb-0.5">Last Exit Status</span>
            <div className="text-[11px] font-semibold text-white truncate" title={autoExit?.last_status || 'STANDBY'}>
              {autoExit?.last_status || 'STANDBY'}
            </div>
            <span className="text-[10px] text-gray-400">Audit trail logged</span>
          </div>
        </div>
      </div>

      {/* Row 2: Strategy Condition Matrix & Active Position Callout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Left 2 Cols: 4 Conditions Evaluation Card */}
        <div className="lg:col-span-2 bg-card border border-border rounded-xl p-4">
          <div className="flex items-center justify-between mb-3 border-b border-border/50 pb-2">
            <div className="flex items-center space-x-2">
              <span className="font-semibold text-sm text-white">Original Strategy Conditions</span>
              <span className="text-[11px] text-gray-400 font-mono">(1-Minute Completed Candles)</span>
            </div>
            <span
              className={`text-xs px-2.5 py-1 rounded font-mono font-bold ${
                isBuy
                  ? 'bg-emerald-950/60 text-emerald-300 border border-emerald-700/60 animate-pulse'
                  : 'bg-gray-800 text-gray-400'
              }`}
            >
              STATE: {strategyStatus?.signal || 'WAITING'}
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs font-mono">
            {/* Condition 1 */}
            <div
              className={`p-3 rounded-lg border flex items-start space-x-2.5 ${
                strategyStatus?.condition_1
                  ? 'bg-emerald-950/20 border-emerald-800/40 text-emerald-300'
                  : 'bg-surface/60 border-border text-gray-400'
              }`}
            >
              {strategyStatus?.condition_1 ? (
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
              ) : (
                <XCircle className="w-4 h-4 text-gray-500 shrink-0 mt-0.5" />
              )}
              <div>
                <div className="font-semibold">Condition 1: EMA 9 &gt; EMA 21</div>
                <div className="text-[11px] text-gray-400 mt-0.5">
                  Fast EMA: {strategyStatus?.ema_9?.toFixed(1) || '--'} | Med EMA: {strategyStatus?.ema_21?.toFixed(1) || '--'}
                </div>
              </div>
            </div>

            {/* Condition 2 */}
            <div
              className={`p-3 rounded-lg border flex items-start space-x-2.5 ${
                strategyStatus?.condition_2
                  ? 'bg-emerald-950/20 border-emerald-800/40 text-emerald-300'
                  : 'bg-surface/60 border-border text-gray-400'
              }`}
            >
              {strategyStatus?.condition_2 ? (
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
              ) : (
                <XCircle className="w-4 h-4 text-gray-500 shrink-0 mt-0.5" />
              )}
              <div>
                <div className="font-semibold">Condition 2: NIFTY Close &gt; EMA 50</div>
                <div className="text-[11px] text-gray-400 mt-0.5">
                  Close: {strategyStatus?.underlying_price?.toFixed(1) || '--'} | Slow EMA: {strategyStatus?.ema_50?.toFixed(1) || '--'}
                </div>
              </div>
            </div>

            {/* Condition 3 */}
            <div
              className={`p-3 rounded-lg border flex items-start space-x-2.5 ${
                strategyStatus?.condition_3
                  ? 'bg-emerald-950/20 border-emerald-800/40 text-emerald-300'
                  : 'bg-surface/60 border-border text-gray-400'
              }`}
            >
              {strategyStatus?.condition_3 ? (
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
              ) : (
                <XCircle className="w-4 h-4 text-gray-500 shrink-0 mt-0.5" />
              )}
              <div>
                <div className="font-semibold">Condition 3: RSI 14 &gt; 50.0</div>
                <div className="text-[11px] text-gray-400 mt-0.5">
                  Current RSI: {strategyStatus?.rsi_14?.toFixed(2) || '--'} (Wilder's RSI)
                </div>
              </div>
            </div>

            {/* Condition 4 */}
            <div
              className={`p-3 rounded-lg border flex items-start space-x-2.5 ${
                strategyStatus?.condition_4
                  ? 'bg-emerald-950/20 border-emerald-800/40 text-emerald-300'
                  : 'bg-surface/60 border-border text-gray-400'
              }`}
            >
              {strategyStatus?.condition_4 ? (
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
              ) : (
                <XCircle className="w-4 h-4 text-gray-500 shrink-0 mt-0.5" />
              )}
              <div>
                <div className="font-semibold">Condition 4: Trading Session</div>
                <div className="text-[11px] text-gray-400 mt-0.5">
                  Window: 09:20 to 15:15 IST | Candle: {strategyStatus?.time_ist || '--'} IST
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Right Col: Active Position or Quick Actions */}
        <div className="bg-card border border-border rounded-xl p-4 flex flex-col justify-between">
          <div className="flex items-center justify-between mb-2">
            <span className="font-semibold text-sm text-white">Active Paper Position</span>
            {activePos ? (
              <span className="px-2 py-0.5 rounded text-[11px] font-mono font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/40">
                OPEN
              </span>
            ) : (
              <span className="px-2 py-0.5 rounded text-[11px] font-mono bg-gray-800 text-gray-400">
                NO POSITION
              </span>
            )}
          </div>

          {activePos ? (
            <div className="space-y-2 text-xs font-mono">
              <div className="text-sm font-bold text-white">{activePos.symbol}</div>
              <div className="flex justify-between text-gray-400">
                <span>Entry Premium:</span>
                <span className="text-white font-semibold">₹{activePos.entry_price.toFixed(2)}</span>
              </div>
              <div className="flex justify-between text-gray-400">
                <span>Current Premium:</span>
                <span className="text-blue-400 font-semibold">₹{activePos.current_price.toFixed(2)}</span>
              </div>
              <div className="flex justify-between text-gray-400">
                <span>Target (+4 pts):</span>
                <span className="text-emerald-400 font-semibold">₹{activePos.target_price.toFixed(2)}</span>
              </div>
              <div className="flex justify-between text-gray-400">
                <span>Stop Loss:</span>
                <span className="text-rose-400 font-semibold">₹{activePos.stop_price.toFixed(2)}</span>
              </div>
              <div className="flex justify-between text-gray-400 pt-2 border-t border-border">
                <span>Unrealized P&L:</span>
                <span className={`text-base font-bold ${getPnlColor(activePos.net_pnl)}`}>
                  {formatCurrency(activePos.net_pnl)}
                </span>
              </div>

              <button
                disabled
                title="Read-Only Mode: Position square-off is disabled"
                className="w-full mt-3 py-2 px-3 rounded-lg bg-slate-800 border border-slate-700/50 text-slate-500 font-semibold cursor-not-allowed"
              >
                Square Off (Read-Only Mode)
              </button>
            </div>
          ) : (
            <div className="space-y-3 my-auto text-center py-4">
              <p className="text-xs text-gray-400">
                Algorithm is continuously listening for completed 1-minute candle BUY signals.
              </p>
              <button
                disabled
                title="Read-Only Mode: Manual trade execution is disabled"
                className="py-2 px-4 rounded-lg bg-slate-800 border border-slate-700/50 text-slate-500 font-semibold text-xs cursor-not-allowed inline-flex items-center gap-1.5"
              >
                <ArrowUpRight className="w-3.5 h-3.5 text-slate-600" />
                Read-Only Observational Mode
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Row 3: Live Chart */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <span className="font-semibold text-base text-white">Live NIFTY 50 Execution Chart</span>
            <span className="text-xs text-gray-400 font-mono">1-Minute Candles with EMA 9, 21, 50 & VWAP</span>
          </div>
          <button
            onClick={() => onNavigateTab('chart')}
            className="text-xs text-blue-400 hover:text-blue-300 transition-colors font-mono flex items-center gap-1"
          >
            Full Chart View &rarr;
          </button>
        </div>

        <ChartComponent candles={candles} activePosition={activePos} height={460} />
      </div>

      {/* Row 4: Daily Performance Analytics Table */}
      <div className="bg-card border border-border rounded-xl p-5">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center space-x-2">
            <Calendar className="w-4 h-4 text-purple-400" />
            <span className="font-semibold text-sm text-white">Daily Performance Breakdown</span>
            <span className="text-xs text-gray-500 font-mono">(Audited P&amp;L &amp; Charges)</span>
          </div>
          <button
            onClick={() => onNavigateTab('analytics')}
            className="text-xs text-blue-400 hover:text-blue-300 font-mono transition-colors"
          >
            Full Analytics &rarr;
          </button>
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
              {!dailySummary || dailySummary.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-6 text-center text-gray-500 whitespace-normal">
                    No daily trading records logged yet. Virtual trades will aggregate here automatically.
                  </td>
                </tr>
              ) : (
                dailySummary.map((day, idx) => (
                  <tr key={idx} className="hover:bg-surface/40">
                    <td className="px-4 py-2 text-white font-bold">{day?.date || 'Unknown'}</td>
                    <td className="px-4 py-2 text-right text-gray-300">{Number(day?.trades ?? 0)}</td>
                    <td className="px-4 py-2 text-right text-emerald-400">{Number(day?.wins ?? 0)}</td>
                    <td className="px-4 py-2 text-right text-rose-400">{Number(day?.losses ?? 0)}</td>
                    <td className="px-4 py-2 text-right text-emerald-400">
                      ₹{Number(day?.grossProfit ?? 0).toFixed(2)}
                    </td>
                    <td className="px-4 py-2 text-right text-rose-400">
                      ₹{Number(day?.grossLoss ?? 0).toFixed(2)}
                    </td>
                    <td className="px-4 py-2 text-right text-gray-400">
                      ₹{Number(day?.charges ?? 0).toFixed(2)}
                    </td>
                    <td className={`px-4 py-2 text-right font-bold ${getPnlColor(Number(day?.pnl ?? 0))}`}>
                      {formatCurrency(Number(day?.pnl ?? 0))}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
