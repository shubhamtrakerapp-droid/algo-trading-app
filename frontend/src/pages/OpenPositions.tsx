import React from 'react';
import { TrendingUp, AlertCircle, Square, CheckCircle2 } from 'lucide-react';
import { PaperPosition } from '../types';
import { formatCurrency, formatIST, getPnlColor, getPnlBg } from '../utils/formatters';

interface OpenPositionsProps {
  position: PaperPosition | null;
  onClosePosition: () => void;
}

export const OpenPositions: React.FC<OpenPositionsProps> = ({ position, onClosePosition }) => {
  if (!position) {
    return (
      <div className="bg-card border border-border rounded-xl p-12 text-center space-y-3">
        <div className="w-12 h-12 rounded-full bg-surface border border-border mx-auto flex items-center justify-center text-gray-500">
          <TrendingUp className="w-6 h-6" />
        </div>
        <h3 className="text-base font-bold text-white">No Open Positions</h3>
        <p className="text-xs text-gray-400 max-w-sm mx-auto font-mono">
          There are currently no active virtual paper trading positions. The algorithm will automatically enter when all 4
          strategy conditions are met on a completed 1-minute candle.
        </p>
      </div>
    );
  }

  const isProfit = position.net_pnl >= 0;

  return (
    <div className="space-y-6">
      {/* Active Position Card */}
      <div className="bg-card border border-border rounded-xl p-6">
        <div className="flex flex-wrap items-center justify-between pb-4 border-b border-border/60 gap-3">
          <div className="flex items-center space-x-3">
            <span className="text-xs font-mono font-bold px-2 py-1 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
              ACTIVE BUY
            </span>
            <h2 className="text-lg font-bold text-white font-mono">{position.symbol}</h2>
          </div>

          <div className="flex items-center space-x-3">
            <div className={`text-xl font-bold font-mono ${getPnlColor(position.net_pnl)}`}>
              {formatCurrency(position.net_pnl)}
            </div>
            <span
              title="Read-Only Mode: Position modifications are disabled in observational mode"
              className="py-1.5 px-3 rounded-lg bg-slate-800 border border-slate-700/60 text-slate-400 font-semibold text-xs flex items-center gap-1.5 cursor-not-allowed"
            >
              <Square className="w-3.5 h-3.5 fill-slate-500" />
              Read-Only Position
            </span>
          </div>
        </div>

        {/* Details Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-4 mt-6 text-xs font-mono">
          <div>
            <span className="text-gray-500 uppercase block mb-1">Entry Premium</span>
            <div className="text-sm font-bold text-white">₹{position.entry_price.toFixed(2)}</div>
            <span className="text-[10px] text-gray-500">Filled with slippage</span>
          </div>

          <div>
            <span className="text-gray-500 uppercase block mb-1">Live Premium</span>
            <div className="text-sm font-bold text-blue-400">₹{position.current_price.toFixed(2)}</div>
            <span className="text-[10px] text-gray-500">
              {(position.current_price - position.entry_price).toFixed(2)} pts
            </span>
          </div>

          <div>
            <span className="text-gray-500 uppercase block mb-1">Target (+4 pts)</span>
            <div className="text-sm font-bold text-emerald-400">₹{position.target_price.toFixed(2)}</div>
            <span className="text-[10px] text-emerald-500/80">Automated exit</span>
          </div>

          <div>
            <span className="text-gray-500 uppercase block mb-1">Stop Loss</span>
            <div className="text-sm font-bold text-rose-400">₹{position.stop_price.toFixed(2)}</div>
            <span className="text-[10px] text-rose-500/80">
              Eff Dist: -{position.effective_stop_distance.toFixed(2)} pts
            </span>
          </div>

          <div>
            <span className="text-gray-500 uppercase block mb-1">Quantity</span>
            <div className="text-sm font-bold text-white">{position.quantity}</div>
            <span className="text-[10px] text-gray-500">
              {position.lots} Lot(s) &times; {position.lot_size}
            </span>
          </div>

          <div>
            <span className="text-gray-500 uppercase block mb-1">Estimated Charges</span>
            <div className="text-sm font-bold text-gray-300">{formatCurrency(position.charges)}</div>
            <span className="text-[10px] text-emerald-400/80">Flat ₹{((position.charges || 20) / 2).toFixed(0)} In + ₹{((position.charges || 20) / 2).toFixed(0)} Out</span>
          </div>
        </div>

        {/* High / Low Bar */}
        <div className="mt-6 pt-4 border-t border-border flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs font-mono text-gray-400">
          <div>
            <span>Entry Time: </span>
            <span className="text-white font-semibold">{formatIST(position.entry_time)} IST</span>
          </div>
          <div className="flex flex-wrap items-center gap-3 sm:space-x-4">
            <span>
              Session High: <strong className="text-emerald-400">₹{position.highest_price.toFixed(2)}</strong>
            </span>
            <span>
              Session Low: <strong className="text-rose-400">₹{position.lowest_price.toFixed(2)}</strong>
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};
