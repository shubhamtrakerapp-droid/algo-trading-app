import React, { useState } from 'react';
import { DollarSign, ShieldAlert, Play, Square, AlertCircle, ArrowUpRight, RotateCcw } from 'lucide-react';
import { PaperAccountStatus, MarketStatus } from '../types';
import { formatCurrency, getPnlColor } from '../utils/formatters';

interface PaperTradingProps {
  paperStatus: PaperAccountStatus | null;
  marketStatus: MarketStatus | null;
  onOpenTrade: () => void;
  onCloseTrade: () => void;
  onResetPaper?: () => void;
}

export const PaperTrading: React.FC<PaperTradingProps> = ({
  paperStatus,
  marketStatus,
  onOpenTrade,
  onCloseTrade,
  onResetPaper,
}) => {
  const [lots, setLots] = useState(1);
  const activePos = paperStatus?.active_position;
  const lotSize = marketStatus?.lot_size || 65;
  const qty = lots * lotSize;
  const maxLossPoints = (1000.0 / Math.max(1, qty)).toFixed(2);
  const effectiveStop = Math.min(4.0, parseFloat(maxLossPoints)).toFixed(2);

  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="bg-card border border-border rounded-xl p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center space-x-3">
          <div className="p-2.5 rounded-xl bg-amber-500/10 text-amber-400 border border-amber-500/30">
            <DollarSign className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-white">Paper Trading Execution Engine</h2>
            <p className="text-xs text-gray-400 font-mono">
              Independent Virtual Broker | Automated execution against option premium | Max Loss ₹1,000 / trade
            </p>
          </div>
        </div>

        {onResetPaper && (
          <button
            onClick={() => {
              if (window.confirm('Are you sure you want to clear all paper trades and reset virtual account to ₹1,00,000?')) {
                onResetPaper();
              }
            }}
            className="px-3 py-1.5 rounded-lg bg-surface border border-rose-500/40 text-rose-400 hover:bg-rose-500/10 text-xs font-mono font-semibold transition-colors flex items-center gap-1.5"
            title="Clear all demo trades and reset virtual capital to ₹1,00,000"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            Reset Account &amp; Clear Demo Data
          </button>
        )}
      </div>

      {/* Account Balances Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-card border border-border rounded-xl p-4">
          <span className="text-xs text-gray-400 font-mono">VIRTUAL STARTING CAPITAL</span>
          <div className="text-xl font-bold font-mono text-white mt-1">
            {formatCurrency(paperStatus?.initial_capital || 100000)}
          </div>
          <span className="text-[11px] text-gray-500 mt-1 block font-mono">Fixed allocation</span>
        </div>

        <div className="bg-card border border-border rounded-xl p-4">
          <span className="text-xs text-gray-400 font-mono">CASH BALANCE</span>
          <div className="text-xl font-bold font-mono text-blue-400 mt-1">
            {formatCurrency(paperStatus?.cash_balance || 100000)}
          </div>
          <span className="text-[11px] text-gray-500 mt-1 block font-mono">Available virtual margin</span>
        </div>

        <div className="bg-card border border-border rounded-xl p-4">
          <span className="text-xs text-gray-400 font-mono">REALIZED NET P&amp;L</span>
          <div className={`text-xl font-bold font-mono mt-1 ${getPnlColor(paperStatus?.realized_pnl || 0)}`}>
            {formatCurrency(paperStatus?.realized_pnl || 0)}
          </div>
          <span className="text-[11px] text-gray-500 mt-1 block font-mono">After flat order charges</span>
        </div>

        <div className="bg-card border border-border rounded-xl p-4">
          <span className="text-xs text-gray-400 font-mono">PORTFOLIO VALUATION</span>
          <div className="text-xl font-bold font-mono text-white mt-1">
            {formatCurrency(paperStatus?.portfolio_value || 100000)}
          </div>
          <span className="text-[11px] text-gray-500 mt-1 block font-mono">
            Unrealized: {formatCurrency(paperStatus?.unrealized_pnl || 0)}
          </span>
        </div>
      </div>

      {/* Execution Rules & Risk Matrix */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Risk Rules Specification */}
        <div className="lg:col-span-2 bg-card border border-border rounded-xl p-5 space-y-4">
          <h3 className="font-bold text-white text-sm">Execution Engine Risk Rules</h3>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs font-mono">
            <div className="p-3 bg-surface rounded-lg border border-border">
              <span className="text-gray-400">Target Points:</span>
              <div className="text-sm font-bold text-emerald-400 mt-1">+4.00 Option Premium Points</div>
              <p className="text-[11px] text-gray-500 mt-0.5">Target = Entry Price + 4.0</p>
            </div>

            <div className="p-3 bg-surface rounded-lg border border-border">
              <span className="text-gray-400">Original Stop Loss:</span>
              <div className="text-sm font-bold text-rose-400 mt-1">-4.00 Option Premium Points</div>
              <p className="text-[11px] text-gray-500 mt-0.5">Subject to ₹1,000 maximum loss cap</p>
            </div>

            <div className="p-3 bg-surface rounded-lg border border-border">
              <span className="text-gray-400">Maximum Loss / Trade:</span>
              <div className="text-sm font-bold text-amber-400 mt-1">₹1,000.00 Fixed Maximum</div>
              <p className="text-[11px] text-gray-500 mt-0.5">Max Loss Points = ₹1,000 / Quantity</p>
            </div>

            <div className="p-3 bg-surface rounded-lg border border-border">
              <span className="text-gray-400">Force Exit Cutoff:</span>
              <div className="text-sm font-bold text-white mt-1">15:20 IST Mandatory</div>
              <p className="text-[11px] text-gray-500 mt-0.5">No positions held overnight</p>
            </div>
          </div>

          <div className="p-3 rounded-lg bg-blue-950/20 border border-blue-800/40 text-xs font-mono space-y-1">
            <div className="font-bold text-blue-300">Effective Stop Distance Formula:</div>
            <div className="text-gray-300">
              Quantity = {lots} Lot(s) &times; {lotSize} = <span className="text-white font-bold">{qty}</span>
            </div>
            <div className="text-gray-300">
              Max Loss Distance = ₹1,000 / {qty} = <span className="text-white font-bold">{maxLossPoints} pts</span>
            </div>
            <div className="text-emerald-400 font-bold">
              Active Stop Distance = min(4.0, {maxLossPoints}) = {effectiveStop} points
            </div>
          </div>
        </div>

        {/* Paper Trade Controls */}
        <div className="bg-card border border-border rounded-xl p-5 flex flex-col justify-between space-y-4">
          <div>
            <h3 className="font-bold text-white text-sm mb-3">Simulated Trade Controls</h3>

            <div className="space-y-3 text-xs font-mono">
              <div>
                <label className="text-gray-400 block mb-1">Contract Lots:</label>
                <div className="flex items-center space-x-2">
                  {[1, 2, 3, 5].map((l) => (
                    <button
                      key={l}
                      onClick={() => setLots(l)}
                      className={`flex-1 py-1.5 rounded border text-center font-bold ${
                        lots === l
                          ? 'bg-blue-600 text-white border-blue-500'
                          : 'bg-surface text-gray-400 border-border hover:text-white'
                      }`}
                    >
                      {l} Lot ({l * lotSize})
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <span className="text-gray-400">Selected Instrument:</span>
                <div className="text-white font-bold mt-0.5">{marketStatus?.option_symbol || 'NIFTY ATM CE'}</div>
                <div className="text-gray-500 text-[11px]">Premium: ₹{marketStatus?.option_premium.toFixed(2) || '145.00'}</div>
              </div>
            </div>
          </div>

          <div className="pt-4 border-t border-border space-y-2">
            {activePos ? (
              <button
                onClick={onCloseTrade}
                className="w-full py-2.5 px-4 rounded-lg bg-rose-600 hover:bg-rose-500 text-white font-semibold text-xs transition-colors flex items-center justify-center gap-2"
              >
                <Square className="w-4 h-4 fill-white" />
                Square Off Active Paper Position
              </button>
            ) : (
              <button
                onClick={onOpenTrade}
                className="w-full py-2.5 px-4 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs transition-colors flex items-center justify-center gap-2"
              >
                <Play className="w-4 h-4 fill-white" />
                Place Simulated BUY Order ({lots} Lot)
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
