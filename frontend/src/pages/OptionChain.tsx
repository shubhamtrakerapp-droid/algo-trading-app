import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Layers, Calendar, Check, AlertCircle, RefreshCw, Wifi, WifiOff, Clock } from 'lucide-react';
import { OptionChainResponse, OptionStrike } from '../types';
import { api } from '../services/api';
import { wsClient, ConnectionState } from '../services/websocket';

interface OptionChainProps {
  onContractSelected?: () => void;
}

export const OptionChain: React.FC<OptionChainProps> = ({ onContractSelected }) => {
  const [chain, setChain] = useState<OptionChainResponse | null>(null);
  const [expiries, setExpiries] = useState<string[]>([]);
  const [selectedExpiry, setSelectedExpiry] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [connectionState, setConnectionState] = useState<ConnectionState>('CONNECTING');
  const [lastTickTime, setLastTickTime] = useState<Date | null>(null);
  const [dataAge, setDataAge] = useState<string>('Connecting...');
  const [flashStrikes, setFlashStrikes] = useState<Record<string, 'up' | 'down'>>({});

  const loadData = useCallback(async (silent = false) => {
    try {
      if (!silent) setLoading(true);
      const [chainRes, expRes] = await Promise.all([api.getOptionChain(), api.getExpiries()]);
      setChain(chainRes);
      setExpiries(expRes.expiries);
      if (expRes.expiries.length > 0 && !selectedExpiry) {
        setSelectedExpiry(expRes.expiries[0]);
      }
      setLastTickTime(new Date());
    } catch (e: any) {
      console.error('Failed to load option chain:', e);
    } finally {
      if (!silent) setLoading(false);
    }
  }, [selectedExpiry]);

  useEffect(() => {
    loadData();
    const interval = setInterval(() => {
      loadData(true);
    }, 60000); // 1-minute live fetcher
    return () => clearInterval(interval);
  }, [loadData]);

  // Real-time WebSocket listener
  useEffect(() => {
    // Sync initial state
    const health = wsClient.getConnectionHealth();
    setConnectionState(health.state);
    if (health.lastTickTime) setLastTickTime(health.lastTickTime);

    const unsubStatus = wsClient.onStatusChange((status) => {
      setConnectionState(status);
    });

    const unsubMessages = wsClient.subscribe((msg: any) => {
      if (!msg || !msg.type) return;

      // 1. Spot price update
      if (msg.type === 'OPTION_CHAIN_SPOT') {
        const spot = parseFloat(msg.data.spot_price);
        const atm = parseFloat(msg.data.atm_strike) || Math.round(spot / 50) * 50;
        setLastTickTime(new Date());

        setChain((prev) => {
          if (!prev) return prev;
          return {
            ...prev,
            spot_price: spot,
            atm_strike: atm,
            strikes: prev.strikes.map((s) => ({
              ...s,
              is_atm: Math.abs(s.strike - atm) < 25,
            })),
          };
        });
      }

      // 2. Option Strike Tick (CE or PE)
      else if (msg.type === 'OPTION_CHAIN_TICK' || (msg.type === 'TICK' && !msg.data?.is_index)) {
        const tick = msg.data;
        if (!tick || !tick.symbol) return;
        setLastTickTime(new Date());

        const sym = tick.symbol.toUpperCase();
        const m = sym.match(/(\d{4,5})\s*(CE|PE)/);
        if (!m) return;

        const strikeVal = parseFloat(m[1]);
        const optType = m[2]; // 'CE' or 'PE'
        const flashKey = `${strikeVal}_${optType}`;

        setChain((prev) => {
          if (!prev) return prev;
          let changed = false;
          const updatedStrikes = prev.strikes.map((row) => {
            if (row.strike === strikeVal) {
              changed = true;
              if (optType === 'CE') {
                const prevPrice = row.ce_ltp;
                const newPrice = tick.price;
                const dir = newPrice >= prevPrice ? 'up' : 'down';
                setFlashStrikes((f) => ({ ...f, [flashKey]: dir }));
                setTimeout(() => {
                  setFlashStrikes((f) => {
                    const copy = { ...f };
                    delete copy[flashKey];
                    return copy;
                  });
                }, 800);

                return {
                  ...row,
                  ce_ltp: newPrice,
                  ce_volume: tick.volume || row.ce_volume,
                  ce_oi: tick.open_interest || row.ce_oi,
                };
              } else {
                const prevPrice = row.pe_ltp;
                const newPrice = tick.price;
                const dir = newPrice >= prevPrice ? 'up' : 'down';
                setFlashStrikes((f) => ({ ...f, [flashKey]: dir }));
                setTimeout(() => {
                  setFlashStrikes((f) => {
                    const copy = { ...f };
                    delete copy[flashKey];
                    return copy;
                  });
                }, 800);

                return {
                  ...row,
                  pe_ltp: newPrice,
                  pe_volume: tick.volume || row.pe_volume,
                  pe_oi: tick.open_interest || row.pe_oi,
                };
              }
            }
            return row;
          });

          return changed ? { ...prev, strikes: updatedStrikes } : prev;
        });
      }
    });

    return () => {
      unsubStatus();
      unsubMessages();
    };
  }, []);

  // Update data freshness counter every second
  useEffect(() => {
    const timer = setInterval(() => {
      if (!lastTickTime) {
        setDataAge('Awaiting feed...');
      } else {
        const diff = Math.max(0, (Date.now() - lastTickTime.getTime()) / 1000);
        if (diff < 1.5) {
          setDataAge('Live streaming');
        } else if (diff < 60) {
          setDataAge(`${diff.toFixed(1)}s ago`);
        } else {
          setDataAge(`${Math.floor(diff / 60)}m ago`);
        }
      }
    }, 1000);
    return () => clearInterval(timer);
  }, [lastTickTime]);

  const handleSelectStrike = async (strike: number) => {
    try {
      await api.selectContract(strike, selectedExpiry);
      setActionMsg(`Selected Strike ${strike} CE as active ATM contract.`);
      setTimeout(() => setActionMsg(null), 3000);
      if (onContractSelected) onContractSelected();
    } catch (e: any) {
      setActionMsg(e.message || 'Error selecting contract');
      setTimeout(() => setActionMsg(null), 4000);
    }
  };

  const getStatusBadge = () => {
    switch (connectionState) {
      case 'CONNECTED':
        return (
          <span className="px-2 py-0.5 rounded text-[11px] font-mono font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            LIVE FEED
          </span>
        );
      case 'CONNECTING':
      case 'RECONNECTING':
        return (
          <span className="px-2 py-0.5 rounded text-[11px] font-mono font-bold bg-amber-500/10 text-amber-400 border border-amber-500/30 flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-ping" />
            {connectionState}
          </span>
        );
      case 'STALE DATA':
        return (
          <span className="px-2 py-0.5 rounded text-[11px] font-mono font-bold bg-orange-500/10 text-orange-400 border border-orange-500/30 flex items-center gap-1">
            <AlertCircle className="w-3 h-3 text-orange-400" />
            STALE DATA
          </span>
        );
      case 'MARKET CLOSED':
        return (
          <span className="px-2 py-0.5 rounded text-[11px] font-mono font-bold bg-blue-500/10 text-blue-400 border border-blue-500/30 flex items-center gap-1">
            <Clock className="w-3 h-3" />
            MARKET CLOSED
          </span>
        );
      default:
        return (
          <span className="px-2 py-0.5 rounded text-[11px] font-mono font-bold bg-rose-500/10 text-rose-400 border border-rose-500/30 flex items-center gap-1">
            <WifiOff className="w-3 h-3" />
            DISCONNECTED
          </span>
        );
    }
  };

  return (
    <div className="space-y-4">
      {/* Top Controls Bar */}
      <div className="bg-card border border-border rounded-xl p-4 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center space-x-3">
          <div className="p-2 rounded-lg bg-blue-600/10 text-blue-400 border border-blue-500/20">
            <Layers className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="font-bold text-white text-base">NIFTY Option Chain</h2>
              {getStatusBadge()}
            </div>
            <p className="text-xs text-gray-400 font-mono mt-0.5">
              Underlying Spot:{' '}
              <span className="text-white font-bold transition-colors">
                {chain?.spot_price ? chain.spot_price.toFixed(2) : '24,500.00'}
              </span>{' '}
              | Dynamic ATM:{' '}
              <span className="text-emerald-400 font-bold">{chain?.atm_strike || 24500}</span>
              <span className="ml-2 text-gray-500">({dataAge})</span>
            </p>
          </div>
        </div>

        {/* Right Controls: Expiry & Manual Refresh */}
        <div className="flex items-center space-x-3 text-xs font-mono">
          <div className="flex items-center space-x-2">
            <Calendar className="w-4 h-4 text-gray-400" />
            <span className="text-gray-400">Expiry:</span>
            <select
              value={selectedExpiry}
              onChange={(e) => setSelectedExpiry(e.target.value)}
              className="bg-surface border border-border rounded-lg px-3 py-1.5 text-white font-mono focus:outline-none focus:border-blue-500"
            >
              {expiries.map((exp) => (
                <option key={exp} value={exp}>
                  {exp}
                </option>
              ))}
            </select>
          </div>

          <button
            onClick={() => loadData(false)}
            disabled={loading}
            title="Force refresh option chain"
            className="p-2 rounded-lg bg-surface border border-border hover:bg-surface/80 text-gray-300 hover:text-white transition-all disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin text-blue-400' : ''}`} />
          </button>
        </div>
      </div>

      {actionMsg && (
        <div className="p-3 rounded-lg bg-blue-950/40 border border-blue-800 text-blue-300 text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4" />
          <span>{actionMsg}</span>
        </div>
      )}

      {/* Option Chain Table */}
      <div className="bg-card border border-border rounded-xl overflow-hidden shadow-sm">
        <div className="overflow-x-auto pb-2">
          <table className="w-full min-w-[620px] text-xs font-mono text-left">
            <thead>
              <tr className="bg-surface/80 border-b border-border text-gray-400 uppercase tracking-wider text-[11px]">
                <th colSpan={3} className="px-4 py-2.5 text-center border-r border-border text-blue-400">
                  CALL OPTIONS (CE)
                </th>
                <th className="px-4 py-2.5 text-center bg-surface font-bold text-white">STRIKE</th>
                <th colSpan={3} className="px-4 py-2.5 text-center border-l border-border text-rose-400">
                  PUT OPTIONS (PE)
                </th>
              </tr>
              <tr className="bg-surface/40 border-b border-border text-gray-400 text-[10px]">
                <th className="px-4 py-2 text-right">OI</th>
                <th className="px-4 py-2 text-right">VOLUME</th>
                <th className="px-4 py-2 text-right border-r border-border text-blue-300">LTP (₹)</th>
                <th className="px-4 py-2 text-center bg-surface font-bold">PRICE</th>
                <th className="px-4 py-2 text-left border-l border-border text-rose-300">LTP (₹)</th>
                <th className="px-4 py-2 text-left">VOLUME</th>
                <th className="px-4 py-2 text-left">OI</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/50">
              {chain?.strikes.map((s) => {
                const isAtm = s.is_atm;
                const ceFlash = flashStrikes[`${s.strike}_CE`];
                const peFlash = flashStrikes[`${s.strike}_PE`];

                return (
                  <tr
                    key={s.strike}
                    className={`hover:bg-surface/40 transition-colors ${
                      isAtm ? 'bg-blue-950/30 font-semibold' : ''
                    }`}
                  >
                    {/* CE Side */}
                    <td className="px-4 py-2 text-right text-gray-400">{s.ce_oi.toLocaleString()}</td>
                    <td className="px-4 py-2 text-right text-gray-400">{s.ce_volume.toLocaleString()}</td>
                    <td
                      className={`px-4 py-2 text-right font-bold text-blue-400 border-r border-border transition-colors duration-300 ${
                        ceFlash === 'up'
                          ? 'bg-emerald-500/20 text-emerald-300'
                          : ceFlash === 'down'
                          ? 'bg-rose-500/20 text-rose-300'
                          : ''
                      }`}
                    >
                      <button
                        onClick={() => handleSelectStrike(s.strike)}
                        title="Click to select this CE contract"
                        className="hover:underline cursor-pointer"
                      >
                        ₹{s.ce_ltp.toFixed(2)}
                      </button>
                    </td>

                    {/* Strike Center */}
                    <td className="px-4 py-2 text-center bg-surface/60 font-bold text-white relative">
                      {s.strike}
                      {isAtm && (
                        <span className="ml-2 text-[9px] px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/40">
                          ATM
                        </span>
                      )}
                    </td>

                    {/* PE Side */}
                    <td
                      className={`px-4 py-2 text-left font-bold text-rose-400 border-l border-border transition-colors duration-300 ${
                        peFlash === 'up'
                          ? 'bg-emerald-500/20 text-emerald-300'
                          : peFlash === 'down'
                          ? 'bg-rose-500/20 text-rose-300'
                          : ''
                      }`}
                    >
                      ₹{s.pe_ltp.toFixed(2)}
                    </td>
                    <td className="px-4 py-2 text-left text-gray-400">{s.pe_volume.toLocaleString()}</td>
                    <td className="px-4 py-2 text-left text-gray-400">{s.pe_oi.toLocaleString()}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
