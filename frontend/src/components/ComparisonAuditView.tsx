import React, { useState, useEffect } from 'react';
import {
  TrendingUp,
  TrendingDown,
  AlertTriangle,
  ShieldCheck,
  Download,
  PlayCircle,
  Database,
  Sliders,
  Scale,
  Zap,
  Activity,
  CheckCircle2,
  XCircle,
  HelpCircle,
  Info
} from 'lucide-react';
import { api } from '../services/api';
import { ComparisonAuditResponse, ComparisonMatrixItem, RootCauseItem } from '../types';
import { formatCurrency, formatIST } from '../utils/formatters';

interface ComparisonAuditViewProps {
  embedded?: boolean;
}

export const ComparisonAuditView: React.FC<ComparisonAuditViewProps> = ({ embedded = false }) => {
  const [loading, setLoading] = useState<boolean>(false);
  const [auditData, setAuditData] = useState<ComparisonAuditResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [selectedRunKey, setSelectedRunKey] = useState<string>('synthetic_trigger');
  const [tradeFilter, setTradeFilter] = useState<'ALL' | 'WINS' | 'LOSSES'>('ALL');

  const [startDate, setStartDate] = useState<string>('2026-11-09');
  const [endDate, setEndDate] = useState<string>('2026-11-13');

  const fetchAudit = async () => {
    setLoading(true);
    setErrorMsg(null);
    try {
      const data = await api.getComparisonAudit({
        start_date: startDate,
        end_date: endDate,
        lots: 5,
        lot_size: 65,
        target_points: 4.0,
        stop_points: 2.0,
        slippage_points: 0.10
      });
      setAuditData(data);
    } catch (err: any) {
      console.error('Failed to load comparison audit', err);
      setErrorMsg(err.message || 'Failed to execute 4-way comparison audit.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAudit();
  }, []);

  const getCsvUrl = () => {
    return api.getComparisonAuditCsvUrl({
      start_date: startDate,
      end_date: endDate,
      lots: 5,
      lot_size: 65,
      target_points: 4.0,
      stop_points: 2.0,
      slippage_points: 0.10
    });
  };

  const getBadgeStyle = (status: string) => {
    if (status === 'SIMULATED_TEST') {
      return 'bg-blue-950/80 text-blue-400 border border-blue-800/80';
    }
    return 'bg-amber-950/80 text-amber-400 border border-amber-800/80';
  };

  const getSeverityStyle = (impact: string) => {
    switch (impact) {
      case 'CRITICAL':
        return 'bg-rose-950/70 text-rose-300 border-rose-800';
      case 'HIGH':
        return 'bg-amber-950/70 text-amber-300 border-amber-800';
      case 'MEDIUM':
        return 'bg-cyan-950/70 text-cyan-300 border-cyan-800';
      default:
        return 'bg-emerald-950/70 text-emerald-300 border-emerald-800';
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Header Card */}
      <div className="bg-card border border-border rounded-xl p-5 shadow-sm">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div className="space-y-1.5">
            <div className="flex items-center gap-2">
              <span className="px-2.5 py-0.5 rounded-full text-[10px] font-mono font-bold bg-purple-950 text-purple-300 border border-purple-800">
                EMPIRICAL 4-WAY AUDIT
              </span>
              <span className="text-gray-400 text-xs font-mono">
                Nov 09 – Nov 13, 2026 (5 Trading Days)
              </span>
            </div>
            <h2 className="text-lg font-bold text-white flex items-center gap-2">
              <Scale className="w-5 h-5 text-purple-400" />
              Synthetic vs Real Historical Backtest Comparison Audit
            </h2>
            <p className="text-xs text-gray-400 max-w-3xl leading-relaxed">
              Audits the identical UT Bot parameters (Key: 1.0, ATR: 10, 5 Lots [325 qty], 2.0 pt SL, 4.0 pt Target, ₹20 flat brokerage)
              on both <span className="text-blue-400 font-semibold">Deterministic Synthetic Data</span> and{' '}
              <span className="text-amber-400 font-semibold">Authentic Kotak Neo Historical Data</span> across{' '}
              <span className="text-gray-200">Trigger-Price</span> and <span className="text-gray-200">Realistic Execution</span> modes.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={fetchAudit}
              disabled={loading}
              className="px-4 py-2 bg-purple-600 hover:bg-purple-500 disabled:bg-purple-800 text-white rounded-lg text-xs font-mono font-bold flex items-center gap-2 shadow-md transition-colors"
            >
              <PlayCircle className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              {loading ? 'Running 4-Way Audit...' : 'Re-Run Audit'}
            </button>
            <a
              href={getCsvUrl()}
              download="synthetic_vs_real_comparison_audit.csv"
              className="px-4 py-2 bg-surface hover:bg-surface/80 border border-border text-gray-200 rounded-lg text-xs font-mono font-bold flex items-center gap-2 transition-colors"
            >
              <Download className="w-4 h-4 text-gray-400" />
              Export Audit CSV
            </a>
          </div>
        </div>

        {/* Audit Parameters Banner */}
        <div className="mt-4 pt-3 border-t border-border grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2 text-[11px] font-mono text-gray-300">
          <div className="bg-surface/50 p-2 rounded border border-border/50">
            <span className="text-gray-500 block text-[10px]">STRATEGY</span>
            <span className="font-bold text-white">UT Bot ATM CE</span>
          </div>
          <div className="bg-surface/50 p-2 rounded border border-border/50">
            <span className="text-gray-500 block text-[10px]">QUANTITY</span>
            <span className="font-bold text-white">325 (5 Lots × 65)</span>
          </div>
          <div className="bg-surface/50 p-2 rounded border border-border/50">
            <span className="text-gray-500 block text-[10px]">STOP LOSS</span>
            <span className="font-bold text-amber-400">2.0 pts (₹650)</span>
          </div>
          <div className="bg-surface/50 p-2 rounded border border-border/50">
            <span className="text-gray-500 block text-[10px]">TARGET</span>
            <span className="font-bold text-emerald-400">4.0 pts (₹1,300)</span>
          </div>
          <div className="bg-surface/50 p-2 rounded border border-border/50">
            <span className="text-gray-500 block text-[10px]">CHARGES</span>
            <span className="font-bold text-white">Flat ₹20 / Trade</span>
          </div>
          <div className="bg-surface/50 p-2 rounded border border-border/50">
            <span className="text-gray-500 block text-[10px]">SLIPPAGE (REALISTIC)</span>
            <span className="font-bold text-cyan-400">0.10 pt / Leg</span>
          </div>
        </div>
      </div>

      {errorMsg && (
        <div className="p-4 rounded-xl bg-rose-950/60 border border-rose-800 text-rose-300 text-xs font-mono flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 flex-shrink-0 text-rose-400 mt-0.5" />
          <div>{errorMsg}</div>
        </div>
      )}

      {/* 4-Way Comparison Matrix Cards */}
      {auditData && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
            {auditData.comparison_matrix.map((item) => {
              const isProfit = item.net_profit >= 0;
              const isReal = item.data_source === 'REAL_MARKET';
              const isRealistic = item.execution_mode === 'REALISTIC';

              return (
                <div
                  key={item.key}
                  onClick={() => setSelectedRunKey(item.key)}
                  className={`bg-card border rounded-xl p-4 flex flex-col justify-between transition-all cursor-pointer relative overflow-hidden ${
                    selectedRunKey === item.key
                      ? 'border-purple-500 ring-2 ring-purple-500/20 shadow-lg'
                      : 'border-border hover:border-gray-600'
                  }`}
                >
                  <div className="space-y-3">
                    {/* Header Badges */}
                    <div className="flex items-center justify-between gap-2">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold ${getBadgeStyle(item.data_quality_status)}`}>
                        {isReal ? 'REAL MARKET' : 'SIMULATED TEST'}
                      </span>
                      <span className="text-[10px] font-mono font-semibold px-2 py-0.5 rounded bg-surface border border-border text-gray-300">
                        {isRealistic ? 'REALISTIC' : 'TRIGGER-PRICE'}
                      </span>
                    </div>

                    <div>
                      <h3 className="text-xs font-bold text-white tracking-wide">{item.label}</h3>
                      <div className="text-[10px] font-mono text-gray-400 mt-0.5">
                        {isReal ? 'Kotak Neo Real FO Data' : 'Deterministic Seed #42'}
                      </div>
                    </div>

                    {/* Net PnL Highlight */}
                    <div className="p-3 rounded-lg bg-surface/70 border border-border/60">
                      <div className="text-[10px] font-mono text-gray-400">NET P&L (AFTER CHARGES)</div>
                      <div className={`text-xl font-bold font-mono ${isProfit ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {formatCurrency(item.net_profit)}
                      </div>
                      <div className="text-[10px] font-mono text-gray-400 mt-1 flex items-center justify-between">
                        <span>Win Rate: <b className="text-white">{item.win_rate}%</b></span>
                        <span>{item.winning_trades}W / {item.losing_trades}L</span>
                      </div>
                    </div>

                    {/* Performance Metrics Table */}
                    <div className="space-y-1.5 text-[11px] font-mono pt-1">
                      <div className="flex justify-between text-gray-400">
                        <span>Total Trades:</span>
                        <span className="font-bold text-white">{item.total_trades}</span>
                      </div>
                      <div className="flex justify-between text-gray-400">
                        <span>Gross Profit:</span>
                        <span className="font-bold text-emerald-400">+{formatCurrency(item.gross_profit)}</span>
                      </div>
                      <div className="flex justify-between text-gray-400">
                        <span>Gross Loss:</span>
                        <span className="font-bold text-rose-400">-{formatCurrency(item.gross_loss)}</span>
                      </div>
                      <div className="flex justify-between text-gray-400">
                        <span>Flat Charges:</span>
                        <span className="font-bold text-amber-400">{formatCurrency(item.total_charges)}</span>
                      </div>
                      <div className="flex justify-between text-gray-400">
                        <span>Slippage Cost:</span>
                        <span className="font-bold text-cyan-400">{formatCurrency(item.total_slippage)}</span>
                      </div>
                      <div className="flex justify-between text-gray-400">
                        <span>Profit Factor:</span>
                        <span className="font-bold text-white">{item.profit_factor}</span>
                      </div>
                      <div className="flex justify-between text-gray-400">
                        <span>Max Drawdown:</span>
                        <span className="font-bold text-rose-400">
                          {formatCurrency(item.max_drawdown)} ({item.max_drawdown_percent}%)
                        </span>
                      </div>
                      <div className="flex justify-between text-gray-400">
                        <span>Avg Hold Time:</span>
                        <span className="font-bold text-gray-200">{item.avg_holding_time_minutes} mins</span>
                      </div>
                    </div>
                  </div>

                  <div className="mt-4 pt-2 border-t border-border/50 text-[10px] font-mono text-center text-purple-400 font-bold">
                    {selectedRunKey === item.key ? '▶ ACTIVE SELECTION (VIEWING TRADES)' : 'Click to inspect trade logs'}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Market Dynamics & Volatility Comparison */}
          <div className="bg-card border border-border rounded-xl p-5 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <Activity className="w-4 h-4 text-cyan-400" />
                Underlying Market Dynamics &amp; Volatility Noise Comparison
              </h3>
              <span className="text-[11px] font-mono text-gray-400">5-Day Aligned Period (09 Nov - 13 Nov)</span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              {/* Metric 1: NIFTY Drift */}
              <div className="bg-surface/60 border border-border/70 rounded-lg p-3.5 space-y-2">
                <div className="text-[10px] font-mono text-gray-400 uppercase tracking-wider">Underlying NIFTY 50 Drift</div>
                <div className="space-y-1 font-mono text-xs">
                  <div className="flex justify-between">
                    <span className="text-blue-400 font-semibold">Synthetic:</span>
                    <span className="font-bold text-emerald-400">
                      +{auditData.market_dynamics.synthetic.nifty_drift} pts (+{auditData.market_dynamics.synthetic.nifty_drift_pct}%)
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-amber-400 font-semibold">Real Market:</span>
                    <span className="font-bold text-gray-300">
                      +{auditData.market_dynamics.real_market.nifty_drift} pts (+{auditData.market_dynamics.real_market.nifty_drift_pct}%)
                    </span>
                  </div>
                </div>
                <div className="text-[10px] text-gray-400 pt-1 border-t border-border/40 leading-tight">
                  Real market was flat chop (+0.27%); Synthetic had a strong +2.83% artificial bull drift (10.2x higher).
                </div>
              </div>

              {/* Metric 2: Option Drift */}
              <div className="bg-surface/60 border border-border/70 rounded-lg p-3.5 space-y-2">
                <div className="text-[10px] font-mono text-gray-400 uppercase tracking-wider">Option Premium Trajectory</div>
                <div className="space-y-1 font-mono text-xs">
                  <div className="flex justify-between">
                    <span className="text-blue-400 font-semibold">Synthetic:</span>
                    <span className="font-bold text-emerald-400">
                      +{auditData.market_dynamics.synthetic.option_drift} pts (+{auditData.market_dynamics.synthetic.option_drift_pct}%)
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-amber-400 font-semibold">Real (25100 CE):</span>
                    <span className="font-bold text-rose-400">
                      {auditData.market_dynamics.real_market.option_drift} pts ({auditData.market_dynamics.real_market.option_drift_pct}%)
                    </span>
                  </div>
                </div>
                <div className="text-[10px] text-gray-400 pt-1 border-t border-border/40 leading-tight">
                  Real CE option suffered -14.3% theta decay in flat market; Synthetic drifted +35.4% up with zero theta decay.
                </div>
              </div>

              {/* Metric 3: 1m Candle Range */}
              <div className="bg-surface/60 border border-border/70 rounded-lg p-3.5 space-y-2">
                <div className="text-[10px] font-mono text-gray-400 uppercase tracking-wider">Average 1-Min Candle Noise</div>
                <div className="space-y-1 font-mono text-xs">
                  <div className="flex justify-between">
                    <span className="text-blue-400 font-semibold">Synthetic:</span>
                    <span className="font-bold text-gray-200">
                      {auditData.market_dynamics.synthetic.avg_1m_candle_range} pts (Max {auditData.market_dynamics.synthetic.max_1m_candle_range})
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-amber-400 font-semibold">Real Market:</span>
                    <span className="font-bold text-amber-300">
                      {auditData.market_dynamics.real_market.avg_1m_candle_range} pts (Max {auditData.market_dynamics.real_market.max_1m_candle_range})
                    </span>
                  </div>
                </div>
                <div className="text-[10px] text-gray-400 pt-1 border-t border-border/40 leading-tight">
                  Real 1-minute candle noise is <b className="text-amber-300">3.18x wider</b> than synthetic noise with spikes to 42.55 pts.
                </div>
              </div>

              {/* Metric 4: SL vs Noise */}
              <div className="bg-surface/60 border border-border/70 rounded-lg p-3.5 space-y-2">
                <div className="text-[10px] font-mono text-gray-400 uppercase tracking-wider">2.0-Point SL vs Noise Ratio</div>
                <div className="space-y-1 font-mono text-xs">
                  <div className="flex justify-between">
                    <span className="text-blue-400 font-semibold">Synthetic:</span>
                    <span className="font-bold text-emerald-400">105% of Noise (Safe)</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-amber-400 font-semibold">Real Market:</span>
                    <span className="font-bold text-rose-400">33% of Noise (Clipped)</span>
                  </div>
                </div>
                <div className="text-[10px] text-gray-400 pt-1 border-t border-border/40 leading-tight">
                  In real market data, 2.0 pt SL is only one-third of a normal 1m bar's range, triggering 90-92 stop-outs.
                </div>
              </div>
            </div>
          </div>

          {/* Root Cause Findings Section */}
          <div className="bg-card border border-border rounded-xl p-5 space-y-4">
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-emerald-400" />
              Root Cause Analysis &amp; Empirical Findings
            </h3>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {auditData.root_causes.map((rc, idx) => (
                <div key={idx} className="bg-surface/60 border border-border/70 rounded-lg p-4 space-y-2">
                  <div className="flex items-center justify-between gap-2">
                    <h4 className="text-xs font-bold text-white">{rc.category}</h4>
                    <span className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold border ${getSeverityStyle(rc.impact)}`}>
                      {rc.impact}
                    </span>
                  </div>
                  <p className="text-xs text-gray-300 leading-relaxed">{rc.finding}</p>
                  <div className="pt-2 border-t border-border/40 text-[11px] font-mono grid grid-cols-1 sm:grid-cols-2 gap-2 text-gray-400">
                    <div>
                      <span className="text-blue-400 font-bold block text-[10px]">SYNTHETIC METRIC:</span>
                      {rc.synthetic_metric}
                    </div>
                    <div>
                      <span className="text-amber-400 font-bold block text-[10px]">REAL MARKET METRIC:</span>
                      {rc.real_metric}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Detailed Trade Log Explorer */}
          {auditData.runs[selectedRunKey] && (
            <div className="bg-card border border-border rounded-xl p-5 space-y-4 shadow-sm">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div>
                  <h3 className="text-sm font-bold text-white flex items-center gap-2">
                    <Database className="w-4 h-4 text-purple-400" />
                    Trade Execution Log — {auditData.runs[selectedRunKey].summary.label}
                  </h3>
                  <div className="text-xs text-gray-400 font-mono mt-0.5">
                    Showing {auditData.runs[selectedRunKey].trades.length} trades | Net P&amp;L:{' '}
                    <span className={`font-bold ${auditData.runs[selectedRunKey].summary.net_profit >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {formatCurrency(auditData.runs[selectedRunKey].summary.net_profit)}
                    </span>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <div className="bg-surface p-1 rounded-lg border border-border flex items-center space-x-1 text-xs font-mono font-bold">
                    <button
                      onClick={() => setTradeFilter('ALL')}
                      className={`px-2.5 py-1 rounded ${tradeFilter === 'ALL' ? 'bg-purple-600 text-white' : 'text-gray-400 hover:text-white'}`}
                    >
                      All ({auditData.runs[selectedRunKey].trades.length})
                    </button>
                    <button
                      onClick={() => setTradeFilter('WINS')}
                      className={`px-2.5 py-1 rounded ${tradeFilter === 'WINS' ? 'bg-emerald-600 text-white' : 'text-gray-400 hover:text-white'}`}
                    >
                      Wins ({auditData.runs[selectedRunKey].summary.winning_trades})
                    </button>
                    <button
                      onClick={() => setTradeFilter('LOSSES')}
                      className={`px-2.5 py-1 rounded ${tradeFilter === 'LOSSES' ? 'bg-rose-600 text-white' : 'text-gray-400 hover:text-white'}`}
                    >
                      Losses ({auditData.runs[selectedRunKey].summary.losing_trades})
                    </button>
                  </div>
                </div>
              </div>

              {/* Trades Table */}
              <div className="overflow-x-auto rounded-lg border border-border">
                <table className="w-full text-left border-collapse text-xs font-mono">
                  <thead>
                    <tr className="bg-surface/80 border-b border-border text-gray-400 text-[10px] uppercase">
                      <th className="py-2.5 px-3">#</th>
                      <th className="py-2.5 px-3">Entry Time (IST)</th>
                      <th className="py-2.5 px-3">Exit Time (IST)</th>
                      <th className="py-2.5 px-3 text-right">Entry Price (₹)</th>
                      <th className="py-2.5 px-3 text-right">Exit Price (₹)</th>
                      <th className="py-2.5 px-3">Exit Reason</th>
                      <th className="py-2.5 px-3 text-right">Gross P&amp;L (₹)</th>
                      <th className="py-2.5 px-3 text-right">Charges (₹)</th>
                      <th className="py-2.5 px-3 text-right">Net P&amp;L (₹)</th>
                      <th className="py-2.5 px-3 text-center">Result</th>
                      <th className="py-2.5 px-3 text-right">Hold</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/50 text-[11px]">
                    {auditData.runs[selectedRunKey].trades
                      .filter((t) => {
                        if (tradeFilter === 'WINS') return t.is_win;
                        if (tradeFilter === 'LOSSES') return !t.is_win;
                        return true;
                      })
                      .slice(0, 100)
                      .map((t) => {
                        return (
                          <tr key={t.id} className="hover:bg-surface/40 transition-colors">
                            <td className="py-2 px-3 text-gray-400">{t.id}</td>
                            <td className="py-2 px-3 text-white">{formatIST(t.entry_time)}</td>
                            <td className="py-2 px-3 text-gray-300">{formatIST(t.exit_time)}</td>
                            <td className="py-2 px-3 text-right font-bold text-gray-200">
                              {Number(t.entry_price).toFixed(2)}
                            </td>
                            <td className="py-2 px-3 text-right font-bold text-gray-200">
                              {Number(t.exit_price).toFixed(2)}
                            </td>
                            <td className="py-2 px-3">
                              <span
                                className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                                  t.exit_reason === 'TARGET'
                                    ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                                    : t.exit_reason === 'AUTO_CLOSE_3_20_PM'
                                    ? 'bg-blue-950 text-blue-400 border border-blue-800'
                                    : 'bg-rose-950 text-rose-400 border border-rose-800'
                                }`}
                              >
                                {t.exit_reason}
                              </span>
                            </td>
                            <td className={`py-2 px-3 text-right font-bold ${t.gross_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                              {formatCurrency(t.gross_pnl)}
                            </td>
                            <td className="py-2 px-3 text-right text-amber-400 font-bold">
                              ₹{Number(t.charges).toFixed(2)}
                            </td>
                            <td className={`py-2 px-3 text-right font-bold ${t.net_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                              {formatCurrency(t.net_pnl)}
                            </td>
                            <td className="py-2 px-3 text-center">
                              {t.is_win ? (
                                <span className="inline-flex items-center text-emerald-400 font-bold gap-1">
                                  <CheckCircle2 className="w-3.5 h-3.5" /> WIN
                                </span>
                              ) : (
                                <span className="inline-flex items-center text-rose-400 font-bold gap-1">
                                  <XCircle className="w-3.5 h-3.5" /> LOSS
                                </span>
                              )}
                            </td>
                            <td className="py-2 px-3 text-right text-gray-400">{t.holding_time_minutes}m</td>
                          </tr>
                        );
                      })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
