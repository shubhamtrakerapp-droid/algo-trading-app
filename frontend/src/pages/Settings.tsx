import React, { useEffect, useState } from 'react';
import {
  Settings as SettingsIcon,
  Shield,
  Server,
  Key,
  AlertTriangle,
  CheckCircle2,
  Trash2,
  RotateCcw,
  Receipt,
  Calculator,
  Save,
  Check,
  RefreshCw,
  Info,
  Clock,
  Timer,
  PlayCircle
} from 'lucide-react';
import { MarketStatus, SystemEventItem } from '../types';
import { api } from '../services/api';
import { formatIST, formatCurrency } from '../utils/formatters';

interface SettingsProps {
  marketStatus: MarketStatus | null;
  onResetPaper?: () => void;
}

export const Settings: React.FC<SettingsProps> = ({ marketStatus, onResetPaper }) => {
  const [events, setEvents] = useState<SystemEventItem[]>([]);
  const [loading, setLoading] = useState(false);

  // Paper Trading Charges State
  const [entryCharge, setEntryCharge] = useState<number>(10);
  const [exitCharge, setExitCharge] = useState<number>(10);
  const [isSavingCharges, setIsSavingCharges] = useState<boolean>(false);
  const [chargeSaveSuccess, setChargeSaveSuccess] = useState<boolean>(false);
  const [recalcPreview, setRecalcPreview] = useState<{
    trades_count: number;
    total_pnl_diff: number;
    preview: any[];
  } | null>(null);
  const [recalcLoading, setRecalcLoading] = useState<boolean>(false);
  const [recalcSuccessMsg, setRecalcSuccessMsg] = useState<string | null>(null);

  // Auto Exit Settings State
  const [autoExitEnabled, setAutoExitEnabled] = useState<boolean>(true);
  const [autoCloseTime, setAutoCloseTime] = useState<string>('15:20');
  const [applyAllStrategies, setApplyAllStrategies] = useState<boolean>(true);
  const [closeProfitable, setCloseProfitable] = useState<boolean>(true);
  const [closeLosing, setCloseLosing] = useState<boolean>(true);
  const [autoExitStatus, setAutoExitStatus] = useState<string>('STANDBY: Scheduled for 03:20 PM IST');
  const [timeRemainingDisplay, setTimeRemainingDisplay] = useState<string>('0m 0s');
  const [autoExitWarning, setAutoExitWarning] = useState<string | null>(null);
  const [awaitingData, setAwaitingData] = useState<boolean>(false);
  const [isSavingAutoExit, setIsSavingAutoExit] = useState<boolean>(false);
  const [autoExitSaveSuccess, setAutoExitSaveSuccess] = useState<boolean>(false);
  const [isTriggeringAutoExit, setIsTriggeringAutoExit] = useState<boolean>(false);
  const [triggerResultMsg, setTriggerResultMsg] = useState<string | null>(null);

  const loadAutoExitSettings = () => {
    api.getAutoExitSettings()
      .then((cfg) => {
        if (cfg) {
          setAutoExitEnabled(cfg.enabled ?? true);
          setAutoCloseTime(cfg.auto_close_time || '15:20');
          setApplyAllStrategies(cfg.apply_to_all_strategies ?? true);
          setCloseProfitable(cfg.close_profitable ?? true);
          setCloseLosing(cfg.close_losing ?? true);
          setAutoExitStatus(cfg.last_status || 'STANDBY');
          setTimeRemainingDisplay(cfg.time_remaining_display || '');
          setAutoExitWarning(cfg.execution_warning || null);
          setAwaitingData(cfg.awaiting_valid_data || false);
        }
      })
      .catch(console.error);
  };

  useEffect(() => {
    api.getSystemEvents(20).then(setEvents).catch(console.error);
    api.getChargesSettings()
      .then((cfg) => {
        if (cfg) {
          setEntryCharge(Number(cfg.entry_charge_per_order ?? 10));
          setExitCharge(Number(cfg.exit_charge_per_order ?? 10));
        }
      })
      .catch(console.error);

    loadAutoExitSettings();
    const interval = setInterval(loadAutoExitSettings, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleSaveAutoExit = async () => {
    setIsSavingAutoExit(true);
    setTriggerResultMsg(null);
    try {
      const res = await api.updateAutoExitSettings({
        enabled: autoExitEnabled,
        auto_close_time: autoCloseTime,
        apply_to_all_strategies: applyAllStrategies,
        close_profitable: closeProfitable,
        close_losing: closeLosing
      });
      setAutoExitSaveSuccess(true);
      setAutoExitStatus(res.last_status || 'SAVED');
      setTimeout(() => setAutoExitSaveSuccess(false), 3000);
    } catch (e) {
      console.error(e);
      alert('Failed to save auto exit settings: ' + (e instanceof Error ? e.message : String(e)));
    } finally {
      setIsSavingAutoExit(false);
    }
  };

  const handleManualTriggerAutoExit = async () => {
    if (!window.confirm('Trigger Auto Exit immediately on all open positions? This will square off all active positions with configured exit charges.')) {
      return;
    }
    setIsTriggeringAutoExit(true);
    setTriggerResultMsg(null);
    try {
      const res = await api.triggerAutoExit(true);
      if (res.status === 'CLOSED') {
        setTriggerResultMsg(`Auto Exit Executed: Closed ${res.trade?.symbol} at ₹${res.trade?.exit_price} (Net P&L: ₹${res.trade?.net_pnl})`);
        if (onResetPaper) onResetPaper();
      } else {
        setTriggerResultMsg(`Auto Exit Trigger: ${res.message || 'No active positions to close'}`);
      }
      loadAutoExitSettings();
      setTimeout(() => setTriggerResultMsg(null), 6000);
    } catch (e) {
      console.error(e);
      alert('Failed to trigger auto exit: ' + (e instanceof Error ? e.message : String(e)));
    } finally {
      setIsTriggeringAutoExit(false);
    }
  };

  const handleSaveCharges = async () => {
    setIsSavingCharges(true);
    try {
      await api.updateChargesSettings(Number(entryCharge), Number(exitCharge));
      setChargeSaveSuccess(true);
      setTimeout(() => setChargeSaveSuccess(false), 3000);
    } catch (e) {
      console.error(e);
      alert('Failed to save charge settings: ' + (e instanceof Error ? e.message : String(e)));
    } finally {
      setIsSavingCharges(false);
    }
  };

  const handlePreviewRecalc = async () => {
    setRecalcLoading(true);
    setRecalcSuccessMsg(null);
    try {
      const res = await api.recalculateCharges(false);
      setRecalcPreview(res);
    } catch (e) {
      console.error(e);
      alert('Failed to preview recalculation: ' + (e instanceof Error ? e.message : String(e)));
    } finally {
      setRecalcLoading(false);
    }
  };

  const handleApplyRecalc = async () => {
    if (!window.confirm('Apply new charge rates to all historical paper trades? This will recalculate historical net P&L and adjust cash balance.')) {
      return;
    }
    setRecalcLoading(true);
    try {
      const res = await api.recalculateCharges(true);
      setRecalcPreview(null);
      setRecalcSuccessMsg(`Successfully recalculated ${res.trades_count} past trades. Cash balance reconciled.`);
      if (onResetPaper) onResetPaper();
      setTimeout(() => setRecalcSuccessMsg(null), 5000);
    } catch (e) {
      console.error(e);
      alert('Failed to apply recalculation: ' + (e instanceof Error ? e.message : String(e)));
    } finally {
      setRecalcLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-card border border-border rounded-xl p-5">
        <div className="flex items-center space-x-3">
          <div className="p-2.5 rounded-xl bg-blue-600/10 text-blue-400 border border-blue-500/30">
            <SettingsIcon className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-white">System Settings &amp; Broker Configuration</h2>
            <p className="text-xs text-gray-400 font-mono">
              Broker adapter credentials, virtual broker risk parameters, and backend audit events
            </p>
          </div>
        </div>
      </div>

      {/* Grid: Broker Connection & Security */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Kotak Neo Adapter Status */}
        <div className="bg-card border border-border rounded-xl p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="font-bold text-white text-sm flex items-center gap-2">
              <Server className="w-4 h-4 text-blue-400" />
              Kotak Neo Broker Integration
            </h3>
            <span
              className={`text-xs px-2.5 py-0.5 rounded font-mono font-bold ${
                marketStatus?.is_demo
                  ? 'bg-purple-500/10 text-purple-400 border border-purple-500/30'
                  : 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30'
              }`}
            >
              {marketStatus?.is_demo ? 'SYNTHETIC DEMO' : 'LIVE CONNECTED'}
            </span>
          </div>

          <div className="space-y-2 text-xs font-mono">
            <div className="flex justify-between p-2 rounded bg-surface border border-border">
              <span className="text-gray-400">Adapter Type:</span>
              <span className="text-white font-semibold">{marketStatus?.broker_name || 'Kotak Neo'}</span>
            </div>
            <div className="flex justify-between p-2 rounded bg-surface border border-border">
              <span className="text-gray-400">Feed Protocol:</span>
              <span className="text-blue-400 font-semibold">Kotak SFeed WebSocket</span>
            </div>
            <div className="flex justify-between p-2 rounded bg-surface border border-border">
              <span className="text-gray-400">Instrument Master:</span>
              <span className="text-white font-semibold">NSE F&amp;O Scrip Master</span>
            </div>
            <div className="flex justify-between p-2 rounded bg-surface border border-border">
              <span className="text-gray-400">Underlying Index:</span>
              <span className="text-white font-semibold">NIFTY 50 (Token: 26000)</span>
            </div>
            <div className="flex justify-between p-2 rounded bg-surface border border-border">
              <span className="text-gray-400">Active Option:</span>
              <span className="text-emerald-400 font-semibold">{marketStatus?.option_symbol || 'NIFTY ATM CE'}</span>
            </div>
          </div>
        </div>

        {/* Security & Credentials Isolation */}
        <div className="bg-card border border-border rounded-xl p-5 space-y-4">
          <h3 className="font-bold text-white text-sm flex items-center gap-2">
            <Shield className="w-4 h-4 text-emerald-400" />
            Backend Security &amp; Credentials Isolation
          </h3>

          <div className="p-3.5 rounded-lg bg-emerald-950/20 border border-emerald-800/40 text-xs space-y-2 text-gray-300">
            <div className="flex items-center gap-2 text-emerald-400 font-semibold">
              <CheckCircle2 className="w-4 h-4 shrink-0" />
              <span>Zero-Exposure Architecture</span>
            </div>
            <p className="text-[11px] leading-relaxed">
              Kotak Neo API Consumer Key, Consumer Secret, UCC, and Access Tokens are stored strictly in backend
              environment variables (<code className="text-white font-mono">.env</code>). Credentials are never sent to the
              browser, JavaScript bundles, or logged in client console output.
            </p>
          </div>

          <div className="p-3.5 rounded-lg bg-surface border border-border text-xs font-mono space-y-1">
            <span className="text-gray-400 block mb-1">Backend Configuration (.env):</span>
            <div className="text-gray-400 text-[11px]">KOTAK_CONSUMER_KEY=******</div>
            <div className="text-gray-400 text-[11px]">KOTAK_UCC=******</div>
            <div className="text-gray-400 text-[11px]">DATABASE_URL=sqlite+aiosqlite:///./nextrade.db</div>
          </div>
        </div>
      </div>

      {/* Paper Trading Charges Configuration */}
      <div className="bg-card border border-border rounded-xl p-5 space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border/60 pb-4">
          <div className="flex items-center space-x-3">
            <div className="p-2 rounded-lg bg-emerald-600/10 text-emerald-400 border border-emerald-500/30">
              <Receipt className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-bold text-white text-base">Paper Trading Charges</h3>
              <p className="text-xs text-gray-400 font-mono">
                Configurable flat per-order simulated brokerage fees. Persisted in database and applied to all simulated fills.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleSaveCharges}
              disabled={isSavingCharges}
              className={`px-4 py-2 rounded-lg text-xs font-mono font-semibold transition-all flex items-center gap-2 ${
                chargeSaveSuccess
                  ? 'bg-emerald-600 text-white'
                  : 'bg-blue-600 hover:bg-blue-500 text-white'
              }`}
            >
              {chargeSaveSuccess ? (
                <>
                  <Check className="w-4 h-4" />
                  Saved to Database!
                </>
              ) : (
                <>
                  <Save className={`w-4 h-4 ${isSavingCharges ? 'animate-spin' : ''}`} />
                  Save Charges Settings
                </>
              )}
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {/* Input: Entry Charge */}
          <div className="bg-surface/50 border border-border rounded-xl p-4 space-y-2">
            <label className="text-xs font-mono font-bold text-gray-300 block">
              Entry Charge per Order (₹)
            </label>
            <div className="relative">
              <span className="absolute left-3 top-2.5 text-gray-400 font-mono text-sm">₹</span>
              <input
                type="number"
                step="0.5"
                min="0"
                value={entryCharge}
                onChange={(e) => setEntryCharge(parseFloat(e.target.value) || 0)}
                className="w-full bg-surface border border-border focus:border-blue-500 rounded-lg pl-8 pr-3 py-2 text-sm font-mono text-white focus:outline-none transition-colors"
                placeholder="10.00"
              />
            </div>
            <p className="text-[11px] text-gray-500 font-mono">
              Flat fee charged when an entry BUY order is filled. Default ₹10.
            </p>
          </div>

          {/* Input: Exit Charge */}
          <div className="bg-surface/50 border border-border rounded-xl p-4 space-y-2">
            <label className="text-xs font-mono font-bold text-gray-300 block">
              Exit Charge per Order (₹)
            </label>
            <div className="relative">
              <span className="absolute left-3 top-2.5 text-gray-400 font-mono text-sm">₹</span>
              <input
                type="number"
                step="0.5"
                min="0"
                value={exitCharge}
                onChange={(e) => setExitCharge(parseFloat(e.target.value) || 0)}
                className="w-full bg-surface border border-border focus:border-blue-500 rounded-lg pl-8 pr-3 py-2 text-sm font-mono text-white focus:outline-none transition-colors"
                placeholder="10.00"
              />
            </div>
            <p className="text-[11px] text-gray-500 font-mono">
              Flat fee charged when an exit SELL order is filled. Default ₹10.
            </p>
          </div>

          {/* Live Calculation Preview Card */}
          <div className="bg-gradient-to-br from-blue-950/30 to-purple-950/20 border border-blue-500/30 rounded-xl p-4 space-y-2.5">
            <div className="flex items-center justify-between text-blue-400 font-mono text-xs font-bold">
              <span className="flex items-center gap-1.5">
                <Calculator className="w-3.5 h-3.5" />
                Live Calculation Preview
              </span>
              <span className="text-[10px] bg-blue-500/20 px-2 py-0.5 rounded text-blue-300">
                1 Trade (1 Entry + 1 Exit)
              </span>
            </div>

            <div className="space-y-1.5 font-mono text-xs">
              <div className="flex justify-between text-gray-300">
                <span>Entry:</span>
                <span className="font-bold text-white">₹{Number(entryCharge).toFixed(2)}</span>
              </div>
              <div className="flex justify-between text-gray-300">
                <span>Exit:</span>
                <span className="font-bold text-white">₹{Number(exitCharge).toFixed(2)}</span>
              </div>
              <div className="border-t border-blue-500/20 pt-1.5 flex justify-between text-emerald-400 font-bold">
                <span>Total round-trip charge:</span>
                <span className="text-sm">₹{(Number(entryCharge) + Number(exitCharge)).toFixed(2)}</span>
              </div>
            </div>

            <p className="text-[10px] text-gray-400 leading-tight pt-1">
              Flat per completed trade. Charges are NEVER multiplied by quantity, lots, or turnover.
            </p>
          </div>
        </div>

        {/* Rule verification alert */}
        <div className="p-3.5 rounded-lg bg-surface border border-border/80 flex items-start gap-3 text-xs">
          <Info className="w-4 h-4 text-blue-400 shrink-0 mt-0.5" />
          <div className="space-y-1 text-gray-300">
            <span className="font-semibold text-white">Accounting Transparency &amp; Non-Destructive Storage</span>
            <p className="text-[11px] text-gray-400">
              Each trade stores its actual applied entry and exit charges. Updating charges applies to future orders and does not silently alter historical records.
            </p>
          </div>
        </div>

        {/* Optional Historical Recalculation Tool */}
        <div className="border-t border-border/60 pt-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h4 className="font-bold text-xs text-white">Historical Trades Recalculation (Controlled)</h4>
            <p className="text-[11px] text-gray-400 font-mono">
              Optionally preview and sync past trades with current ₹{(Number(entryCharge) + Number(exitCharge)).toFixed(2)} roundtrip charges.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handlePreviewRecalc}
              disabled={recalcLoading}
              className="px-3 py-1.5 rounded-lg bg-surface border border-border text-xs font-mono text-gray-300 hover:text-white transition-colors flex items-center gap-1.5"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${recalcLoading ? 'animate-spin' : ''}`} />
              Preview Recalculation
            </button>
          </div>
        </div>

        {recalcSuccessMsg && (
          <div className="p-3 rounded-lg bg-emerald-950/40 border border-emerald-500/40 text-emerald-400 text-xs font-mono flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 shrink-0" />
            <span>{recalcSuccessMsg}</span>
          </div>
        )}

        {recalcPreview && (
          <div className="bg-surface/80 border border-border rounded-xl p-4 space-y-3 font-mono text-xs">
            <div className="flex items-center justify-between">
              <span className="font-bold text-white">
                Recalculation Preview ({recalcPreview.trades_count} trades analyzed)
              </span>
              <span className={`font-bold ${recalcPreview.total_pnl_diff >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                Portfolio Net P&amp;L Impact: {formatCurrency(recalcPreview.total_pnl_diff)}
              </span>
            </div>

            {recalcPreview.trades_count === 0 ? (
              <p className="text-gray-500 text-[11px]">No closed historical paper trades to recalculate.</p>
            ) : (
              <div className="max-h-40 overflow-y-auto divide-y divide-border/40 text-[11px]">
                {recalcPreview.preview.slice(0, 10).map((p: any) => (
                  <div key={p.trade_id} className="py-1.5 flex justify-between text-gray-300">
                    <span>Trade #{p.trade_id}:</span>
                    <span>Old Charges: ₹{p.old_charges.toFixed(2)} → New: ₹{p.new_charges.toFixed(2)}</span>
                    <span className={p.diff >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
                      P&amp;L Δ: {formatCurrency(p.diff)}
                    </span>
                  </div>
                ))}
                {recalcPreview.preview.length > 10 && (
                  <div className="py-1 text-center text-gray-500">
                    ...and {recalcPreview.preview.length - 10} more trades
                  </div>
                )}
              </div>
            )}

            {recalcPreview.trades_count > 0 && (
              <div className="pt-2 flex justify-end gap-2">
                <button
                  onClick={() => setRecalcPreview(null)}
                  className="px-3 py-1.5 rounded-lg bg-surface border border-border text-gray-400 hover:text-white"
                >
                  Dismiss
                </button>
                <button
                  onClick={handleApplyRecalc}
                  disabled={recalcLoading}
                  className="px-3 py-1.5 rounded-lg bg-amber-600 hover:bg-amber-500 text-white font-semibold flex items-center gap-1.5"
                >
                  Apply &amp; Reconcile Cash
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Auto Exit Settings Configuration */}
      <div className="bg-card border border-border rounded-xl p-5 space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border/60 pb-4">
          <div className="flex items-center space-x-3">
            <div className="p-2 rounded-lg bg-amber-600/10 text-amber-400 border border-amber-500/30">
              <Clock className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-bold text-white text-base">Auto Exit Settings</h3>
              <p className="text-xs text-gray-400 font-mono">
                Mandatory session square-off (default 03:20 PM IST). Closes open positions, applies exit charges, and blocks overnight risk.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleManualTriggerAutoExit}
              disabled={isTriggeringAutoExit}
              className="px-3 py-2 rounded-lg bg-surface border border-amber-500/40 text-amber-300 hover:bg-amber-500/10 text-xs font-mono font-semibold transition-colors flex items-center gap-1.5"
              title="Test immediate auto exit execution on open position"
            >
              <PlayCircle className={`w-3.5 h-3.5 ${isTriggeringAutoExit ? 'animate-spin' : ''}`} />
              Test Auto Exit Now
            </button>

            <button
              onClick={handleSaveAutoExit}
              disabled={isSavingAutoExit}
              className={`px-4 py-2 rounded-lg text-xs font-mono font-semibold transition-all flex items-center gap-2 ${
                autoExitSaveSuccess
                  ? 'bg-emerald-600 text-white'
                  : 'bg-blue-600 hover:bg-blue-500 text-white'
              }`}
            >
              {autoExitSaveSuccess ? (
                <>
                  <Check className="w-4 h-4" />
                  Saved to Database!
                </>
              ) : (
                <>
                  <Save className={`w-4 h-4 ${isSavingAutoExit ? 'animate-spin' : ''}`} />
                  Save Auto Exit Settings
                </>
              )}
            </button>
          </div>
        </div>

        {triggerResultMsg && (
          <div className="p-3.5 rounded-lg bg-blue-950/40 border border-blue-500/40 text-blue-300 text-xs font-mono flex items-center gap-2">
            <Info className="w-4 h-4 shrink-0 text-blue-400" />
            <span>{triggerResultMsg}</span>
          </div>
        )}

        {awaitingData && autoExitWarning && (
          <div className="p-3.5 rounded-lg bg-amber-950/40 border border-amber-500/40 text-amber-300 text-xs font-mono flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0 text-amber-400 mt-0.5" />
            <div className="space-y-1">
              <span className="font-bold">Execution Warning: Market Data Awaiting Valid Quotes</span>
              <p className="text-[11px] text-amber-200/80">{autoExitWarning}</p>
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {/* Toggle: Enable Auto Close */}
          <div className="bg-surface/50 border border-border rounded-xl p-4 flex flex-col justify-between space-y-3">
            <div>
              <span className="text-xs font-mono font-bold text-gray-300 block">
                Enable Auto Close
              </span>
              <p className="text-[11px] text-gray-500 font-mono mt-1">
                When enabled, automatically squares off open paper positions at the scheduled cutoff time.
              </p>
            </div>
            <div className="flex items-center justify-between pt-2 border-t border-border/40">
              <span className="text-xs font-mono font-bold text-white">
                {autoExitEnabled ? 'ENABLED' : 'DISABLED'}
              </span>
              <button
                type="button"
                onClick={() => setAutoExitEnabled(!autoExitEnabled)}
                className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                  autoExitEnabled ? 'bg-emerald-600' : 'bg-gray-700'
                }`}
              >
                <span
                  className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                    autoExitEnabled ? 'translate-x-5' : 'translate-x-0'
                  }`}
                />
              </button>
            </div>
          </div>

          {/* Input: Auto Close Time */}
          <div className="bg-surface/50 border border-border rounded-xl p-4 space-y-2">
            <label className="text-xs font-mono font-bold text-gray-300 block">
              Auto Close Time (IST)
            </label>
            <div className="relative">
              <input
                type="text"
                value={autoCloseTime}
                onChange={(e) => setAutoCloseTime(e.target.value)}
                placeholder="15:20"
                className="w-full bg-surface border border-border focus:border-blue-500 rounded-lg px-3 py-2 text-sm font-mono text-white focus:outline-none transition-colors"
              />
            </div>
            <p className="text-[11px] text-gray-500 font-mono">
              Default: <strong>15:20</strong> (03:20 PM IST). 24-hour format (HH:MM).
            </p>
          </div>

          {/* Toggle: Apply to all strategies */}
          <div className="bg-surface/50 border border-border rounded-xl p-4 flex flex-col justify-between space-y-3">
            <div>
              <span className="text-xs font-mono font-bold text-gray-300 block">
                Apply to All Strategies
              </span>
              <p className="text-[11px] text-gray-500 font-mono mt-1">
                Applies cutoff uniformly across UT Bot ATM Option and NIFTY EMA/RSI strategies.
              </p>
            </div>
            <div className="flex items-center justify-between pt-2 border-t border-border/40">
              <span className="text-xs font-mono font-bold text-white">
                {applyAllStrategies ? 'YES (ALL)' : 'SELECTED ONLY'}
              </span>
              <button
                type="button"
                onClick={() => setApplyAllStrategies(!applyAllStrategies)}
                className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                  applyAllStrategies ? 'bg-blue-600' : 'bg-gray-700'
                }`}
              >
                <span
                  className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                    applyAllStrategies ? 'translate-x-5' : 'translate-x-0'
                  }`}
                />
              </button>
            </div>
          </div>

          {/* Toggle: Close profitable positions */}
          <div className="bg-surface/50 border border-border rounded-xl p-4 flex flex-col justify-between space-y-3">
            <div>
              <span className="text-xs font-mono font-bold text-gray-300 block">
                Close Profitable Positions
              </span>
              <p className="text-[11px] text-gray-500 font-mono mt-1">
                Square off positions currently in profit at cutoff time (lock in simulated gains).
              </p>
            </div>
            <div className="flex items-center justify-between pt-2 border-t border-border/40">
              <span className="text-xs font-mono font-bold text-emerald-400">
                {closeProfitable ? 'ON (CLOSE)' : 'OFF (HOLD)'}
              </span>
              <button
                type="button"
                onClick={() => setCloseProfitable(!closeProfitable)}
                className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                  closeProfitable ? 'bg-emerald-600' : 'bg-gray-700'
                }`}
              >
                <span
                  className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                    closeProfitable ? 'translate-x-5' : 'translate-x-0'
                  }`}
                />
              </button>
            </div>
          </div>

          {/* Toggle: Close losing positions */}
          <div className="bg-surface/50 border border-border rounded-xl p-4 flex flex-col justify-between space-y-3">
            <div>
              <span className="text-xs font-mono font-bold text-gray-300 block">
                Close Losing Positions
              </span>
              <p className="text-[11px] text-gray-500 font-mono mt-1">
                Square off positions currently in loss at cutoff time (prevent overnight gap risk).
              </p>
            </div>
            <div className="flex items-center justify-between pt-2 border-t border-border/40">
              <span className="text-xs font-mono font-bold text-rose-400">
                {closeLosing ? 'ON (CLOSE)' : 'OFF (HOLD)'}
              </span>
              <button
                type="button"
                onClick={() => setCloseLosing(!closeLosing)}
                className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                  closeLosing ? 'bg-rose-600' : 'bg-gray-700'
                }`}
              >
                <span
                  className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                    closeLosing ? 'translate-x-5' : 'translate-x-0'
                  }`}
                />
              </button>
            </div>
          </div>

          {/* Live Scheduler Telemetry Card */}
          <div className="bg-gradient-to-br from-amber-950/30 to-purple-950/20 border border-amber-500/30 rounded-xl p-4 space-y-2.5 font-mono text-xs">
            <div className="flex items-center justify-between text-amber-400 font-bold">
              <span className="flex items-center gap-1.5">
                <Timer className="w-3.5 h-3.5" />
                Scheduler Status
              </span>
              <span className="text-[10px] bg-amber-500/20 px-2 py-0.5 rounded text-amber-300">
                Live Watcher
              </span>
            </div>

            <div className="space-y-1.5">
              <div className="flex justify-between text-gray-300">
                <span>Cutoff Time:</span>
                <span className="font-bold text-white">{autoCloseTime} IST</span>
              </div>
              <div className="flex justify-between text-gray-300">
                <span>Time Remaining:</span>
                <span className="font-bold text-amber-300">{timeRemainingDisplay}</span>
              </div>
              <div className="border-t border-amber-500/20 pt-1.5 text-gray-300">
                <span className="block text-gray-500 text-[10px] uppercase">Last Status:</span>
                <span className="font-semibold text-[11px] text-white break-words">{autoExitStatus}</span>
              </div>
            </div>
          </div>
        </div>

        {/* Rule verification notice */}
        <div className="p-3.5 rounded-lg bg-surface border border-border/80 flex items-start gap-3 text-xs">
          <Info className="w-4 h-4 text-blue-400 shrink-0 mt-0.5" />
          <div className="space-y-1 text-gray-300">
            <span className="font-semibold text-white">Execution Guarantee</span>
            <p className="text-[11px] text-gray-400">
              Auto exit records exit reason as <code className="text-white font-mono">AUTO_CLOSE_3_20_PM</code>. Orders already closed earlier by target, stop-loss, or opposite signals are never duplicated. If market feeds disconnect, positions are flagged awaiting valid quotes rather than fabricating synthetic prices.
            </p>
          </div>
        </div>
      </div>

      {/* Demo & Test Data Management */}
      <div className="bg-card border border-border rounded-xl p-5 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="font-bold text-white text-sm flex items-center gap-2">
              <Trash2 className="w-4 h-4 text-rose-400" />
              Demo Data &amp; Database Management
            </h3>
            <p className="text-xs text-gray-400 font-mono mt-0.5">
              Permanently wipe all demo paper trades, orders, positions, signals, and test events.
            </p>
          </div>

          <button
            onClick={async () => {
              if (window.confirm('Reset all demo data? This will clear all trades, orders, signals, and backtest history and restore cash to ₹1,00,000.')) {
                try {
                  await api.resetPaperData();
                  if (onResetPaper) onResetPaper();
                  const updatedEvents = await api.getSystemEvents(20);
                  setEvents(updatedEvents);
                } catch (e) {
                  console.error(e);
                }
              }
            }}
            className="px-4 py-2 rounded-lg bg-rose-600 hover:bg-rose-500 text-white text-xs font-mono font-semibold transition-colors flex items-center gap-2"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            Clear All Demo Data &amp; Reset System
          </button>
        </div>
      </div>

      {/* System Audit Events Table */}
      <div className="bg-card border border-border rounded-xl p-5">
        <h3 className="font-bold text-white text-sm mb-3">System Events &amp; Reconnection Audit</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-xs font-mono text-left min-w-[540px]">
            <thead>
              <tr className="bg-surface/60 border-b border-border text-gray-400 uppercase text-[11px] whitespace-nowrap">
                <th className="px-3 py-2">ID</th>
                <th className="px-3 py-2">Timestamp (IST)</th>
                <th className="px-3 py-2">Event Type</th>
                <th className="px-3 py-2">Title</th>
                <th className="px-3 py-2">Message</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/40">
              {events.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-6 text-center text-gray-500 whitespace-normal">
                    No system alert events recorded. System running smoothly.
                  </td>
                </tr>
              ) : (
                events.map((e) => (
                  <tr key={e.id} className="hover:bg-surface/40">
                    <td className="px-3 py-2 text-gray-400 font-bold whitespace-nowrap">#{e.id}</td>
                    <td className="px-3 py-2 text-gray-400 whitespace-nowrap">{formatIST(e.created_at)}</td>
                    <td className="px-3 py-2 whitespace-nowrap">
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-surface border border-border">
                        {e.event_type}
                      </span>
                    </td>
                    <td className="px-3 py-2 font-bold text-white whitespace-nowrap">{e.title}</td>
                    <td className="px-3 py-2 text-gray-300 min-w-[200px]">{e.message}</td>
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
