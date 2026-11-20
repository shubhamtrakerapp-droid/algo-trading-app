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

      {/* Trades Table */}
      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
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
      </div>
    </div>
  );
};
