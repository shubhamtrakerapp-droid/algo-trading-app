import React, { useEffect, useState } from 'react';
import {
  Sliders,
  CheckCircle2,
  XCircle,
  ShieldCheck,
  Zap,
  Activity,
  ArrowUpRight,
  TrendingDown,
  TrendingUp,
  Layers,
  Save,
  Check,
  Lock,
  Unlock,
  Clock,
  Target,
  ShieldAlert,
  AlertCircle,
} from 'lucide-react';
import { StrategyStatus, StrategyProfile, StrategyType, UTBotConfig, SupertrendEMAConfig } from '../types';
import { api } from '../services/api';

interface StrategyProps {
  strategyStatus: StrategyStatus | null;
}

export const Strategy: React.FC<StrategyProps> = ({ strategyStatus }) => {
  const [profiles, setProfiles] = useState<StrategyProfile[]>([]);
  const [selectedStrategyId, setSelectedStrategyId] = useState<StrategyType>('UT_BOT');
  const [activeTab, setActiveTab] = useState<StrategyType>('UT_BOT');
  const [signals, setSignals] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  // UT Bot Form State
  const [utConfig, setUtConfig] = useState<UTBotConfig>({
    key_value: 1.0,
    atr_period: 10,
    use_heikin_ashi: false,
    lots: 5,
    lot_size: 65,
    target_points: 4.0,
    stop_points: 2.0,
    max_loss_per_trade: 1000.0,
    signal_source: 'CHART_INSTRUMENT',
    exit_on_ut_sell_signal: false,
    execution_mode: 'TRIGGER_PRICE',
  });
  const [useRiskCap, setUseRiskCap] = useState(true);

  // EMA Strategy Form State
  const [emaLots, setEmaLots] = useState(1);
  const [emaLotSize, setEmaLotSize] = useState(65);
  const [emaTarget, setEmaTarget] = useState(4.0);
  const [emaStop, setEmaStop] = useState(2.0);

  // Supertrend EMA Scalper Form State
  const [stConfig, setStConfig] = useState<SupertrendEMAConfig>({
    atr_period: 10,
    multiplier: 3.0,
    ema_fast: 9,
    ema_slow: 21,
    lots: 5,
    lot_size: 65,
    target_net_profit: 200.0,
    max_loss_per_trade: 1000.0,
    daily_profit_target: 1000.0,
    daily_loss_limit: -2000.0,
    roundtrip_charges: 20.0,
  });
  const [stLiveStatus, setStLiveStatus] = useState<any>(null);
  const [closingPosition, setClosingPosition] = useState(false);

  useEffect(() => {
    loadProfiles();
    loadSignals();
  }, []);

  useEffect(() => {
    const fetchStStatus = async () => {
      try {
        const data = await api.getStrategyStatus('SUPERTREND_EMA');
        setStLiveStatus(data);
      } catch (err) {
        // silent
      }
    };
    fetchStStatus();
    const interval = setInterval(fetchStStatus, 2500);
    return () => clearInterval(interval);
  }, []);

  const loadProfiles = async () => {
    try {
      const data = await api.getStrategyProfiles();
      setProfiles(data.profiles);
      setSelectedStrategyId(data.selected_strategy);
      setActiveTab(data.selected_strategy);

      // Populate config fields
      const utProfile = data.profiles.find((p) => p.id === 'UT_BOT');
      if (utProfile && utProfile.config) {
        setUtConfig({
          key_value: utProfile.config.key_value ?? 1.0,
          atr_period: utProfile.config.atr_period ?? 10,
          use_heikin_ashi: utProfile.config.use_heikin_ashi ?? false,
          lots: utProfile.config.lots ?? 5,
          lot_size: utProfile.config.lot_size ?? 65,
          target_points: utProfile.config.target_points ?? 4.0,
          stop_points: utProfile.config.stop_points ?? 2.0,
          max_loss_per_trade: utProfile.config.max_loss_per_trade ?? 1000.0,
          signal_source: utProfile.config.signal_source ?? 'CHART_INSTRUMENT',
          exit_on_ut_sell_signal: utProfile.config.exit_on_ut_sell_signal ?? false,
          execution_mode: utProfile.config.execution_mode ?? 'TRIGGER_PRICE',
        });
        setUseRiskCap(utProfile.config.max_loss_per_trade !== null);
      }

      const stProfile = data.profiles.find((p: any) => p.id === 'SUPERTREND_EMA' || p.strategy_id === 'SUPERTREND_EMA');
      if (stProfile && stProfile.config) {
        setStConfig({
          atr_period: stProfile.config.atr_period ?? 10,
          multiplier: stProfile.config.multiplier ?? 3.0,
          ema_fast: stProfile.config.ema_fast ?? 9,
          ema_slow: stProfile.config.ema_slow ?? 21,
          lots: stProfile.config.lots ?? 5,
          lot_size: stProfile.config.lot_size ?? 65,
          target_net_profit: stProfile.config.target_net_profit ?? 200.0,
          max_loss_per_trade: stProfile.config.max_loss_per_trade ?? 1000.0,
          daily_profit_target: stProfile.config.daily_profit_target ?? 1000.0,
          daily_loss_limit: stProfile.config.daily_loss_limit ?? -2000.0,
          roundtrip_charges: stProfile.config.roundtrip_charges ?? 20.0,
        });
      }

      const emaProfile = data.profiles.find((p) => p.id === 'EMA_RSI');
      if (emaProfile && emaProfile.config) {
        setEmaLots(emaProfile.config.lots ?? 1);
        setEmaLotSize(emaProfile.config.lot_size ?? 65);
        setEmaTarget(emaProfile.config.target_points ?? 4.0);
        setEmaStop(emaProfile.config.stop_points ?? 2.0);
      }
    } catch (e) {
      console.error('Failed to load strategy profiles:', e);
    }
  };

  const loadSignals = async () => {
    setLoading(true);
    try {
      const data = await api.getSignals(50);
      setSignals(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const handleSelectStrategy = async (strategyId: StrategyType) => {
    try {
      setSaving(true);
      await api.selectStrategy(strategyId);
      setSelectedStrategyId(strategyId);
      await loadProfiles();
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 2500);
    } catch (e: any) {
      alert(`Error activating strategy: ${e.message}`);
    } finally {
      setSaving(false);
    }
  };

  const handleSaveUTConfig = async () => {
    try {
      setSaving(true);
      const payload = {
        ...utConfig,
        max_loss_per_trade: useRiskCap ? 1000.0 : null,
      };
      await api.configureStrategy('UT_BOT', payload);
      await api.selectStrategy('UT_BOT');
      setSelectedStrategyId('UT_BOT');
      await loadProfiles();
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 2500);
    } catch (e: any) {
      alert(`Error saving UT Bot configuration: ${e.message}`);
    } finally {
      setSaving(false);
    }
  };

  const handleSaveEMAConfig = async () => {
    try {
      setSaving(true);
      const payload = {
        lots: emaLots,
        lot_size: emaLotSize,
        target_points: emaTarget,
        stop_points: emaStop,
      };
      await api.configureStrategy('EMA_RSI', payload);
      await api.selectStrategy('EMA_RSI');
      setSelectedStrategyId('EMA_RSI');
      await loadProfiles();
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 2500);
    } catch (e: any) {
      alert(`Error saving EMA configuration: ${e.message}`);
    } finally {
      setSaving(false);
    }
  };

  const handleSaveSupertrendConfig = async () => {
    try {
      setSaving(true);
      await api.configureStrategy('SUPERTREND_EMA', stConfig);
      await api.selectStrategy('SUPERTREND_EMA');
      setSelectedStrategyId('SUPERTREND_EMA');
      await loadProfiles();
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 2500);
    } catch (e: any) {
      alert(`Error saving Supertrend EMA configuration: ${e.message}`);
    } finally {
      setSaving(false);
    }
  };

  const handleManualClose = async () => {
    if (!confirm('Are you sure you want to square off the current paper position?')) return;
    try {
      setClosingPosition(true);
      await api.closePosition();
      const data = await api.getStrategyStatus('SUPERTREND_EMA');
      setStLiveStatus(data);
    } catch (err: any) {
      alert(`Error squaring off position: ${err.message}`);
    } finally {
      setClosingPosition(false);
    }
  };

  // Calculations for live preview
  const utTradeQty = utConfig.lots * utConfig.lot_size;
  const utBaselineRisk = utConfig.stop_points * utTradeQty;
  const utCappedStopPoints = useRiskCap ? Math.min(utConfig.stop_points, 1000.0 / Math.max(1, utTradeQty)) : utConfig.stop_points;
  const utMaxLossActual = Math.min(utBaselineRisk, useRiskCap ? 1000.0 : utBaselineRisk);

  // Supertrend EMA Calculations for live preview
  const stTradeQty = stConfig.lots * stConfig.lot_size;
  const stTargetPts = ((stConfig.target_net_profit + 20.0) / Math.max(1, stTradeQty)).toFixed(2);
  const stStopPts = ((stConfig.max_loss_per_trade - 20.0) / Math.max(1, stTradeQty)).toFixed(2);

  // Active Telemetry
  const utProfile = profiles.find((p) => p.id === 'UT_BOT');
  const utTelem = utProfile?.live_telemetry;

  return (
    <div className="space-y-6">
      {/* Top Navigation Tabs & Active Indicator */}
      <div className="bg-card border border-border rounded-xl p-4 flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => setActiveTab('SUPERTREND_EMA')}
            className={`px-4 py-2 rounded-xl text-xs font-mono font-bold transition-all flex items-center gap-2 ${
              activeTab === 'SUPERTREND_EMA'
                ? 'bg-emerald-600 text-white shadow-lg shadow-emerald-500/20'
                : 'bg-surface text-gray-400 hover:text-white border border-border'
            }`}
          >
            <TrendingUp className="w-4 h-4 text-emerald-400" />
            Supertrend EMA Scalper
            {selectedStrategyId === 'SUPERTREND_EMA' && (
              <span className="px-1.5 py-0.5 rounded text-[10px] bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
                ACTIVE
              </span>
            )}
          </button>

          <button
            onClick={() => setActiveTab('UT_BOT')}
            className={`px-4 py-2 rounded-xl text-xs font-mono font-bold transition-all flex items-center gap-2 ${
              activeTab === 'UT_BOT'
                ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/20'
                : 'bg-surface text-gray-400 hover:text-white border border-border'
            }`}
          >
            <Zap className="w-4 h-4 text-amber-400" />
            UT Bot ATM Option Strategy
            {selectedStrategyId === 'UT_BOT' && (
              <span className="px-1.5 py-0.5 rounded text-[10px] bg-emerald-500/20 text-emerald-400 border border-emerald-500/40">
                ACTIVE
              </span>
            )}
          </button>

          <button
            onClick={() => setActiveTab('EMA_RSI')}
            className={`px-4 py-2 rounded-xl text-xs font-mono font-bold transition-all flex items-center gap-2 ${
              activeTab === 'EMA_RSI'
                ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/20'
                : 'bg-surface text-gray-400 hover:text-white border border-border'
            }`}
          >
            <Layers className="w-4 h-4 text-purple-400" />
            NIFTY EMA / RSI Strategy
            {selectedStrategyId === 'EMA_RSI' && (
              <span className="px-1.5 py-0.5 rounded text-[10px] bg-emerald-500/20 text-emerald-400 border border-emerald-500/40">
                ACTIVE
              </span>
            )}
          </button>
        </div>

        <div className="flex items-center space-x-3 text-xs font-mono">
          <span className="text-gray-400">Trading Engine:</span>
          <span className="font-bold text-white uppercase bg-surface px-3 py-1 rounded-lg border border-border">
            {selectedStrategyId === 'SUPERTREND_EMA'
              ? 'SUPERTREND EMA (5 LOTS)'
              : selectedStrategyId === 'UT_BOT'
              ? 'UT BOT (5 LOTS)'
              : 'EMA 9/21/50 + RSI'}
          </span>
          {saveSuccess && (
            <span className="text-emerald-400 flex items-center gap-1 font-semibold animate-pulse">
              <Check className="w-3.5 h-3.5" /> Saved &amp; Activated!
            </span>
          )}
        </div>
      </div>

      {/* SUPERTREND EMA SCALPER VIEW */}
      {activeTab === 'SUPERTREND_EMA' && (
        <div className="space-y-6">
          {/* Header Card */}
          <div className="bg-card border border-border rounded-xl p-5">
            <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
              <div className="flex items-center space-x-3">
                <div className="p-2.5 rounded-xl bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                  <TrendingUp className="w-5 h-5" />
                </div>
                <div>
                  <h2 className="text-lg font-bold text-white">SUPERTREND EMA SCALPER — 1-Minute Strategy</h2>
                  <p className="text-xs text-gray-400 font-mono">
                    Underlying Signal: NIFTY 50 Spot | Execution: ATM CE &amp; ATM PE Options | Timeframe: 1m
                  </p>
                </div>
              </div>

              <div className="flex items-center space-x-2">
                <button
                  onClick={() => handleSelectStrategy('SUPERTREND_EMA')}
                  disabled={selectedStrategyId === 'SUPERTREND_EMA'}
                  className={`px-3 py-1.5 rounded-lg text-xs font-mono font-bold transition-all flex items-center gap-1.5 ${
                    selectedStrategyId === 'SUPERTREND_EMA'
                      ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 cursor-default'
                      : 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-md'
                  }`}
                >
                  <ShieldCheck className="w-4 h-4" />
                  {selectedStrategyId === 'SUPERTREND_EMA' ? 'LIVE FOR PAPER TRADING' : 'ACTIVATE FOR PAPER TRADING'}
                </button>
              </div>
            </div>

            {/* Live Indicator Telemetry Strip (Dashboard) */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mt-4 pt-4 border-t border-border/60 text-xs font-mono">
              <div className="bg-surface/50 p-2.5 rounded-lg border border-border/60">
                <div className="text-gray-500 text-[10px]">SUPERTREND (10, 3.0)</div>
                <div className="text-white font-bold text-sm mt-0.5">
                  {stLiveStatus?.supertrend ? `₹${stLiveStatus.supertrend.toFixed(2)}` : 'Evaluating...'}
                </div>
              </div>

              <div className="bg-surface/50 p-2.5 rounded-lg border border-border/60">
                <div className="text-gray-500 text-[10px]">CURRENT TREND</div>
                <div
                  className={`font-bold text-sm mt-0.5 flex items-center gap-1 ${
                    stLiveStatus?.trend === 'BULLISH' ? 'text-emerald-400' : stLiveStatus?.trend === 'BEARISH' ? 'text-red-400' : 'text-gray-400'
                  }`}
                >
                  {stLiveStatus?.trend === 'BULLISH' ? (
                    <><ArrowUpRight className="w-4 h-4" /> BULLISH</>
                  ) : stLiveStatus?.trend === 'BEARISH' ? (
                    <><TrendingDown className="w-4 h-4" /> BEARISH</>
                  ) : (
                    'NEUTRAL'
                  )}
                </div>
              </div>

              <div className="bg-surface/50 p-2.5 rounded-lg border border-border/60">
                <div className="text-gray-500 text-[10px]">FAST EMA (9)</div>
                <div className="text-blue-400 font-bold text-sm mt-0.5">
                  {stLiveStatus?.ema_9 ? `₹${stLiveStatus.ema_9.toFixed(2)}` : '--'}
                </div>
              </div>

              <div className="bg-surface/50 p-2.5 rounded-lg border border-border/60">
                <div className="text-gray-500 text-[10px]">SLOW EMA (21)</div>
                <div className="text-purple-400 font-bold text-sm mt-0.5">
                  {stLiveStatus?.ema_21 ? `₹${stLiveStatus.ema_21.toFixed(2)}` : '--'}
                </div>
              </div>

              <div className="bg-surface/50 p-2.5 rounded-lg border border-border/60">
                <div className="text-gray-500 text-[10px]">LATEST SIGNAL</div>
                <div
                  className={`font-bold text-xs mt-0.5 ${
                    stLiveStatus?.signal === 'BUY_CE'
                      ? 'text-emerald-400'
                      : stLiveStatus?.signal === 'BUY_PE'
                      ? 'text-red-400'
                      : 'text-gray-400'
                  }`}
                >
                  {stLiveStatus?.signal || 'NONE'}
                </div>
              </div>

              <div className="bg-surface/50 p-2.5 rounded-lg border border-border/60">
                <div className="text-gray-500 text-[10px]">EXECUTION CONTRACT</div>
                <div className="text-white font-bold text-xs mt-0.5 truncate">
                  {stLiveStatus?.contract_symbol || 'NIFTY ATM CE'}
                </div>
              </div>
            </div>
          </div>

          {/* Daily Risk Management & Persistent Lock Dashboard */}
          <div className="bg-card border border-border rounded-xl p-5 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h3 className="font-bold text-white text-sm flex items-center gap-2 font-mono">
                <ShieldAlert className="w-4 h-4 text-amber-400" />
                Daily Risk Management &amp; Persistent Lock
              </h3>
              <div className="flex items-center space-x-2 font-mono text-xs">
                <span className="text-gray-400">Lock Status:</span>
                <span
                  className={`px-2.5 py-1 rounded font-bold flex items-center gap-1 ${
                    stLiveStatus?.daily_risk?.is_locked
                      ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40'
                      : 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                  }`}
                >
                  {stLiveStatus?.daily_risk?.is_locked ? (
                    <><Lock className="w-3.5 h-3.5" /> {stLiveStatus.daily_risk.lock_reason}</>
                  ) : (
                    <><Unlock className="w-3.5 h-3.5" /> ACTIVE (ENTRIES PERMITTED)</>
                  )}
                </span>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 text-xs font-mono">
              <div className="bg-surface/50 p-3 rounded-lg border border-border">
                <div className="text-gray-400 text-[11px] mb-1">Today's Realized Net P&amp;L</div>
                <div
                  className={`text-lg font-bold ${
                    (stLiveStatus?.daily_risk?.realized_net_pnl ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'
                  }`}
                >
                  {(stLiveStatus?.daily_risk?.realized_net_pnl ?? 0) >= 0 ? '+' : ''}₹
                  {(stLiveStatus?.daily_risk?.realized_net_pnl ?? 0).toFixed(2)}
                </div>
                <div className="text-[10px] text-gray-500 mt-1">
                  Across {stLiveStatus?.daily_risk?.trade_count || 0} trades ({stLiveStatus?.daily_risk?.winning_trades || 0}W / {stLiveStatus?.daily_risk?.losing_trades || 0}L)
                </div>
              </div>

              <div className="bg-surface/50 p-3 rounded-lg border border-border">
                <div className="flex items-center justify-between text-gray-400 text-[11px] mb-1">
                  <span>Daily Profit Target (+₹{stConfig.daily_profit_target})</span>
                  <span className="text-emerald-400 font-bold">
                    {stLiveStatus?.daily_risk?.profit_target_progress_pct ?? 0}%
                  </span>
                </div>
                <div className="w-full bg-border rounded-full h-2 mt-2 overflow-hidden">
                  <div
                    className="bg-emerald-500 h-2 rounded-full transition-all duration-500"
                    style={{ width: `${Math.min(100, Math.max(0, stLiveStatus?.daily_risk?.profit_target_progress_pct ?? 0))}%` }}
                  />
                </div>
                <div className="text-[10px] text-gray-500 mt-2">
                  When reached, new entries are locked for the remainder of the session.
                </div>
              </div>

              <div className="bg-surface/50 p-3 rounded-lg border border-border">
                <div className="flex items-center justify-between text-gray-400 text-[11px] mb-1">
                  <span>Daily Loss Limit (-₹{Math.abs(stConfig.daily_loss_limit)})</span>
                  <span className="text-rose-400 font-bold">
                    {stLiveStatus?.daily_risk?.loss_limit_progress_pct ?? 0}%
                  </span>
                </div>
                <div className="w-full bg-border rounded-full h-2 mt-2 overflow-hidden">
                  <div
                    className="bg-rose-500 h-2 rounded-full transition-all duration-500"
                    style={{ width: `${Math.min(100, Math.max(0, stLiveStatus?.daily_risk?.loss_limit_progress_pct ?? 0))}%` }}
                  />
                </div>
                <div className="text-[10px] text-gray-500 mt-2">
                  When reached, new entries are locked for the remainder of the session.
                </div>
              </div>

              <div className="bg-surface/50 p-3 rounded-lg border border-border flex flex-col justify-between">
                <div>
                  <div className="text-gray-400 text-[11px] mb-1">Lock Reset Schedule</div>
                  <div className="text-white font-bold text-xs">Next Trading Session Open</div>
                </div>
                <div className="text-[10px] text-gray-400 mt-1">
                  Limits never reset on page refresh or restart. Stored persistently in database.
                </div>
              </div>
            </div>
          </div>

          {/* Active Open Position Card (If open) */}
          {stLiveStatus?.active_position && (
            <div className="bg-card border-2 border-blue-500/50 rounded-xl p-5 space-y-3 font-mono text-xs shadow-md">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 pb-3">
                <div className="flex items-center space-x-2">
                  <span className="px-2 py-0.5 rounded bg-blue-500/20 text-blue-300 font-bold">OPEN POSITION</span>
                  <span className="text-white font-bold text-sm">{stLiveStatus.active_position.symbol}</span>
                  <span className="text-gray-400">({stLiveStatus.active_position.quantity} Qty = {stLiveStatus.active_position.lots} lots)</span>
                </div>
                <button
                  onClick={handleManualClose}
                  disabled={closingPosition}
                  className="px-3 py-1 rounded bg-rose-600 hover:bg-rose-500 text-white font-bold transition-all disabled:opacity-50"
                >
                  {closingPosition ? 'Squaring Off...' : 'Emergency Square Off'}
                </button>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 pt-1">
                <div>
                  <span className="text-gray-500 block">Entry Price:</span>
                  <span className="text-white font-bold">₹{stLiveStatus.active_position.entry_price?.toFixed(2)}</span>
                </div>
                <div>
                  <span className="text-gray-500 block">Current LTP:</span>
                  <span className="text-white font-bold">₹{stLiveStatus.active_position.current_price?.toFixed(2)}</span>
                </div>
                <div>
                  <span className="text-gray-500 block">Target Trigger:</span>
                  <span className="text-emerald-400 font-bold">₹{stLiveStatus.active_position.target_price?.toFixed(2)}</span>
                </div>
                <div>
                  <span className="text-gray-500 block">SL Trigger:</span>
                  <span className="text-red-400 font-bold">₹{stLiveStatus.active_position.stop_price?.toFixed(2)}</span>
                </div>
                <div>
                  <span className="text-gray-500 block">Charges:</span>
                  <span className="text-gray-400 font-bold">₹{stLiveStatus.active_position.charges?.toFixed(2) || '20.00'}</span>
                </div>
                <div>
                  <span className="text-gray-500 block">Unrealized Net P&amp;L:</span>
                  <span
                    className={`font-bold text-sm ${
                      (stLiveStatus.active_position.net_pnl || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'
                    }`}
                  >
                    {(stLiveStatus.active_position.net_pnl || 0) >= 0 ? '+' : ''}₹{stLiveStatus.active_position.net_pnl?.toFixed(2)}
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* Strategy Configuration Form */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 bg-card border border-border rounded-xl p-5 space-y-4">
              <h3 className="font-bold text-white text-sm flex items-center gap-2 font-mono">
                <Sliders className="w-4 h-4 text-emerald-400" />
                Supertrend EMA Parameters &amp; Dynamic Net Risk Model
              </h3>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs font-mono">
                <div>
                  <label className="text-gray-400 block mb-1">Supertrend ATR Period:</label>
                  <input
                    type="number"
                    min="1"
                    value={stConfig.atr_period}
                    onChange={(e) => setStConfig({ ...stConfig, atr_period: parseInt(e.target.value) || 10 })}
                    className="w-full bg-surface border border-border rounded-lg px-3 py-2 text-white font-bold focus:outline-none focus:border-emerald-500"
                  />
                  <span className="text-[10px] text-gray-500">ATR lookback period for volatility trailing band (default 10).</span>
                </div>

                <div>
                  <label className="text-gray-400 block mb-1">Supertrend Multiplier:</label>
                  <input
                    type="number"
                    step="0.1"
                    min="0.5"
                    value={stConfig.multiplier}
                    onChange={(e) => setStConfig({ ...stConfig, multiplier: parseFloat(e.target.value) || 3.0 })}
                    className="w-full bg-surface border border-border rounded-lg px-3 py-2 text-white font-bold focus:outline-none focus:border-emerald-500"
                  />
                  <span className="text-[10px] text-gray-500">Factor multiplied by ATR to calculate upper/lower bands (default 3.0).</span>
                </div>

                <div>
                  <label className="text-gray-400 block mb-1">Fast EMA Period (Default 9):</label>
                  <input
                    type="number"
                    min="1"
                    value={stConfig.ema_fast}
                    onChange={(e) => setStConfig({ ...stConfig, ema_fast: parseInt(e.target.value) || 9 })}
                    className="w-full bg-surface border border-border rounded-lg px-3 py-2 text-white font-bold focus:outline-none focus:border-emerald-500"
                  />
                  <span className="text-[10px] text-gray-500">Fast exponential moving average for trend confirmation.</span>
                </div>

                <div>
                  <label className="text-gray-400 block mb-1">Slow EMA Period (Default 21):</label>
                  <input
                    type="number"
                    min="2"
                    value={stConfig.ema_slow}
                    onChange={(e) => setStConfig({ ...stConfig, ema_slow: parseInt(e.target.value) || 21 })}
                    className="w-full bg-surface border border-border rounded-lg px-3 py-2 text-white font-bold focus:outline-none focus:border-emerald-500"
                  />
                  <span className="text-[10px] text-gray-500">Slow exponential moving average for baseline alignment.</span>
                </div>

                <div>
                  <label className="text-gray-400 block mb-1">Lots (Default 5):</label>
                  <input
                    type="number"
                    min="1"
                    value={stConfig.lots}
                    onChange={(e) => setStConfig({ ...stConfig, lots: parseInt(e.target.value) || 5 })}
                    className="w-full bg-surface border border-border rounded-lg px-3 py-2 text-white font-bold focus:outline-none focus:border-emerald-500"
                  />
                  <span className="text-[10px] text-gray-500">Total contracts = {stConfig.lots * stConfig.lot_size} quantity.</span>
                </div>

                <div>
                  <label className="text-gray-400 block mb-1">Contract Lot Size:</label>
                  <input
                    type="number"
                    min="1"
                    value={stConfig.lot_size}
                    onChange={(e) => setStConfig({ ...stConfig, lot_size: parseInt(e.target.value) || 65 })}
                    className="w-full bg-surface border border-border rounded-lg px-3 py-2 text-white font-bold focus:outline-none focus:border-emerald-500"
                  />
                  <span className="text-[10px] text-gray-500">Standard NIFTY option lot size (default 65).</span>
                </div>

                <div>
                  <label className="text-gray-400 block mb-1">Target Net Profit Per Trade (₹):</label>
                  <input
                    type="number"
                    step="50"
                    value={stConfig.target_net_profit}
                    onChange={(e) => setStConfig({ ...stConfig, target_net_profit: parseFloat(e.target.value) || 200.0 })}
                    className="w-full bg-surface border border-border rounded-lg px-3 py-2 text-emerald-400 font-bold focus:outline-none focus:border-emerald-500"
                  />
                  <span className="text-[10px] text-gray-500">Target net profit after roundtrip charges (default ₹200).</span>
                </div>

                <div>
                  <label className="text-gray-400 block mb-1">Max Loss Budget Per Trade (₹):</label>
                  <input
                    type="number"
                    step="100"
                    value={stConfig.max_loss_per_trade}
                    onChange={(e) => setStConfig({ ...stConfig, max_loss_per_trade: parseFloat(e.target.value) || 1000.0 })}
                    className="w-full bg-surface border border-border rounded-lg px-3 py-2 text-red-400 font-bold focus:outline-none focus:border-emerald-500"
                  />
                  <span className="text-[10px] text-gray-500">Hard net loss cap budget per trade (default ₹1,000).</span>
                </div>

                <div>
                  <label className="text-gray-400 block mb-1">Daily NET Profit Target (₹):</label>
                  <input
                    type="number"
                    step="100"
                    value={stConfig.daily_profit_target}
                    onChange={(e) => setStConfig({ ...stConfig, daily_profit_target: parseFloat(e.target.value) || 1000.0 })}
                    className="w-full bg-surface border border-border rounded-lg px-3 py-2 text-emerald-300 font-bold focus:outline-none focus:border-emerald-500"
                  />
                  <span className="text-[10px] text-gray-500">Locks new entries when reached (default +₹1,000).</span>
                </div>

                <div>
                  <label className="text-gray-400 block mb-1">Daily NET Loss Limit (₹):</label>
                  <input
                    type="number"
                    step="100"
                    value={stConfig.daily_loss_limit}
                    onChange={(e) => setStConfig({ ...stConfig, daily_loss_limit: parseFloat(e.target.value) || -2000.0 })}
                    className="w-full bg-surface border border-border rounded-lg px-3 py-2 text-rose-300 font-bold focus:outline-none focus:border-emerald-500"
                  />
                  <span className="text-[10px] text-gray-500">Locks new entries when reached (default -₹2,000).</span>
                </div>
              </div>

              {/* Dynamic Points Calculation Card */}
              <div className="bg-surface/60 border border-border/80 rounded-xl p-4 text-xs font-mono space-y-2">
                <div className="flex items-center justify-between text-gray-300 font-bold">
                  <span>Dynamic Premium SL / Target Reconciliation:</span>
                  <span className="text-[11px] text-gray-400">Formula: Net P&amp;L = Gross P&amp;L - Charges (₹20) - Slippage</span>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
                  <div className="bg-surface p-2.5 rounded border border-border/60">
                    <span className="text-gray-400 text-[10px] block">DYNAMIC TARGET POINTS</span>
                    <span className="text-emerald-400 font-bold text-sm">+{stTargetPts} points</span>
                    <p className="text-[10px] text-gray-500 mt-1">
                      ({stConfig.target_net_profit} net + ₹20 charges) / {stTradeQty} qty = +{stTargetPts} pts. Gross +₹{((parseFloat(stTargetPts) * stTradeQty)).toFixed(2)}.
                    </p>
                  </div>

                  <div className="bg-surface p-2.5 rounded border border-border/60">
                    <span className="text-gray-400 text-[10px] block">DYNAMIC STOP LOSS POINTS</span>
                    <span className="text-red-400 font-bold text-sm">-{stStopPts} points</span>
                    <p className="text-[10px] text-gray-500 mt-1">
                      ({stConfig.max_loss_per_trade} budget - ₹20 charges) / {stTradeQty} qty = -{stStopPts} pts. Gross -₹{((parseFloat(stStopPts) * stTradeQty)).toFixed(2)}.
                    </p>
                  </div>
                </div>
              </div>

              <div className="flex justify-end pt-2">
                <button
                  onClick={handleSaveSupertrendConfig}
                  disabled={saving}
                  className="px-6 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-mono font-bold text-xs transition-all flex items-center gap-2 shadow-lg shadow-emerald-500/20 disabled:opacity-50"
                >
                  <Save className="w-4 h-4" />
                  {saving ? 'Saving...' : 'Save & Activate Supertrend Parameters'}
                </button>
              </div>
            </div>

            {/* Sidebar Summary Card */}
            <div className="bg-card border border-border rounded-xl p-5 space-y-4 font-mono text-xs">
              <h4 className="font-bold text-white text-sm flex items-center gap-1.5">
                <Activity className="w-4 h-4 text-emerald-400" />
                Strategy Execution Rules
              </h4>

              <div className="space-y-3 text-gray-300 text-[11px] leading-relaxed">
                <div className="p-2.5 rounded bg-surface/60 border border-border">
                  <span className="text-emerald-400 font-bold block mb-1">BUY CE Entry Conditions:</span>
                  1. Supertrend direction is bullish (direction == 1)<br />
                  2. EMA 9 &gt; EMA 21<br />
                  3. Completed candle close &gt; EMA 9 and &gt; EMA 21<br />
                  4. Confirmed on same completed 1m candle<br />
                  5. No open position &amp; daily risk permits
                </div>

                <div className="p-2.5 rounded bg-surface/60 border border-border">
                  <span className="text-red-400 font-bold block mb-1">BUY PE Entry Conditions:</span>
                  1. Supertrend direction is bearish (direction == -1)<br />
                  2. EMA 9 &lt; EMA 21<br />
                  3. Completed candle close &lt; EMA 9 and &lt; EMA 21<br />
                  4. Confirmed on same completed 1m candle<br />
                  5. No open position &amp; daily risk permits
                </div>

                <div className="p-2.5 rounded bg-surface/60 border border-border">
                  <span className="text-amber-400 font-bold block mb-1">Exit Priorities:</span>
                  1. Target reached (+₹200 net)<br />
                  2. Stop loss reached (-₹1,000 net)<br />
                  3. Opposite confirmed Supertrend direction (Close, do not auto-reverse)<br />
                  4. Auto square-off at 15:20 IST
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* UT BOT STRATEGY VIEW */}
      {activeTab === 'UT_BOT' && (
        <div className="space-y-6">
          {/* Header Card */}
          <div className="bg-card border border-border rounded-xl p-5">
            <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
              <div className="flex items-center space-x-3">
                <div className="p-2.5 rounded-xl bg-amber-500/10 text-amber-400 border border-amber-500/30">
                  <Zap className="w-5 h-5" />
                </div>
                <div>
                  <h2 className="text-lg font-bold text-white">UT Bot ATM Option Strategy — Pine Script v4</h2>
                  <p className="text-xs text-gray-400 font-mono">
                    Underlying: NIFTY 50 | Instrument: ATM CE Option | Trailing Stop Sensitivity: {utConfig.key_value}
                  </p>
                </div>
              </div>

              <div className="flex items-center space-x-2">
                <button
                  onClick={() => handleSelectStrategy('UT_BOT')}
                  disabled={selectedStrategyId === 'UT_BOT'}
                  className={`px-3 py-1.5 rounded-lg text-xs font-mono font-bold transition-all flex items-center gap-1.5 ${
                    selectedStrategyId === 'UT_BOT'
                      ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 cursor-default'
                      : 'bg-blue-600 hover:bg-blue-500 text-white shadow-md'
                  }`}
                >
                  <ShieldCheck className="w-4 h-4" />
                  {selectedStrategyId === 'UT_BOT' ? 'LIVE FOR PAPER TRADING' : 'ACTIVATE FOR PAPER TRADING'}
                </button>
              </div>
            </div>

            {/* Live Indicator Telemetry Strip */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mt-4 pt-4 border-t border-border/60 text-xs font-mono">
              <div className="bg-surface/50 p-2.5 rounded-lg border border-border/60">
                <div className="text-gray-500 text-[10px]">SOURCE PRICE</div>
                <div className="text-white font-bold text-sm mt-0.5">
                  {utTelem?.source_price !== undefined ? `₹${utTelem.source_price.toFixed(2)}` : 'Evaluating...'}
                </div>
              </div>

              <div className="bg-surface/50 p-2.5 rounded-lg border border-border/60">
                <div className="text-gray-500 text-[10px]">ATR (10)</div>
                <div className="text-emerald-400 font-bold text-sm mt-0.5">
                  {utTelem?.atr !== undefined ? utTelem.atr.toFixed(2) : '--'}
                </div>
              </div>

              <div className="bg-surface/50 p-2.5 rounded-lg border border-border/60">
                <div className="text-gray-500 text-[10px]">TRAILING STOP</div>
                <div className="text-amber-400 font-bold text-sm mt-0.5">
                  {utTelem?.trailing_stop !== undefined ? `₹${utTelem.trailing_stop.toFixed(2)}` : '--'}
                </div>
              </div>

              <div className="bg-surface/50 p-2.5 rounded-lg border border-border/60">
                <div className="text-gray-500 text-[10px]">DIRECTION (POS)</div>
                <div
                  className={`font-bold text-sm mt-0.5 ${
                    utTelem?.pos === 1 ? 'text-emerald-400' : utTelem?.pos === -1 ? 'text-red-400' : 'text-gray-400'
                  }`}
                >
                  {utTelem?.pos === 1 ? 'LONG (+1)' : utTelem?.pos === -1 ? 'SHORT (-1)' : 'FLAT (0)'}
                </div>
              </div>

              <div className="bg-surface/50 p-2.5 rounded-lg border border-border/60">
                <div className="text-gray-500 text-[10px]">CROSSOVER STATE</div>
                <div className="font-bold text-xs mt-0.5 text-blue-400">
                  {utTelem?.above_crossover ? 'ABOVE (BUY)' : utTelem?.below_crossunder ? 'BELOW (SELL)' : 'IN POSITION'}
                </div>
              </div>

              <div className="bg-surface/50 p-2.5 rounded-lg border border-border/60">
                <div className="text-gray-500 text-[10px]">SESSION (09:20-15:15)</div>
                <div
                  className={`font-bold text-xs mt-0.5 ${
                    utTelem?.session_valid ? 'text-emerald-400' : 'text-amber-400'
                  }`}
                >
                  {utTelem?.session_valid ? 'SESSION OPEN' : 'SESSION CLOSED'}
                </div>
              </div>
            </div>
          </div>

          {/* Configuration Inputs & Live Risk Overlay */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Input Form Column (2/3) */}
            <div className="lg:col-span-2 bg-card border border-border rounded-xl p-5 space-y-4">
              <h3 className="font-bold text-white text-sm flex items-center gap-2">
                <Sliders className="w-4 h-4 text-blue-400" />
                UT Bot Strategy Parameters
              </h3>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs font-mono">
                <div>
                  <label className="text-gray-400 block mb-1">Key Value - Sensitivity (a):</label>
                  <input
                    type="number"
                    step="0.1"
                    min="0.1"
                    value={utConfig.key_value}
                    onChange={(e) => setUtConfig({ ...utConfig, key_value: parseFloat(e.target.value) || 1.0 })}
                    className="w-full bg-surface border border-border rounded-lg px-3 py-2 text-white font-bold focus:outline-none focus:border-blue-500"
                  />
                  <span className="text-[10px] text-gray-500">Default: 1.0 (ATR multiplier)</span>
                </div>

                <div>
                  <label className="text-gray-400 block mb-1">ATR Period (c):</label>
                  <input
                    type="number"
                    min="1"
                    value={utConfig.atr_period}
                    onChange={(e) => setUtConfig({ ...utConfig, atr_period: parseInt(e.target.value) || 10 })}
                    className="w-full bg-surface border border-border rounded-lg px-3 py-2 text-white font-bold focus:outline-none focus:border-blue-500"
                  />
                  <span className="text-[10px] text-gray-500">Default: 10 (Wilder's RMA smoothing)</span>
                </div>

                <div>
                  <label className="text-gray-400 block mb-1">Number of Lots:</label>
                  <input
                    type="number"
                    min="1"
                    value={utConfig.lots}
                    onChange={(e) => setUtConfig({ ...utConfig, lots: parseInt(e.target.value) || 1 })}
                    className="w-full bg-surface border border-border rounded-lg px-3 py-2 text-white font-bold focus:outline-none focus:border-blue-500"
                  />
                  <span className="text-[10px] text-gray-500">Default: 5 lots</span>
                </div>

                <div>
                  <label className="text-gray-400 block mb-1">Quantity per Lot:</label>
                  <input
                    type="number"
                    min="1"
                    value={utConfig.lot_size}
                    onChange={(e) => setUtConfig({ ...utConfig, lot_size: parseInt(e.target.value) || 65 })}
                    className="w-full bg-surface border border-border rounded-lg px-3 py-2 text-white font-bold focus:outline-none focus:border-blue-500"
                  />
                  <span className="text-[10px] text-gray-500">Current NIFTY Lot Size: 65</span>
                </div>

                <div>
                  <label className="text-gray-400 block mb-1">Target Points (Premium):</label>
                  <input
                    type="number"
                    step="0.5"
                    min="1"
                    value={utConfig.target_points}
                    onChange={(e) => setUtConfig({ ...utConfig, target_points: parseFloat(e.target.value) || 4.0 })}
                    className="w-full bg-surface border border-border rounded-lg px-3 py-2 text-white font-bold focus:outline-none focus:border-blue-500"
                  />
                  <span className="text-[10px] text-gray-500">Default: +4.0 premium points</span>
                </div>

                <div>
                  <label className="text-gray-400 block mb-1">Stop Loss Points (Premium):</label>
                  <input
                    type="number"
                    step="0.5"
                    min="1"
                    value={utConfig.stop_points}
                    onChange={(e) => setUtConfig({ ...utConfig, stop_points: parseFloat(e.target.value) || 2.0 })}
                    className="w-full bg-surface border border-border rounded-lg px-3 py-2 text-white font-bold focus:outline-none focus:border-blue-500"
                  />
                  <span className="text-[10px] text-gray-500">Default: -2.0 premium points</span>
                </div>

                <div>
                  <label className="text-gray-400 block mb-1">Signal Source Setting:</label>
                  <select
                    value={utConfig.signal_source}
                    onChange={(e) =>
                      setUtConfig({
                        ...utConfig,
                        signal_source: e.target.value as 'CHART_INSTRUMENT' | 'NIFTY_INDEX',
                      })
                    }
                    className="w-full bg-surface border border-border rounded-lg px-3 py-2 text-white font-bold focus:outline-none focus:border-blue-500"
                  >
                    <option value="CHART_INSTRUMENT">Selected Chart Instrument (Original Pine Script)</option>
                    <option value="NIFTY_INDEX">NIFTY Underlying Index (Spot)</option>
                  </select>
                  <span className="text-[10px] text-gray-500">Calculates signals from option vs spot candle</span>
                </div>

                <div className="flex flex-col justify-center">
                  <label className="text-gray-400 block mb-2">Candle Type:</label>
                  <label className="flex items-center space-x-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={utConfig.use_heikin_ashi}
                      onChange={(e) => setUtConfig({ ...utConfig, use_heikin_ashi: e.target.checked })}
                      className="rounded bg-surface border-border text-blue-600 focus:ring-0"
                    />
                    <span className="text-gray-300">Calculate signals from Heikin Ashi candles</span>
                  </label>
                  <span className="text-[10px] text-gray-500 mt-1">Default: OFF (standard candles)</span>
                </div>

                <div className="flex flex-col justify-center">
                  <label className="text-gray-400 block mb-2">Exit on UT Sell Signal:</label>
                  <label className="flex items-center space-x-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={utConfig.exit_on_ut_sell_signal ?? false}
                      onChange={(e) => setUtConfig({ ...utConfig, exit_on_ut_sell_signal: e.target.checked })}
                      className="rounded bg-surface border-border text-red-600 focus:ring-0"
                    />
                    <span className="text-gray-300">Exit open positions on opposite UT Sell</span>
                  </label>
                  <span className="text-[10px] text-gray-500 mt-1">Default: OFF (strict 2-pt SL / 4-pt Target)</span>
                </div>
              </div>

              {/* Risk Cap Toggle */}
              <div className="pt-3 border-t border-border/60">
                <label className="flex items-center space-x-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={useRiskCap}
                    onChange={(e) => setUseRiskCap(e.target.checked)}
                    className="rounded bg-surface border-border text-blue-600 focus:ring-0"
                  />
                  <span className="text-xs font-mono font-bold text-amber-300">
                    Apply ₹1,000 Total Max Loss Risk Cap Overlay
                  </span>
                </label>
                <p className="text-[11px] text-gray-400 mt-1 pl-5">
                  When enabled, automatically caps your maximum rupee loss per trade at ₹1,000.
                  Effective SL Distance = min(Configured SL Points, Max Loss / Quantity).
                  For 325 qty and 2.0 SL, normal risk is ₹650 (within ₹1,000 limit, effective SL remains 2.00 pts).
                  For larger sizes (e.g. 600 qty), effective SL tightens to {utCappedStopPoints.toFixed(2)} pts.
                </p>
              </div>

              <div className="pt-2">
                <button
                  onClick={handleSaveUTConfig}
                  disabled={saving}
                  className="px-5 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-mono font-bold text-xs flex items-center gap-2 transition-all shadow-md shadow-blue-500/20"
                >
                  <Save className="w-4 h-4" />
                  {saving ? 'Saving...' : 'Save & Activate Configuration for Paper Trading'}
                </button>
              </div>
            </div>

            {/* Live Parameter & Risk Preview Column (1/3) */}
            <div className="bg-card border border-border rounded-xl p-5 space-y-4">
              <h3 className="font-bold text-white text-sm flex items-center gap-2">
                <Activity className="w-4 h-4 text-emerald-400" />
                Live Order &amp; Risk Preview
              </h3>

              <div className="space-y-3 text-xs font-mono">
                <div className="bg-surface/60 p-3 rounded-lg border border-border">
                  <div className="text-gray-400 text-[11px]">Total Trade Quantity</div>
                  <div className="text-white text-lg font-bold mt-1">
                    {utTradeQty} <span className="text-xs font-normal text-gray-400">({utConfig.lots} lots × {utConfig.lot_size})</span>
                  </div>
                </div>

                <div className="bg-surface/60 p-3 rounded-lg border border-border">
                  <div className="text-gray-400 text-[11px]">Baseline {utConfig.stop_points}-Point SL Loss</div>
                  <div className="text-red-400 text-base font-bold mt-1">
                    -₹{utBaselineRisk.toFixed(2)}
                  </div>
                  <div className="text-[10px] text-gray-500 mt-0.5">
                    {utConfig.stop_points} pts × {utTradeQty} qty
                  </div>
                </div>

                <div
                  className={`p-3 rounded-lg border ${
                    useRiskCap ? 'bg-amber-500/10 border-amber-500/30' : 'bg-surface/60 border-border'
                  }`}
                >
                  <div className="text-amber-400 font-bold text-[11px]">
                    {useRiskCap ? '₹1,000 Capped Effective Stop' : 'Standard Stop Loss'}
                  </div>
                  <div className="text-white text-base font-bold mt-1">
                    -{utCappedStopPoints.toFixed(2)} points
                  </div>
                  <div className="text-[10px] text-gray-400 mt-0.5">
                    Max rupee risk: ₹{utMaxLossActual.toFixed(2)}
                  </div>
                </div>

                <div className="bg-surface/60 p-3 rounded-lg border border-border">
                  <div className="text-gray-400 text-[11px]">Target Profit (+4.0 pts)</div>
                  <div className="text-emerald-400 text-base font-bold mt-1">
                    +₹{(utConfig.target_points * utTradeQty).toFixed(2)}
                  </div>
                  <div className="text-[10px] text-gray-500 mt-0.5">
                    +{utConfig.target_points} pts × {utTradeQty} qty
                  </div>
                </div>

                <div className="bg-surface/40 p-3 rounded-lg border border-border text-[11px] text-gray-400 space-y-1">
                  <div className="font-bold text-gray-300">Execution Guarantees:</div>
                  <div>&bull; Pyramiding: Disabled (1 position max)</div>
                  <div>&bull; BUY Signal: Enters long option</div>
                  <div>&bull; Opposite SELL: Closes long immediately</div>
                  <div>&bull; Force Exit: 15:20 IST daily</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* EMA / RSI STRATEGY VIEW */}
      {activeTab === 'EMA_RSI' && (
        <div className="space-y-6">
          {/* Header Card */}
          <div className="bg-card border border-border rounded-xl p-5">
            <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
              <div className="flex items-center space-x-3">
                <div className="p-2.5 rounded-xl bg-purple-500/10 text-purple-400 border border-purple-500/30">
                  <Layers className="w-5 h-5" />
                </div>
                <div>
                  <h2 className="text-lg font-bold text-white">Original NIFTY EMA 9/21/50 + RSI 14 Strategy</h2>
                  <p className="text-xs text-gray-400 font-mono">
                    Underlying: NIFTY 50 Spot | Instrument: NIFTY ATM CE Option | Timeframe: 1 Minute
                  </p>
                </div>
              </div>

              <div className="flex items-center space-x-2">
                <button
                  onClick={() => handleSelectStrategy('EMA_RSI')}
                  disabled={selectedStrategyId === 'EMA_RSI'}
                  className={`px-3 py-1.5 rounded-lg text-xs font-mono font-bold transition-all flex items-center gap-1.5 ${
                    selectedStrategyId === 'EMA_RSI'
                      ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 cursor-default'
                      : 'bg-blue-600 hover:bg-blue-500 text-white shadow-md'
                  }`}
                >
                  <ShieldCheck className="w-4 h-4" />
                  {selectedStrategyId === 'EMA_RSI' ? 'LIVE FOR PAPER TRADING' : 'ACTIVATE FOR PAPER TRADING'}
                </button>
              </div>
            </div>

            {/* 4 Conditions Card Layout */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mt-4">
              <div
                className={`p-4 rounded-xl border ${
                  strategyStatus?.condition_1
                    ? 'bg-emerald-950/20 border-emerald-800/50 text-emerald-300'
                    : 'bg-surface/50 border-border text-gray-400'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="font-semibold text-xs text-white">Condition 1</span>
                  {strategyStatus?.condition_1 ? (
                    <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                  ) : (
                    <XCircle className="w-4 h-4 text-gray-500" />
                  )}
                </div>
                <div className="text-sm font-bold font-mono">EMA 9 &gt; EMA 21</div>
                <p className="text-[11px] text-gray-400 mt-1">Short-term trend momentum above medium trend.</p>
                <div className="mt-3 pt-2 border-t border-border/50 text-[11px] font-mono">
                  Value: {strategyStatus?.ema_9?.toFixed(1) || '--'} vs {strategyStatus?.ema_21?.toFixed(1) || '--'}
                </div>
              </div>

              <div
                className={`p-4 rounded-xl border ${
                  strategyStatus?.condition_2
                    ? 'bg-emerald-950/20 border-emerald-800/50 text-emerald-300'
                    : 'bg-surface/50 border-border text-gray-400'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="font-semibold text-xs text-white">Condition 2</span>
                  {strategyStatus?.condition_2 ? (
                    <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                  ) : (
                    <XCircle className="w-4 h-4 text-gray-500" />
                  )}
                </div>
                <div className="text-sm font-bold font-mono">Close &gt; EMA 50</div>
                <p className="text-[11px] text-gray-400 mt-1">NIFTY spot candle close above 50-period EMA baseline.</p>
                <div className="mt-3 pt-2 border-t border-border/50 text-[11px] font-mono">
                  Value: {strategyStatus?.underlying_price?.toFixed(1) || '--'} vs {strategyStatus?.ema_50?.toFixed(1) || '--'}
                </div>
              </div>

              <div
                className={`p-4 rounded-xl border ${
                  strategyStatus?.condition_3
                    ? 'bg-emerald-950/20 border-emerald-800/50 text-emerald-300'
                    : 'bg-surface/50 border-border text-gray-400'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="font-semibold text-xs text-white">Condition 3</span>
                  {strategyStatus?.condition_3 ? (
                    <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                  ) : (
                    <XCircle className="w-4 h-4 text-gray-500" />
                  )}
                </div>
                <div className="text-sm font-bold font-mono">RSI 14 &gt; 50.0</div>
                <p className="text-[11px] text-gray-400 mt-1">Wilder's 14-period RSI in bullish expansion territory.</p>
                <div className="mt-3 pt-2 border-t border-border/50 text-[11px] font-mono">
                  Value: {strategyStatus?.rsi_14?.toFixed(2) || '--'}
                </div>
              </div>

              <div
                className={`p-4 rounded-xl border ${
                  strategyStatus?.condition_4
                    ? 'bg-emerald-950/20 border-emerald-800/50 text-emerald-300'
                    : 'bg-surface/50 border-border text-gray-400'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="font-semibold text-xs text-white">Condition 4</span>
                  {strategyStatus?.condition_4 ? (
                    <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                  ) : (
                    <XCircle className="w-4 h-4 text-gray-500" />
                  )}
                </div>
                <div className="text-sm font-bold font-mono">Session Filter</div>
                <p className="text-[11px] text-gray-400 mt-1">Trading permitted strictly between 09:20 and 15:15 IST.</p>
                <div className="mt-3 pt-2 border-t border-border/50 text-[11px] font-mono">
                  Candle: {strategyStatus?.time_ist || '--'} IST
                </div>
              </div>
            </div>

            {/* Configuration Form */}
            <div className="mt-6 pt-4 border-t border-border flex flex-wrap items-center gap-4 text-xs font-mono">
              <div>
                <label className="text-gray-400 block mb-1">Lots:</label>
                <input
                  type="number"
                  min="1"
                  value={emaLots}
                  onChange={(e) => setEmaLots(parseInt(e.target.value) || 1)}
                  className="w-20 bg-surface border border-border rounded-lg px-2 py-1 text-white font-bold"
                />
              </div>
              <div>
                <label className="text-gray-400 block mb-1">Lot Size:</label>
                <input
                  type="number"
                  min="1"
                  value={emaLotSize}
                  onChange={(e) => setEmaLotSize(parseInt(e.target.value) || 65)}
                  className="w-20 bg-surface border border-border rounded-lg px-2 py-1 text-white font-bold"
                />
              </div>
              <div>
                <label className="text-gray-400 block mb-1">Target Points:</label>
                <input
                  type="number"
                  step="0.5"
                  value={emaTarget}
                  onChange={(e) => setEmaTarget(parseFloat(e.target.value) || 4.0)}
                  className="w-24 bg-surface border border-border rounded-lg px-2 py-1 text-white font-bold"
                />
              </div>
              <div>
                <label className="text-gray-400 block mb-1">Stop Points:</label>
                <input
                  type="number"
                  step="0.5"
                  value={emaStop}
                  onChange={(e) => setEmaStop(parseFloat(e.target.value) || 4.0)}
                  className="w-24 bg-surface border border-border rounded-lg px-2 py-1 text-white font-bold"
                />
              </div>
              <div className="flex items-end">
                <button
                  onClick={handleSaveEMAConfig}
                  disabled={saving}
                  className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-bold flex items-center gap-1.5 transition-colors"
                >
                  <Save className="w-3.5 h-3.5" /> Save EMA Config
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Strategy Signal History Table */}
      <div className="bg-card border border-border rounded-xl p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-bold text-white text-sm">Strategy Signals &amp; Candle Confirmations</h3>
          <button
            onClick={loadSignals}
            className="text-xs text-blue-400 hover:text-blue-300 font-mono transition-colors"
          >
            Refresh Log
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-xs font-mono text-left">
            <thead>
              <tr className="bg-surface/60 border-b border-border text-gray-400 uppercase text-[11px]">
                <th className="px-3 py-2">Signal ID</th>
                <th className="px-3 py-2">Strategy</th>
                <th className="px-3 py-2">Candle Time</th>
                <th className="px-3 py-2">Source Price</th>
                <th className="px-3 py-2">Telemetry (ATR / Stop / RSI)</th>
                <th className="px-3 py-2">Signal</th>
                <th className="px-3 py-2">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/40">
              {signals.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-gray-500">
                    No signals logged yet. Evaluating completed bars...
                  </td>
                </tr>
              ) : (
                signals.map((s) => (
                  <tr key={s.id} className="hover:bg-surface/40">
                    <td className="px-3 py-2 text-gray-400">#{s.id}</td>
                    <td className="px-3 py-2 font-bold text-gray-300">
                      {s.strategy_id === 'UT_BOT' ? 'UT BOT' : 'EMA RSI'}
                    </td>
                    <td className="px-3 py-2">{s.candle_time}</td>
                    <td className="px-3 py-2 font-bold text-white">{s.underlying_price.toFixed(2)}</td>
                    <td className="px-3 py-2 text-gray-400">
                      {s.strategy_id === 'UT_BOT' ? (
                        <span>
                          ATR: {s.atr ? s.atr.toFixed(2) : '--'} | Stop: {s.trailing_stop ? s.trailing_stop.toFixed(2) : '--'}
                        </span>
                      ) : (
                        <span>
                          EMA 9: {s.ema_9?.toFixed(1)} | EMA 21: {s.ema_21?.toFixed(1)} | RSI: {s.rsi_14?.toFixed(1)}
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          s.signal_type?.includes('BUY')
                            ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                            : s.signal_type?.includes('SELL')
                            ? 'bg-red-500/20 text-red-400 border border-red-500/30'
                            : 'bg-gray-800 text-gray-500'
                        }`}
                      >
                        {s.signal_type}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-gray-400">
                      {s.executed ? (
                        <span className="text-emerald-400 font-semibold">Paper Executed</span>
                      ) : (
                        <span>Monitored</span>
                      )}
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
