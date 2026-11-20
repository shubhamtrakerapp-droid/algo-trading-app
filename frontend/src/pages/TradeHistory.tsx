import React, { useEffect, useState } from 'react';
import { History, Download, RefreshCw, Trash2 } from 'lucide-react';
import { PaperTrade } from '../types';
import { api } from '../services/api';
import { formatCurrency, formatIST, formatISTDate, getPnlColor } from '../utils/formatters';

interface TradeHistoryProps {
  onResetPaper?: () => void;
}

export const TradeHistory: React.FC<TradeHistoryProps> = ({ onResetPaper }) => {
  const [trades, setTrades] = useState<PaperTrade[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    loadTrades();
  }, []);

  const loadTrades = async () => {
    setLoading(true);
    try {
      const data = await api.getPaperTrades(100);
      setTrades(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const getExitReasonBadge = (reason: string) => {
    switch (reason) {
      case 'TARGET':
        return 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30';
      case 'STOP_LOSS':
        return 'bg-rose-500/20 text-rose-400 border-rose-500/30';
      case 'GAP_STOP':
        return 'bg-red-950 text-red-400 border-red-800';
      case 'FORCE_EXIT_1520':
      case 'AUTO_CLOSE_3_20_PM':
        return 'bg-amber-500/20 text-amber-400 border-amber-500/30';
      default:
        return 'bg-gray-800 text-gray-400 border-gray-700';
    }
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="bg-card border border-border rounded-xl p-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center space-x-3">
          <div className="p-2 rounded-lg bg-blue-600/10 text-blue-400 border border-blue-500/20">
            <History className="w-5 h-5" />
          </div>
          <div>
            <h2 className="font-bold text-white text-base">Paper Trade Execution Audit</h2>
            <p className="text-xs text-gray-400 font-mono">
              Complete trade-by-trade simulated logs persisted in database
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <a
            href={api.getPaperTradesCsvUrl()}
            download="nextrade_paper_trades.csv"
            className={`px-3 py-1.5 rounded-lg bg-surface border border-border text-xs font-mono text-gray-300 hover:text-white transition-colors flex items-center gap-1.5 ${
              trades.length === 0 ? 'pointer-events-none opacity-40' : ''
            }`}
          >
            <Download className="w-3.5 h-3.5 text-blue-400" />
            Export CSV
          </a>

          <button
            onClick={loadTrades}
            disabled={loading}
            className="px-3 py-1.5 rounded-lg bg-surface border border-border text-xs font-mono text-gray-300 hover:text-white transition-colors flex items-center gap-1.5"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>

          <button
            onClick={async () => {
              if (window.confirm('Clear all demo trade records from database and reset virtual capital?')) {
                setLoading(true);
                try {
                  await api.resetPaperData();
                  if (onResetPaper) onResetPaper();
                  await loadTrades();
                } catch (e) {
                  console.error(e);
                } finally {
                  setLoading(false);
                }
              }
            }}
            disabled={loading || trades.length === 0}
            className="px-3 py-1.5 rounded-lg bg-surface border border-rose-500/40 text-rose-400 hover:bg-rose-500/10 disabled:opacity-40 disabled:hover:bg-surface text-xs font-mono font-semibold transition-colors flex items-center gap-1.5"
            title="Clear all demo trades"
          >
            <Trash2 className="w-3.5 h-3.5" />
            Clear Demo Trades
          </button>
        </div>
      </div>

      {/* Trades: Desktop Table View + Mobile Card View */}
      <div className="bg-card border border-border rounded-xl overflow-hidden">
        {/* Desktop Table (Visible on md and larger) */}
        <div className="hidden md:block overflow-x-auto">
          <table className="w-full text-xs font-mono text-left">
            <thead>
              <tr className="bg-surface/60 border-b border-border text-gray-400 uppercase text-[11px]">
                <th className="px-3 py-2.5">ID</th>
                <th className="px-3 py-2.5">Date</th>
                <th className="px-3 py-2.5">Contract</th>
                <th className="px-3 py-2.5">Entry (IST)</th>
                <th className="px-3 py-2.5">Exit (IST)</th>
                <th className="px-3 py-2.5 text-right">Entry (₹)</th>
                <th className="px-3 py-2.5 text-right">Exit (₹)</th>
                <th className="px-3 py-2.5 text-right">Qty</th>
                <th className="px-3 py-2.5">Exit Reason</th>
                <th className="px-3 py-2.5 text-right">Gross (₹)</th>
                <th className="px-3 py-2.5 text-right">Charges</th>
                <th className="px-3 py-2.5 text-right">Net P&amp;L</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/40">
              {trades.length === 0 ? (
                <tr>
                  <td colSpan={12} className="px-4 py-8 text-center text-gray-500">
                    No closed paper trades yet.
                  </td>
                </tr>
              ) : (
                trades.map((t) => (
                  <tr key={t.id} className="hover:bg-surface/40 transition-colors">
                    <td className="px-3 py-2.5 text-gray-400 font-bold">#{t.id}</td>
                    <td className="px-3 py-2.5 text-gray-400">{formatISTDate(t.entry_time)}</td>
                    <td className="px-3 py-2.5 font-bold text-white">{t.option_symbol}</td>
                    <td className="px-3 py-2.5 text-gray-300">{formatIST(t.entry_time)}</td>
                    <td className="px-3 py-2.5 text-gray-300">{formatIST(t.exit_time)}</td>
                    <td className="px-3 py-2.5 text-right font-semibold text-white">₹{t.entry_price.toFixed(2)}</td>
                    <td className="px-3 py-2.5 text-right font-semibold text-blue-400">₹{t.exit_price.toFixed(2)}</td>
                    <td className="px-3 py-2.5 text-right text-gray-300">{t.quantity}</td>
                    <td className="px-3 py-2.5">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold border ${getExitReasonBadge(t.exit_reason)}`}>
                        {t.exit_reason}
                      </span>
                    </td>
                    <td className={`px-3 py-2.5 text-right font-semibold ${getPnlColor(t.gross_pnl)}`}>
                      {formatCurrency(t.gross_pnl)}
                    </td>
                    <td className="px-3 py-2.5 text-right font-mono text-gray-300">
                      <div>₹{t.total_charges.toFixed(2)}</div>
                      <div className="text-[10px] text-gray-500">
                        ₹{t.entry_charge ?? 10} + ₹{t.exit_charge ?? 10}
                      </div>
                    </td>
                    <td className={`px-3 py-2.5 text-right font-bold ${getPnlColor(t.net_pnl)}`}>
                      {formatCurrency(t.net_pnl)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Mobile Touch Cards View (Visible on screens smaller than md) */}
        <div className="md:hidden divide-y divide-border/40 font-mono text-xs">
          {trades.length === 0 ? (
            <div className="px-4 py-8 text-center text-gray-500">
              No closed paper trades yet.
            </div>
          ) : (
            trades.map((t) => (
              <div key={t.id} className="p-3.5 space-y-2.5 hover:bg-surface/30 transition-colors">
                {/* Header: ID, Date, Contract & Net P&L */}
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className="text-gray-400 font-bold">#{t.id}</span>
                      <span className="text-white font-bold truncate">{t.option_symbol}</span>
                    </div>
                    <span className="text-[10px] text-gray-500">{formatISTDate(t.entry_time)}</span>
                  </div>
                  <div className="text-right shrink-0">
                    <span className={`text-sm font-bold block ${getPnlColor(t.net_pnl)}`}>
                      {formatCurrency(t.net_pnl)}
                    </span>
                    <span className={`px-1.5 py-0.2 rounded text-[9px] font-bold border ${getExitReasonBadge(t.exit_reason)}`}>
                      {t.exit_reason}
                    </span>
                  </div>
                </div>

                {/* Grid Details */}
                <div className="grid grid-cols-2 gap-2 text-[11px] bg-surface/50 rounded-lg p-2.5 border border-border/50">
                  <div>
                    <span className="text-gray-500 block text-[10px]">ENTRY</span>
                    <span className="text-white font-semibold">₹{t.entry_price.toFixed(2)}</span>
                    <span className="text-gray-400 block text-[10px]">{formatIST(t.entry_time)}</span>
                  </div>
                  <div>
                    <span className="text-gray-500 block text-[10px]">EXIT</span>
                    <span className="text-blue-400 font-semibold">₹{t.exit_price.toFixed(2)}</span>
                    <span className="text-gray-400 block text-[10px]">{formatIST(t.exit_time)}</span>
                  </div>
                  <div>
                    <span className="text-gray-500 block text-[10px]">QTY / CHARGES</span>
                    <span className="text-gray-200">{t.quantity} qty</span>
                    <span className="text-gray-400 block text-[10px]">Charges: ₹{t.total_charges.toFixed(2)}</span>
                  </div>
                  <div>
                    <span className="text-gray-500 block text-[10px]">GROSS P&amp;L</span>
                    <span className={`font-semibold ${getPnlColor(t.gross_pnl)}`}>
                      {formatCurrency(t.gross_pnl)}
                    </span>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};
