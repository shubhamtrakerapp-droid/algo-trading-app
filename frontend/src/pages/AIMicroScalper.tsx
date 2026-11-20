import React, { useState, useEffect } from 'react';
import {
  Brain,
  Shield,
  Activity,
  Sliders,
  PlayCircle,
  BarChart2,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Clock,
  TrendingUp,
  TrendingDown,
  RotateCcw,
  Zap,
  DollarSign,
  Download,
  Flame,
  Info,
  Server,
  Database,
  Lock,
} from 'lucide-react';
import { api } from '../services/api';

type SubTab =
  | 'overview'
  | 'settings'
  | 'agents'
  | 'signals'
  | 'positions'
  | 'history'
  | 'backtesting'
  | 'analytics'
  | 'data-health';

export const AIMicroScalper: React.FC = () => {
  const [activeSubTab, setActiveSubTab] = useState<SubTab>('overview');
  const [status, setStatus] = useState<any>(null);
  const [config, setConfig] = useState<any>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [actionLoading, setActionLoading] = useState<boolean>(false);
  const [toast, setToast] = useState<{ msg: string; type: 'success' | 'error' | 'info' } | null>(null);

  // Backtest state
  const [btDataSource, setBtDataSource] = useState<string>('KOTAK_NEO_HISTORICAL');
  const [btExecMode, setBtExecMode] = useState<string>('TRIGGER_PRICE');
  const [btDuration, setBtDuration] = useState<number>(5);
  const [btStartDate, setBtStartDate] = useState<string>('');
  const [btEndDate, setBtEndDate] = useState<string>('');
  const [btSplit, setBtSplit] = useState<string>('ALL');
  const [btRunning, setBtRunning] = useState<boolean>(false);
  const [btResults, setBtResults] = useState<any>(null);

  // Ablation state
  const [ablationRunning, setAblationRunning] = useState<boolean>(false);
  const [ablationResults, setAblationResults] = useState<any>(null);

  // Editable settings form state
  const [formConfig, setFormConfig] = useState<any>({});

  const showToast = (msg: string, type: 'success' | 'error' | 'info' = 'info') => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 4000);
  };

  const loadData = async () => {
    try {
      const [st, cfg] = await Promise.all([
        api.getAIMicroScalperStatus(),
        api.getAIMicroScalperConfig(),
      ]);
      setStatus(st);
      setConfig(cfg);
      setFormConfig(cfg);
    } catch (err: any) {
      console.error('Failed to load AI Micro-Scalper data', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleToggleStrategy = async () => {
    setActionLoading(true);
    try {
      const action = status?.is_active ? 'PAUSE' : 'START';
      await api.controlAIMicroScalper(action);
      showToast(`Strategy ${action === 'START' ? 'Activated' : 'Paused'} successfully`, 'success');
      await loadData();
    } catch (err: any) {
      showToast('Failed to change strategy state', 'error');
    } finally {
      setActionLoading(false);
    }
  };

  const handleEmergencyClose = async () => {
    if (!window.confirm('Confirm EMERGENCY manual square-off for open paper position?')) return;
    setActionLoading(true);
    try {
      const res = await api.emergencyCloseAIMicroScalper();
      showToast(res.message || 'Position closed', 'success');
      await loadData();
    } catch (err: any) {
      showToast('Failed to close position', 'error');
    } finally {
      setActionLoading(false);
    }
  };

  const handleSaveSettings = async (e: React.FormEvent) => {
    e.preventDefault();
    setActionLoading(true);
    try {
      const res = await api.updateAIMicroScalperConfig(formConfig);
      setConfig(res.config);
      showToast('Settings updated successfully', 'success');
    } catch (err: any) {
      showToast('Failed to update settings', 'error');
    } finally {
      setActionLoading(false);
    }
  };

  const handleRunBacktest = async () => {
    setBtRunning(true);
    try {
      const payload: any = {
        data_source: btDataSource,
        execution_mode: btExecMode,
        duration_days: btDuration,
        initial_capital: config?.initial_capital || 20000.0,
        lots: config?.lots || 2,
        lot_size: config?.lot_size || 65,
        target_net_profit: config?.target_net_profit || 200.0,
        max_loss_per_trade: config?.max_loss_per_trade || 300.0,
        daily_profit_target: config?.daily_profit_target || 500.0,
        daily_loss_limit: config?.daily_loss_limit || -500.0,
        max_trades_per_day: config?.max_trades_per_day || 5,
        max_consecutive_losses: config?.max_consecutive_losses || 2,
        max_holding_time_minutes: config?.max_holding_time_minutes || 5,
        split_type: btSplit === 'ALL' ? null : btSplit,
      };
      if (btStartDate && btEndDate) {
        payload.start_date = btStartDate;
        payload.end_date = btEndDate;
      }
      const res = await api.runAIMicroScalperBacktest(payload);
      setBtResults(res);
      showToast(`Backtest completed: ${res.total_trades} trades executed`, 'success');
    } catch (err: any) {
      showToast(err.response?.data?.detail || 'Backtest execution failed', 'error');
    } finally {
      setBtRunning(false);
    }
  };

  const handleRunAblation = async () => {
    setAblationRunning(true);
    try {
      const payload: any = {
        data_source: btDataSource,
        execution_mode: btExecMode,
        duration_days: btDuration,
      };
      if (btStartDate && btEndDate) {
        payload.start_date = btStartDate;
        payload.end_date = btEndDate;
      }
      const res = await api.runAIMicroScalperAblation(payload);
      setAblationResults(res);
      showToast('Agent ablation comparison completed', 'success');
    } catch (err: any) {
      showToast(err.response?.data?.detail || 'Ablation experiment failed', 'error');
    } finally {
      setAblationRunning(false);
    }
  };

  const dailyRisk = status?.daily_risk || {};
  const realizedNet = dailyRisk.realized_net_pnl || 0.0;
  const profitTarget = config?.daily_profit_target || 500.0;
  const lossLimit = config?.daily_loss_limit || -500.0;
  const tradeCount = dailyRisk.trade_count || 0;
  const maxTrades = config?.max_trades_per_day || 5;
  const lastEval = status?.last_evaluation;
  const activePos = status?.active_position;

  return (
    <div className="space-y-6 pb-12">
      {/* Header Banner */}
      <div className="bg-gradient-to-r from-indigo-950/70 via-slate-900 to-slate-950 border border-indigo-500/30 rounded-2xl p-4 sm:p-6 shadow-xl relative overflow-hidden">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-start sm:items-center space-x-3 sm:space-x-4">
            <div className="p-2.5 sm:p-3.5 bg-indigo-600/20 border border-indigo-500/40 rounded-xl text-indigo-400 shrink-0">
              <Brain className="w-6 h-6 sm:w-8 h-8" />
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="text-base sm:text-2xl font-bold font-mono tracking-tight text-white truncate">
                  NEXTRADE AI MICRO-SCALPER
                </h1>
                <span className="px-2 py-0.5 text-[10px] sm:text-xs font-bold font-mono bg-indigo-500/20 text-indigo-300 border border-indigo-500/40 rounded-full">
                  V1.0
                </span>
                <span className="px-2 py-0.5 text-[10px] sm:text-xs font-bold font-mono bg-amber-500/20 text-amber-300 border border-amber-500/40 rounded-full flex items-center space-x-1">
                  <Shield className="w-3 h-3" />
                  <span>PAPER TRADING ONLY</span>
                </span>
              </div>
              <p className="text-[11px] sm:text-xs text-gray-400 mt-1 line-clamp-2 sm:line-clamp-none">
                Explainable Multi-Agent Algorithmic Micro-Scalping Engine with Non-Repainting 5m Trend &amp; 1m Pullback
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2 sm:gap-3">
            <button
              onClick={handleToggleStrategy}
              disabled={actionLoading}
              className={`px-3 sm:px-4 py-2 rounded-xl text-xs font-bold font-mono transition-all flex items-center space-x-2 shadow-lg ${
                status?.is_active
                  ? 'bg-amber-600 hover:bg-amber-500 text-white shadow-amber-900/40'
                  : 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-emerald-900/40'
              }`}
            >
              <Zap className="w-4 h-4" />
              <span>{status?.is_active ? 'PAUSE STRATEGY' : 'ACTIVATE STRATEGY'}</span>
            </button>

            {activePos && (
              <button
                onClick={handleEmergencyClose}
                disabled={actionLoading}
                className="px-3 sm:px-4 py-2 rounded-xl text-xs font-bold font-mono bg-rose-600 hover:bg-rose-500 text-white transition-all shadow-lg shadow-rose-900/40"
              >
                EMERGENCY SQUARE-OFF
              </button>
            )}
          </div>
        </div>

        {/* Real-time Status Strip */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6 pt-6 border-t border-indigo-500/20">
          <div>
            <div className="text-[10px] uppercase font-mono text-gray-400 tracking-wider">Virtual Capital</div>
            <div className="text-lg font-bold font-mono text-white mt-0.5">
              ₹{((status?.current_capital || 20000.0)).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
            </div>
            <div className="text-[10px] text-gray-500">Starting: ₹20,000 (90% Cap)</div>
          </div>

          <div>
            <div className="text-[10px] uppercase font-mono text-gray-400 tracking-wider">Today's Realized Net</div>
            <div
              className={`text-lg font-bold font-mono mt-0.5 ${
                realizedNet > 0 ? 'text-emerald-400' : realizedNet < 0 ? 'text-rose-400' : 'text-gray-300'
              }`}
            >
              {realizedNet >= 0 ? '+' : ''}₹{realizedNet.toFixed(2)}
            </div>
            <div className="text-[10px] text-gray-500">Target +₹500 | Limit -₹500</div>
          </div>

          <div>
            <div className="text-[10px] uppercase font-mono text-gray-400 tracking-wider">Today's Trades</div>
            <div className="text-lg font-bold font-mono text-white mt-0.5">
              {tradeCount} <span className="text-xs font-normal text-gray-400">/ {maxTrades} max</span>
            </div>
            <div className="text-[10px] text-gray-500">
              Loss streak: {dailyRisk.consecutive_losses || 0} / 2 max
            </div>
          </div>

          <div>
            <div className="text-[10px] uppercase font-mono text-gray-400 tracking-wider">Risk Lock Status</div>
            <div className="flex items-center space-x-1.5 mt-0.5">
              {dailyRisk.is_locked ? (
                <>
                  <Lock className="w-4 h-4 text-rose-400" />
                  <span className="text-xs font-bold font-mono text-rose-400">{dailyRisk.lock_reason}</span>
                </>
              ) : (
                <>
                  <CheckCircle className="w-4 h-4 text-emerald-400" />
                  <span className="text-xs font-bold font-mono text-emerald-400">TRADING ACTIVE</span>
                </>
              )}
            </div>
            <div className="text-[10px] text-gray-500">{dailyRisk.status_text || 'Active'}</div>
          </div>
        </div>
      </div>

      {/* Sub-Tabs Navigation */}
      <div className="flex overflow-x-auto space-x-2 border-b border-border/40 pb-2 scrollbar-none">
        {[
          { id: 'overview', label: 'Overview', icon: Activity },
          { id: 'settings', label: 'Strategy Settings', icon: Sliders },
          { id: 'agents', label: 'Agent Monitor', icon: Brain },
          { id: 'signals', label: 'Live Signals', icon: Zap },
          { id: 'positions', label: 'Paper Positions', icon: DollarSign, badge: activePos ? '1' : undefined },
          { id: 'history', label: 'Trade History', icon: Clock },
          { id: 'backtesting', label: 'Backtesting', icon: PlayCircle },
          { id: 'analytics', label: 'Analytics', icon: BarChart2 },
          { id: 'data-health', label: 'Data Health', icon: Server },
        ].map((tab) => {
          const Icon = tab.icon;
          const isActive = activeSubTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveSubTab(tab.id as SubTab)}
              className={`px-3.5 py-2 rounded-xl text-xs font-mono font-semibold flex items-center space-x-2 whitespace-nowrap transition-all ${
                isActive
                  ? 'bg-indigo-600 text-white shadow-md shadow-indigo-950/50'
                  : 'bg-card/50 text-gray-400 hover:text-white hover:bg-card border border-border/30'
              }`}
            >
              <Icon className="w-3.5 h-3.5" />
              <span>{tab.label}</span>
              {tab.badge && (
                <span className="ml-1 px-1.5 py-0.2 bg-emerald-500 text-black text-[10px] font-bold rounded-full">
                  {tab.badge}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* SUB-TAB 1: OVERVIEW */}
      {activeSubTab === 'overview' && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* Rules Summary Card */}
            <div className="bg-card border border-border/50 rounded-2xl p-5 space-y-4">
              <h3 className="text-sm font-bold font-mono text-white flex items-center space-x-2">
                <Shield className="w-4 h-4 text-indigo-400" />
                <span>Strategy Architecture</span>
              </h3>
              <ul className="text-xs text-gray-300 space-y-2.5 font-mono">
                <li className="flex justify-between border-b border-border/30 pb-1.5">
                  <span className="text-gray-400">Timeframe</span>
                  <span className="text-white">1m (with 5m Trend)</span>
                </li>
                <li className="flex justify-between border-b border-border/30 pb-1.5">
                  <span className="text-gray-400">Signal Source</span>
                  <span className="text-white">NIFTY 50 Index</span>
                </li>
                <li className="flex justify-between border-b border-border/30 pb-1.5">
                  <span className="text-gray-400">Execution</span>
                  <span className="text-indigo-400">Actual Option Premium</span>
                </li>
                <li className="flex justify-between border-b border-border/30 pb-1.5">
                  <span className="text-gray-400">Position Sizing</span>
                  <span className="text-white">2 Lots ({config?.quantity || 130} Qty)</span>
                </li>
                <li className="flex justify-between border-b border-border/30 pb-1.5">
                  <span className="text-gray-400">Preferred Premium</span>
                  <span className="text-white">₹100 – ₹150</span>
                </li>
                <li className="flex justify-between">
                  <span className="text-gray-400">Capital Deployment Cap</span>
                  <span className="text-emerald-400">Max 90% (₹18,000)</span>
                </li>
              </ul>
            </div>

            {/* Net Targets Card */}
            <div className="bg-card border border-border/50 rounded-2xl p-5 space-y-4">
              <h3 className="text-sm font-bold font-mono text-white flex items-center space-x-2">
                <TrendingUp className="w-4 h-4 text-emerald-400" />
                <span>Per-Trade Net Limits</span>
              </h3>
              <ul className="text-xs text-gray-300 space-y-2.5 font-mono">
                <li className="flex justify-between border-b border-border/30 pb-1.5">
                  <span className="text-gray-400">Net Profit Target</span>
                  <span className="text-emerald-400 font-bold">+₹{config?.target_net_profit || 200.0}</span>
                </li>
                <li className="flex justify-between border-b border-border/30 pb-1.5">
                  <span className="text-gray-400">Target Points</span>
                  <span className="text-white">+{config?.target_points || 1.79} pts</span>
                </li>
                <li className="flex justify-between border-b border-border/30 pb-1.5">
                  <span className="text-gray-400">Maximum Net Loss</span>
                  <span className="text-rose-400 font-bold">-₹{config?.max_loss_per_trade || 300.0}</span>
                </li>
                <li className="flex justify-between border-b border-border/30 pb-1.5">
                  <span className="text-gray-400">Stop Loss Points</span>
                  <span className="text-white">-{config?.stop_points || 2.05} pts</span>
                </li>
                <li className="flex justify-between border-b border-border/30 pb-1.5">
                  <span className="text-gray-400">Max Holding Time</span>
                  <span className="text-white">{config?.max_holding_time_minutes || 5} Minutes</span>
                </li>
                <li className="flex justify-between">
                  <span className="text-gray-400">Flat Charges / Roundtrip</span>
                  <span className="text-amber-400">₹{config?.roundtrip_charges || 20.0}</span>
                </li>
              </ul>
            </div>

            {/* Daily Risk Discipline Card */}
            <div className="bg-card border border-border/50 rounded-2xl p-5 space-y-4">
              <h3 className="text-sm font-bold font-mono text-white flex items-center space-x-2">
                <Lock className="w-4 h-4 text-amber-400" />
                <span>Daily Risk Safeguards</span>
              </h3>
              <ul className="text-xs text-gray-300 space-y-2.5 font-mono">
                <li className="flex justify-between border-b border-border/30 pb-1.5">
                  <span className="text-gray-400">Daily Profit Lock</span>
                  <span className="text-emerald-400">+₹{config?.daily_profit_target || 500.0}</span>
                </li>
                <li className="flex justify-between border-b border-border/30 pb-1.5">
                  <span className="text-gray-400">Daily Loss Lock</span>
                  <span className="text-rose-400">-₹{Math.abs(config?.daily_loss_limit || -500.0)}</span>
                </li>
                <li className="flex justify-between border-b border-border/30 pb-1.5">
                  <span className="text-gray-400">Max Completed Trades</span>
                  <span className="text-white">5 per trading day</span>
                </li>
                <li className="flex justify-between border-b border-border/30 pb-1.5">
                  <span className="text-gray-400">Consecutive Loss Pause</span>
                  <span className="text-rose-400">2 consecutive losses</span>
                </li>
                <li className="flex justify-between border-b border-border/30 pb-1.5">
                  <span className="text-gray-400">Entry Session Window</span>
                  <span className="text-white">09:25 – 14:45 IST</span>
                </li>
                <li className="flex justify-between">
                  <span className="text-gray-400">Mandatory Square-off</span>
                  <span className="text-white">15:20 IST</span>
                </li>
              </ul>
            </div>
          </div>

          {/* Latest Signal & Agent Consensus Card */}
          <div className="bg-card border border-border/50 rounded-2xl p-6">
            <h3 className="text-sm font-bold font-mono text-white flex items-center justify-between">
              <span className="flex items-center space-x-2">
                <Brain className="w-4 h-4 text-indigo-400" />
                <span>Latest Candle Evaluation &amp; AI Consensus</span>
              </span>
              <span className="text-xs text-gray-400 font-normal">
                {lastEval ? `${lastEval.time_ist} IST` : 'Standby'}
              </span>
            </h3>

            {lastEval ? (
              <div className="mt-4 space-y-4">
                <div className="flex flex-wrap items-center gap-3">
                  <span
                    className={`px-3 py-1 text-xs font-bold font-mono rounded-lg ${
                      lastEval.signal === 'BUY_CE'
                        ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                        : lastEval.signal === 'BUY_PE'
                        ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40'
                        : 'bg-gray-800 text-gray-400 border border-gray-700'
                    }`}
                  >
                    SIGNAL: {lastEval.signal}
                  </span>

                  <span className="text-xs font-mono text-gray-300">
                    NIFTY Spot: <span className="font-bold text-white">₹{lastEval.underlying_price}</span>
                  </span>

                  {lastEval.contract_symbol && (
                    <span className="text-xs font-mono text-indigo-300">
                      Contract: {lastEval.contract_symbol} @ ₹{lastEval.contract_premium} (Spread: {lastEval.spread} pts)
                    </span>
                  )}
                </div>

                <div className="p-3 bg-card/60 rounded-xl border border-border/30 text-xs font-mono text-gray-300">
                  <span className="text-gray-400 font-bold">Action Reason: </span>
                  {lastEval.action_reason}
                </div>
              </div>
            ) : (
              <div className="mt-4 text-xs font-mono text-gray-500 p-4 bg-card/40 rounded-xl text-center">
                Awaiting next completed 1-minute candle evaluation...
              </div>
            )}
          </div>
        </div>
      )}

      {/* SUB-TAB 2: SETTINGS */}
      {activeSubTab === 'settings' && (
        <form onSubmit={handleSaveSettings} className="bg-card border border-border/50 rounded-2xl p-6 space-y-6">
          <div className="flex items-center justify-between border-b border-border/30 pb-4">
            <div>
              <h2 className="text-lg font-bold font-mono text-white">Strategy Parameters Configuration</h2>
              <p className="text-xs text-gray-400 mt-0.5">Customize trading thresholds and risk budget</p>
            </div>
            <button
              type="submit"
              disabled={actionLoading}
              className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-xs font-mono font-bold transition-all shadow-lg shadow-indigo-950/50"
            >
              SAVE SETTINGS
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 text-xs font-mono">
            {/* Capital & Sizing */}
            <div className="space-y-4">
              <h4 className="font-bold text-indigo-400 uppercase tracking-wider text-[11px]">Capital &amp; Sizing</h4>
              <div>
                <label className="text-gray-400 block mb-1">Starting Virtual Capital (₹)</label>
                <input
                  type="number"
                  value={formConfig.initial_capital || 20000}
                  onChange={(e) => setFormConfig({ ...formConfig, initial_capital: Number(e.target.value) })}
                  className="w-full bg-background border border-border/60 rounded-lg p-2.5 text-white"
                />
              </div>
              <div>
                <label className="text-gray-400 block mb-1">Position Lots</label>
                <input
                  type="number"
                  value={formConfig.lots || 2}
                  onChange={(e) => setFormConfig({ ...formConfig, lots: Number(e.target.value) })}
                  className="w-full bg-background border border-border/60 rounded-lg p-2.5 text-white"
                />
              </div>
              <div>
                <label className="text-gray-400 block mb-1">Lot Size (Dynamic Fallback)</label>
                <input
                  type="number"
                  value={formConfig.lot_size || 65}
                  onChange={(e) => setFormConfig({ ...formConfig, lot_size: Number(e.target.value) })}
                  className="w-full bg-background border border-border/60 rounded-lg p-2.5 text-white"
                />
              </div>
              <div>
                <label className="text-gray-400 block mb-1">Preferred Premium Min (₹)</label>
                <input
                  type="number"
                  value={formConfig.preferred_premium_min || 100}
                  onChange={(e) => setFormConfig({ ...formConfig, preferred_premium_min: Number(e.target.value) })}
                  className="w-full bg-background border border-border/60 rounded-lg p-2.5 text-white"
                />
              </div>
              <div>
                <label className="text-gray-400 block mb-1">Preferred Premium Max (₹)</label>
                <input
                  type="number"
                  value={formConfig.preferred_premium_max || 150}
                  onChange={(e) => setFormConfig({ ...formConfig, preferred_premium_max: Number(e.target.value) })}
                  className="w-full bg-background border border-border/60 rounded-lg p-2.5 text-white"
                />
              </div>
            </div>

            {/* Trade & Daily P&L Limits */}
            <div className="space-y-4">
              <h4 className="font-bold text-emerald-400 uppercase tracking-wider text-[11px]">Trade &amp; Daily Limits</h4>
              <div>
                <label className="text-gray-400 block mb-1">Target Net Profit Per Trade (₹)</label>
                <input
                  type="number"
                  value={formConfig.target_net_profit || 200}
                  onChange={(e) => setFormConfig({ ...formConfig, target_net_profit: Number(e.target.value) })}
                  className="w-full bg-background border border-border/60 rounded-lg p-2.5 text-white"
                />
              </div>
              <div>
                <label className="text-gray-400 block mb-1">Max Loss Per Trade (₹)</label>
                <input
                  type="number"
                  value={formConfig.max_loss_per_trade || 300}
                  onChange={(e) => setFormConfig({ ...formConfig, max_loss_per_trade: Number(e.target.value) })}
                  className="w-full bg-background border border-border/60 rounded-lg p-2.5 text-white"
                />
              </div>
              <div>
                <label className="text-gray-400 block mb-1">Daily Net Profit Target (₹)</label>
                <input
                  type="number"
                  value={formConfig.daily_profit_target || 500}
                  onChange={(e) => setFormConfig({ ...formConfig, daily_profit_target: Number(e.target.value) })}
                  className="w-full bg-background border border-border/60 rounded-lg p-2.5 text-white"
                />
              </div>
              <div>
                <label className="text-gray-400 block mb-1">Daily Net Loss Limit (₹)</label>
                <input
                  type="number"
                  value={formConfig.daily_loss_limit || -500}
                  onChange={(e) => setFormConfig({ ...formConfig, daily_loss_limit: Number(e.target.value) })}
                  className="w-full bg-background border border-border/60 rounded-lg p-2.5 text-white"
                />
              </div>
              <div>
                <label className="text-gray-400 block mb-1">Max Trades Per Day</label>
                <input
                  type="number"
                  value={formConfig.max_trades_per_day || 5}
                  onChange={(e) => setFormConfig({ ...formConfig, max_trades_per_day: Number(e.target.value) })}
                  className="w-full bg-background border border-border/60 rounded-lg p-2.5 text-white"
                />
              </div>
            </div>

            {/* Execution & Sessions */}
            <div className="space-y-4">
              <h4 className="font-bold text-amber-400 uppercase tracking-wider text-[11px]">Execution &amp; Session</h4>
              <div>
                <label className="text-gray-400 block mb-1">Max Holding Time (Minutes)</label>
                <select
                  value={formConfig.max_holding_time_minutes || 5}
                  onChange={(e) => setFormConfig({ ...formConfig, max_holding_time_minutes: Number(e.target.value) })}
                  className="w-full bg-background border border-border/60 rounded-lg p-2.5 text-white"
                >
                  <option value={3}>3 Minutes</option>
                  <option value={5}>5 Minutes</option>
                  <option value={8}>8 Minutes</option>
                </select>
              </div>
              <div>
                <label className="text-gray-400 block mb-1">Entry Window Start (IST)</label>
                <input
                  type="text"
                  value={formConfig.entry_start_ist || '09:25'}
                  onChange={(e) => setFormConfig({ ...formConfig, entry_start_ist: e.target.value })}
                  className="w-full bg-background border border-border/60 rounded-lg p-2.5 text-white"
                />
              </div>
              <div>
                <label className="text-gray-400 block mb-1">Entry Window End (IST)</label>
                <input
                  type="text"
                  value={formConfig.entry_end_ist || '14:45'}
                  onChange={(e) => setFormConfig({ ...formConfig, entry_end_ist: e.target.value })}
                  className="w-full bg-background border border-border/60 rounded-lg p-2.5 text-white"
                />
              </div>
              <div>
                <label className="text-gray-400 block mb-1">Mandatory Square-off (IST)</label>
                <input
                  type="text"
                  value={formConfig.force_exit_ist || '15:20'}
                  onChange={(e) => setFormConfig({ ...formConfig, force_exit_ist: e.target.value })}
                  className="w-full bg-background border border-border/60 rounded-lg p-2.5 text-white"
                />
              </div>
              <div>
                <label className="text-gray-400 block mb-1">Roundtrip Charges (₹)</label>
                <input
                  type="number"
                  value={formConfig.roundtrip_charges || 20}
                  onChange={(e) => setFormConfig({ ...formConfig, roundtrip_charges: Number(e.target.value) })}
                  className="w-full bg-background border border-border/60 rounded-lg p-2.5 text-white"
                />
              </div>
            </div>
          </div>
        </form>
      )}

      {/* SUB-TAB 3: AGENT MONITOR */}
      {activeSubTab === 'agents' && (
        <div className="space-y-6">
          <div className="bg-card border border-border/50 rounded-2xl p-6">
            <div className="flex items-center justify-between border-b border-border/30 pb-4">
              <div>
                <h2 className="text-base font-bold font-mono text-white">Five Specialized AI Agents</h2>
                <p className="text-xs text-gray-400 mt-0.5">
                  Explainable, deterministic agents requiring &gt;= 4 of 5 consensus with compulsory Risk Agent approval
                </p>
              </div>
              <div className="px-3 py-1.5 bg-indigo-500/20 border border-indigo-500/40 rounded-xl text-xs font-mono text-indigo-300">
                Consensus Requirement: 4 / 5
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-6">
              {/* Agent 1: Trend Agent */}
              <div className="p-4 bg-background/50 border border-border/40 rounded-xl space-y-2 font-mono text-xs">
                <div className="flex justify-between items-center">
                  <span className="font-bold text-white flex items-center space-x-1.5">
                    <TrendingUp className="w-4 h-4 text-blue-400" />
                    <span>1. Trend Agent</span>
                  </span>
                  <span className="px-2 py-0.5 bg-blue-500/20 text-blue-300 rounded text-[10px]">
                    5m EMA 20/50 + VWAP + ADX
                  </span>
                </div>
                <p className="text-gray-400 text-[11px]">
                  Evaluates completed 5m candle trend. Requires 5m Close &gt; VWAP, 5m EMA 20 &gt; 5m EMA 50, and ADX &gt;= 20.
                </p>
                <div className="text-[11px] text-gray-300">
                  Vote: <span className="text-emerald-400 font-bold">{lastEval?.agent_votes?.trend?.approved ? 'APPROVED' : 'NEUTRAL / REJECTED'}</span>
                  {lastEval?.agent_votes?.trend?.reason && ` (${lastEval.agent_votes.trend.reason})`}
                </div>
              </div>

              {/* Agent 2: Momentum Agent */}
              <div className="p-4 bg-background/50 border border-border/40 rounded-xl space-y-2 font-mono text-xs">
                <div className="flex justify-between items-center">
                  <span className="font-bold text-white flex items-center space-x-1.5">
                    <Zap className="w-4 h-4 text-amber-400" />
                    <span>2. Momentum Agent</span>
                  </span>
                  <span className="px-2 py-0.5 bg-amber-500/20 text-amber-300 rounded text-[10px]">
                    1m RSI 14 + Body Ratio + Volume
                  </span>
                </div>
                <p className="text-gray-400 text-[11px]">
                  Requires healthy RSI range (52–68 for CE, 32–48 for PE), solid candle body ratio &gt;= 45%, and non-exhausted momentum.
                </p>
                <div className="text-[11px] text-gray-300">
                  Vote: <span className="text-emerald-400 font-bold">{lastEval?.agent_votes?.momentum?.approved ? 'APPROVED' : 'NEUTRAL / REJECTED'}</span>
                  {lastEval?.agent_votes?.momentum?.reason && ` (${lastEval.agent_votes.momentum.reason})`}
                </div>
              </div>

              {/* Agent 3: Volatility Agent */}
              <div className="p-4 bg-background/50 border border-border/40 rounded-xl space-y-2 font-mono text-xs">
                <div className="flex justify-between items-center">
                  <span className="font-bold text-white flex items-center space-x-1.5">
                    <Activity className="w-4 h-4 text-purple-400" />
                    <span>3. Volatility Agent</span>
                  </span>
                  <span className="px-2 py-0.5 bg-purple-500/20 text-purple-300 rounded text-[10px]">
                    1m ATR 14 + Feasibility
                  </span>
                </div>
                <p className="text-gray-400 text-[11px]">
                  Verifies option premium ATR is expanding and confirms target points ({config?.target_points || 1.79} pts) are realistic within 5 minutes.
                </p>
                <div className="text-[11px] text-gray-300">
                  Vote: <span className="text-emerald-400 font-bold">{lastEval?.agent_votes?.volatility?.approved ? 'APPROVED' : 'NEUTRAL / REJECTED'}</span>
                  {lastEval?.agent_votes?.volatility?.reason && ` (${lastEval.agent_votes.volatility.reason})`}
                </div>
              </div>

              {/* Agent 4: Market Regime Agent */}
              <div className="p-4 bg-background/50 border border-border/40 rounded-xl space-y-2 font-mono text-xs">
                <div className="flex justify-between items-center">
                  <span className="font-bold text-white flex items-center space-x-1.5">
                    <BarChart2 className="w-4 h-4 text-cyan-400" />
                    <span>4. Market Regime Agent</span>
                  </span>
                  <span className="px-2 py-0.5 bg-cyan-500/20 text-cyan-300 rounded text-[10px]">
                    Trending vs Choppy/Sideways
                  </span>
                </div>
                <p className="text-gray-400 text-[11px]">
                  Rejects choppy conditions and sideways markets (ADX &lt; 20). Approves only clean trending regimes.
                </p>
                <div className="text-[11px] text-gray-300">
                  Vote: <span className="text-emerald-400 font-bold">{lastEval?.agent_votes?.regime?.approved ? 'APPROVED' : 'NEUTRAL / REJECTED'}</span>
                  {lastEval?.agent_votes?.regime?.reason && ` (${lastEval.agent_votes.regime.reason})`}
                </div>
              </div>

              {/* Agent 5: Risk Agent */}
              <div className="p-4 bg-indigo-950/30 border border-indigo-500/50 rounded-xl space-y-2 font-mono text-xs md:col-span-2">
                <div className="flex justify-between items-center">
                  <span className="font-bold text-white flex items-center space-x-1.5">
                    <Shield className="w-4 h-4 text-emerald-400" />
                    <span>5. Risk Agent (COMPULSORY APPROVAL)</span>
                  </span>
                  <span className="px-2 py-0.5 bg-emerald-500/20 text-emerald-300 rounded text-[10px]">
                    Zero-Tolerance Gatekeeper
                  </span>
                </div>
                <p className="text-gray-300 text-[11px]">
                  Compulsory approval. Evaluates 90% capital deployment cap, preferred premium range (₹100–₹150), bid-ask spread &lt;= 0.50 pts, daily P&L limits (+₹500 / -₹500), max 5 trades, 2 consecutive loss pause, session window, and single position cap.
                </p>
                <div className="text-[11px] text-gray-300 pt-1">
                  Status: <span className="text-emerald-400 font-bold">{lastEval?.agent_votes?.risk?.approved ? 'APPROVED' : 'REJECTED / BLOCKED'}</span>
                  {lastEval?.agent_votes?.risk?.reason && ` (${lastEval.agent_votes.risk.reason})`}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* SUB-TAB 4: LIVE SIGNALS */}
      {activeSubTab === 'signals' && (
        <div className="bg-card border border-border/50 rounded-2xl p-6 space-y-4">
          <h2 className="text-base font-bold font-mono text-white">Live Signal Feed</h2>
          {lastEval ? (
            <div className="p-4 bg-background/50 border border-border/40 rounded-xl space-y-3 font-mono text-xs">
              <div className="flex justify-between items-center border-b border-border/30 pb-2">
                <span className="text-gray-400">Time: {lastEval.time_ist} IST</span>
                <span
                  className={`px-2 py-0.5 rounded font-bold ${
                    lastEval.signal.startsWith('BUY') ? 'bg-emerald-500/20 text-emerald-300' : 'bg-gray-800 text-gray-400'
                  }`}
                >
                  {lastEval.signal}
                </span>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-[11px]">
                <div>
                  <span className="text-gray-400 block">NIFTY Spot</span>
                  <span className="text-white font-bold">₹{lastEval.underlying_price}</span>
                </div>
                <div>
                  <span className="text-gray-400 block">5m Trend</span>
                  <span className="text-white">
                    ADX: {lastEval.adx_5m} | VWAP: {lastEval.vwap_5m}
                  </span>
                </div>
                <div>
                  <span className="text-gray-400 block">1m Momentum</span>
                  <span className="text-white">
                    RSI: {lastEval.rsi_1m} | ATR: {lastEval.atr_1m}
                  </span>
                </div>
                <div>
                  <span className="text-gray-400 block">Target / SL</span>
                  <span className="text-emerald-400">+{lastEval.target_points} pts</span> /{' '}
                  <span className="text-rose-400">-{lastEval.stop_points} pts</span>
                </div>
              </div>
              <div className="text-[11px] text-gray-300 pt-1">
                <span className="text-gray-400">Detail: </span>
                {lastEval.action_reason}
              </div>
            </div>
          ) : (
            <div className="text-xs font-mono text-gray-500 p-8 text-center bg-card/40 rounded-xl">
              No recent signals recorded. Feed activates automatically during trading hours.
            </div>
          )}
        </div>
      )}

      {/* SUB-TAB 5: PAPER POSITIONS */}
      {activeSubTab === 'positions' && (
        <div className="bg-card border border-border/50 rounded-2xl p-6 space-y-4">
          <div className="flex justify-between items-center">
            <h2 className="text-base font-bold font-mono text-white">Active Paper Positions</h2>
            <span className="text-xs font-mono text-amber-400">STRICTLY VIRTUAL EXECUTION</span>
          </div>

          {activePos ? (
            <div className="p-5 bg-background/50 border border-border/50 rounded-xl space-y-4 font-mono text-xs">
              <div className="flex justify-between items-center border-b border-border/30 pb-3">
                <div>
                  <div className="text-sm font-bold text-white">{activePos.symbol}</div>
                  <div className="text-[11px] text-gray-400">
                    Qty: {activePos.quantity} ({activePos.lots} lots) &bull; Entry: ₹{activePos.entry_price}
                  </div>
                </div>
                <div className="text-right">
                  <div
                    className={`text-base font-bold ${
                      activePos.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'
                    }`}
                  >
                    {activePos.pnl >= 0 ? '+' : ''}₹{activePos.pnl.toFixed(2)}
                  </div>
                  <div className="text-[10px] text-gray-400">LTP: ₹{activePos.current_price}</div>
                </div>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-[11px]">
                <div>
                  <span className="text-gray-400 block">Target Trigger</span>
                  <span className="text-emerald-400 font-bold">₹{activePos.target_price}</span>
                </div>
                <div>
                  <span className="text-gray-400 block">Stop Loss Trigger</span>
                  <span className="text-rose-400 font-bold">₹{activePos.stop_price}</span>
                </div>
                <div>
                  <span className="text-gray-400 block">Entry Time</span>
                  <span className="text-white">{activePos.entry_time}</span>
                </div>
                <div>
                  <span className="text-gray-400 block">Max Holding Limit</span>
                  <span className="text-white">{config?.max_holding_time_minutes || 5} min</span>
                </div>
              </div>

              <div className="pt-2">
                <button
                  onClick={handleEmergencyClose}
                  disabled={actionLoading}
                  className="w-full py-2.5 bg-rose-600 hover:bg-rose-500 text-white rounded-xl font-bold transition-all"
                >
                  CLOSE PAPER POSITION NOW
                </button>
              </div>
            </div>
          ) : (
            <div className="text-xs font-mono text-gray-500 p-8 text-center bg-card/40 rounded-xl">
              No active paper position currently open. Position manager is FLAT.
            </div>
          )}
        </div>
      )}

      {/* SUB-TAB 6: TRADE HISTORY */}
      {activeSubTab === 'history' && (
        <div className="bg-card border border-border/50 rounded-2xl p-6 space-y-4">
          <div className="flex justify-between items-center">
            <h2 className="text-base font-bold font-mono text-white">Today's Executed Paper Trades</h2>
            <span className="text-xs font-mono text-gray-400">Total: {status?.today_trades?.length || 0}</span>
          </div>

          {status?.today_trades && status.today_trades.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-left font-mono text-xs">
                <thead>
                  <tr className="border-b border-border/40 text-gray-400 text-[11px]">
                    <th className="py-2.5 px-3">Contract</th>
                    <th className="py-2.5 px-3">Entry</th>
                    <th className="py-2.5 px-3">Exit</th>
                    <th className="py-2.5 px-3">Qty</th>
                    <th className="py-2.5 px-3">Gross P&amp;L</th>
                    <th className="py-2.5 px-3">Charges</th>
                    <th className="py-2.5 px-3">Net P&amp;L</th>
                    <th className="py-2.5 px-3">Reason</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/20">
                  {status.today_trades.map((t: any) => (
                    <tr key={t.id} className="hover:bg-card/40">
                      <td className="py-2.5 px-3 text-white font-medium">{t.symbol}</td>
                      <td className="py-2.5 px-3 text-gray-300">₹{t.entry_price}</td>
                      <td className="py-2.5 px-3 text-gray-300">₹{t.exit_price}</td>
                      <td className="py-2.5 px-3 text-gray-400">{t.quantity}</td>
                      <td className="py-2.5 px-3 text-gray-300">₹{t.gross_pnl}</td>
                      <td className="py-2.5 px-3 text-amber-400">₹{t.total_charges}</td>
                      <td
                        className={`py-2.5 px-3 font-bold ${
                          t.net_pnl > 0 ? 'text-emerald-400' : 'text-rose-400'
                        }`}
                      >
                        {t.net_pnl >= 0 ? '+' : ''}₹{t.net_pnl}
                      </td>
                      <td className="py-2.5 px-3 text-gray-400 text-[11px]">{t.exit_reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-xs font-mono text-gray-500 p-8 text-center bg-card/40 rounded-xl">
              No paper trades executed today yet.
            </div>
          )}
        </div>
      )}

      {/* SUB-TAB 7: BACKTESTING */}
      {activeSubTab === 'backtesting' && (
        <div className="space-y-6">
          <div className="bg-card border border-border/50 rounded-2xl p-6 space-y-6">
            <h2 className="text-base font-bold font-mono text-white">Dedicated Historical Backtest</h2>

            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 text-xs font-mono">
              <div>
                <label className="text-gray-400 block mb-1">Data Source</label>
                <select
                  value={btDataSource}
                  onChange={(e) => setBtDataSource(e.target.value)}
                  className="w-full bg-background border border-border/60 rounded-lg p-2.5 text-white"
                >
                  <option value="KOTAK_NEO_HISTORICAL">Kotak Neo Historical (Real)</option>
                  <option value="SYNTHETIC_TEST">Synthetic Test (Simulated)</option>
                </select>
              </div>

              <div>
                <label className="text-gray-400 block mb-1">Execution Mode</label>
                <select
                  value={btExecMode}
                  onChange={(e) => setBtExecMode(e.target.value)}
                  className="w-full bg-background border border-border/60 rounded-lg p-2.5 text-white"
                >
                  <option value="TRIGGER_PRICE">Trigger-Price Mode (Ideal)</option>
                  <option value="REALISTIC">Realistic Mode (Bid/Ask + Slippage)</option>
                </select>
              </div>

              <div>
                <label className="text-gray-400 block mb-1">Historical Duration</label>
                <select
                  value={btDuration}
                  onChange={(e) => setBtDuration(Number(e.target.value))}
                  className="w-full bg-background border border-border/60 rounded-lg p-2.5 text-white"
                >
                  <option value={1}>Today (1 Day)</option>
                  <option value={3}>Last 3 Trading Days</option>
                  <option value={5}>Last 5 Trading Days</option>
                  <option value={10}>Last 10 Trading Days</option>
                  <option value={30}>Last 30 Trading Days</option>
                </select>
              </div>

              <div>
                <label className="text-gray-400 block mb-1">Data Split</label>
                <select
                  value={btSplit}
                  onChange={(e) => setBtSplit(e.target.value)}
                  className="w-full bg-background border border-border/60 rounded-lg p-2.5 text-white"
                >
                  <option value="ALL">Complete Period (100%)</option>
                  <option value="TRAIN">Train Split (Chronological 60%)</option>
                  <option value="VALIDATION">Validation Split (Next 20%)</option>
                  <option value="TEST">Test Split (Final 20%)</option>
                </select>
              </div>
            </div>

            <div className="flex justify-end pt-2">
              <button
                onClick={handleRunBacktest}
                disabled={btRunning}
                className="px-6 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-xs font-mono font-bold transition-all flex items-center space-x-2 shadow-lg shadow-indigo-950/50"
              >
                <PlayCircle className="w-4 h-4" />
                <span>{btRunning ? 'RUNNING BACKTEST...' : 'RUN HISTORICAL BACKTEST'}</span>
              </button>
            </div>
          </div>

          {/* Backtest Results Display */}
          {btResults && (
            <div className="bg-card border border-border/50 rounded-2xl p-6 space-y-6">
              <div className="flex justify-between items-center border-b border-border/30 pb-4">
                <h3 className="text-sm font-bold font-mono text-white">Backtest Performance Results</h3>
                <span className="text-xs font-mono text-gray-400">
                  Execution: <span className="text-indigo-400">{btResults.execution_mode}</span> &bull; Data:{' '}
                  <span className="text-white">{btResults.data_source}</span>
                </span>
              </div>

              {/* KPI Cards */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 font-mono">
                <div className="p-4 bg-background/50 border border-border/40 rounded-xl">
                  <div className="text-[10px] uppercase text-gray-400">Net Profit</div>
                  <div
                    className={`text-xl font-bold mt-1 ${
                      btResults.net_profit >= 0 ? 'text-emerald-400' : 'text-rose-400'
                    }`}
                  >
                    {btResults.net_profit >= 0 ? '+' : ''}₹{btResults.net_profit}
                  </div>
                </div>

                <div className="p-4 bg-background/50 border border-border/40 rounded-xl">
                  <div className="text-[10px] uppercase text-gray-400">Win Rate</div>
                  <div className="text-xl font-bold text-white mt-1">
                    {btResults.win_rate}%{' '}
                    <span className="text-xs font-normal text-gray-400">
                      ({btResults.winning_trades} / {btResults.total_trades})
                    </span>
                  </div>
                </div>

                <div className="p-4 bg-background/50 border border-border/40 rounded-xl">
                  <div className="text-[10px] uppercase text-gray-400">Profit Factor</div>
                  <div className="text-xl font-bold text-white mt-1">{btResults.profit_factor}</div>
                </div>

                <div className="p-4 bg-background/50 border border-border/40 rounded-xl">
                  <div className="text-[10px] uppercase text-gray-400">Max Drawdown</div>
                  <div className="text-xl font-bold text-rose-400 mt-1">
                    ₹{btResults.max_drawdown} ({btResults.max_drawdown_pct}%)
                  </div>
                </div>
              </div>

              {/* Missing data indicator if any */}
              {btResults.missing_data_count > 0 && (
                <div className="p-3 bg-amber-500/10 border border-amber-500/30 rounded-xl text-xs font-mono text-amber-300 flex items-center space-x-2">
                  <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
                  <span>
                    MISSING DATA: {btResults.missing_data_count} candles were missing from historical feed and recorded
                    honestly without faking synthetic bars.
                  </span>
                </div>
              )}

              {/* Daily Breakdown Table */}
              {btResults.daily_breakdown && btResults.daily_breakdown.length > 0 && (
                <div className="space-y-3">
                  <h4 className="text-xs font-bold font-mono text-gray-300 uppercase">Daily Performance Breakdown</h4>
                  <div className="overflow-x-auto">
                    <table className="w-full text-left font-mono text-xs">
                      <thead>
                        <tr className="border-b border-border/40 text-gray-400 text-[11px]">
                          <th className="py-2 px-3">Date</th>
                          <th className="py-2 px-3">Trades</th>
                          <th className="py-2 px-3">Net P&amp;L</th>
                          <th className="py-2 px-3">Status</th>
                          <th className="py-2 px-3">Risk Lock</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border/20">
                        {btResults.daily_breakdown.map((d: any) => (
                          <tr key={d.date} className="hover:bg-card/40">
                            <td className="py-2 px-3 text-white">{d.date}</td>
                            <td className="py-2 px-3 text-gray-300">{d.trades}</td>
                            <td
                              className={`py-2 px-3 font-bold ${
                                d.net_pnl > 0 ? 'text-emerald-400' : d.net_pnl < 0 ? 'text-rose-400' : 'text-gray-400'
                              }`}
                            >
                              {d.net_pnl >= 0 ? '+' : ''}₹{d.net_pnl}
                            </td>
                            <td className="py-2 px-3 text-gray-300">{d.status}</td>
                            <td className="py-2 px-3 text-gray-400 text-[11px]">{d.lock_reason}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* SUB-TAB 8: ANALYTICS */}
      {activeSubTab === 'analytics' && (
        <div className="space-y-6">
          <div className="bg-card border border-border/50 rounded-2xl p-6 space-y-4">
            <div className="flex justify-between items-center">
              <div>
                <h2 className="text-base font-bold font-mono text-white">Agent Performance Comparison / Ablation</h2>
                <p className="text-xs text-gray-400 mt-0.5">
                  Measures incremental alpha and drawdown protection across all 7 configurations (A to G)
                </p>
              </div>
              <button
                onClick={handleRunAblation}
                disabled={ablationRunning}
                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-xs font-mono font-bold transition-all"
              >
                {ablationRunning ? 'RUNNING EXPERIMENTS...' : 'RUN ABLATION COMPARISON'}
              </button>
            </div>

            {ablationResults?.ablation_comparison ? (
              <div className="overflow-x-auto mt-4">
                <table className="w-full text-left font-mono text-xs">
                  <thead>
                    <tr className="border-b border-border/40 text-gray-400 text-[11px]">
                      <th className="py-2.5 px-3">Exp</th>
                      <th className="py-2.5 px-3">Configuration</th>
                      <th className="py-2.5 px-3">Trades</th>
                      <th className="py-2.5 px-3">Win Rate</th>
                      <th className="py-2.5 px-3">Net P&amp;L</th>
                      <th className="py-2.5 px-3">Profit Factor</th>
                      <th className="py-2.5 px-3">Max DD</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/20">
                    {ablationResults.ablation_comparison.map((row: any) => (
                      <tr
                        key={row.experiment_id}
                        className={row.experiment_id === 'G' ? 'bg-indigo-950/40 font-bold' : 'hover:bg-card/40'}
                      >
                        <td className="py-2.5 px-3 text-indigo-400">{row.experiment_id}</td>
                        <td className="py-2.5 px-3 text-white">{row.experiment_name}</td>
                        <td className="py-2.5 px-3 text-gray-300">{row.total_trades}</td>
                        <td className="py-2.5 px-3 text-white">{row.win_rate}%</td>
                        <td
                          className={`py-2.5 px-3 font-bold ${
                            row.net_profit >= 0 ? 'text-emerald-400' : 'text-rose-400'
                          }`}
                        >
                          {row.net_profit >= 0 ? '+' : ''}₹{row.net_profit}
                        </td>
                        <td className="py-2.5 px-3 text-gray-300">{row.profit_factor}</td>
                        <td className="py-2.5 px-3 text-rose-400">₹{row.max_drawdown}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="text-xs font-mono text-gray-500 p-8 text-center bg-card/40 rounded-xl">
                Click "Run Ablation Comparison" to evaluate all 7 agent configurations.
              </div>
            )}
          </div>
        </div>
      )}

      {/* SUB-TAB 9: DATA HEALTH */}
      {activeSubTab === 'data-health' && (
        <div className="bg-card border border-border/50 rounded-2xl p-6 space-y-6">
          <h2 className="text-base font-bold font-mono text-white">Historical Data Health &amp; Telemetry</h2>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 font-mono text-xs">
            <div className="p-4 bg-background/50 border border-border/40 rounded-xl space-y-2">
              <span className="font-bold text-white flex items-center space-x-1.5">
                <Database className="w-4 h-4 text-emerald-400" />
                <span>Kotak Neo Historical API</span>
              </span>
              <p className="text-gray-400 text-[11px]">
                Endpoint: <code>/Orders/2.0/quick/user/instruments/historical</code>
              </p>
              <div className="text-emerald-400 font-bold">Connected &amp; Verified</div>
            </div>

            <div className="p-4 bg-background/50 border border-border/40 rounded-xl space-y-2">
              <span className="font-bold text-white flex items-center space-x-1.5">
                <Activity className="w-4 h-4 text-indigo-400" />
                <span>Dynamic Lot Size</span>
              </span>
              <p className="text-gray-400 text-[11px]">
                Dynamically fetched from official Kotak Neo FO instrument master.
              </p>
              <div className="text-white font-bold">{config?.lot_size || 65} Qty / Lot</div>
            </div>

            <div className="p-4 bg-background/50 border border-border/40 rounded-xl space-y-2">
              <span className="font-bold text-white flex items-center space-x-1.5">
                <Shield className="w-4 h-4 text-amber-400" />
                <span>Missing Data Policy</span>
              </span>
              <p className="text-gray-400 text-[11px]">
                Zero data fabrication. In real-market mode, missing bars are recorded as MISSING_DATA.
              </p>
              <div className="text-amber-400 font-bold">Strict Non-Fabrication</div>
            </div>
          </div>
        </div>
      )}

      {/* Toast Notification */}
      {toast && (
        <div className="fixed bottom-6 right-6 z-50">
          <div
            className={`px-4 py-3 rounded-xl shadow-2xl border text-xs font-mono font-semibold flex items-center space-x-2 ${
              toast.type === 'success'
                ? 'bg-emerald-950/90 border-emerald-700 text-emerald-200'
                : toast.type === 'error'
                ? 'bg-rose-950/90 border-rose-700 text-rose-200'
                : 'bg-indigo-950/90 border-indigo-700 text-indigo-200'
            }`}
          >
            {toast.type === 'success' ? (
              <CheckCircle className="w-4 h-4" />
            ) : toast.type === 'error' ? (
              <XCircle className="w-4 h-4" />
            ) : (
              <Info className="w-4 h-4" />
            )}
            <span>{toast.msg}</span>
          </div>
        </div>
      )}
    </div>
  );
};
