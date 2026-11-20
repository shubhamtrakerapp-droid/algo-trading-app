import React, { useEffect, useState, useRef } from 'react';
import {
  ShieldAlert,
  Wifi,
  WifiOff,
  Clock,
  Zap,
  Menu,
  Activity,
  AlertTriangle,
} from 'lucide-react';
import { MarketStatus, StrategyType } from '../types';
import { formatCurrency, formatIST } from '../utils/formatters';
import { api } from '../services/api';
import { wsClient, ConnectionState } from '../services/websocket';

interface NavbarProps {
  marketStatus: MarketStatus | null;
  onToggleMobileSidebar: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({ marketStatus, onToggleMobileSidebar }) => {
  const [currentTime, setCurrentTime] = useState<string>(formatIST(new Date()));
  const [activeStrategy, setActiveStrategy] = useState<StrategyType>('AI_MICRO_SCALPER_V1');
  const [connectionState, setConnectionState] = useState<ConnectionState>('CONNECTING');
  const [lastTickTime, setLastTickTime] = useState<Date | null>(null);
  const [dataAgeStr, setDataAgeStr] = useState<string>('Live');
  const [subsCount, setSubsCount] = useState<number>(2);

  // Price flash indicators
  const [spotPrice, setSpotPrice] = useState<number>(marketStatus?.nifty_price || 24500.0);
  const [spotFlash, setSpotFlash] = useState<'up' | 'down' | null>(null);
  const [optionPrem, setOptionPrem] = useState<number>(marketStatus?.option_premium || 145.0);
  const [optFlash, setOptFlash] = useState<'up' | 'down' | null>(null);

  const prevSpotRef = useRef<number>(spotPrice);
  const prevOptRef = useRef<number>(optionPrem);

  useEffect(() => {
    const timer = setInterval(() => {
      setCurrentTime(formatIST(new Date()));

      // Update data freshness indicator every second
      const health = wsClient.getConnectionHealth();
      if (health.lastTickTime) {
        const diff = Math.max(0, (Date.now() - health.lastTickTime.getTime()) / 1000);
        if (diff < 1.5) {
          setDataAgeStr('Live');
        } else if (diff < 60) {
          setDataAgeStr(`${diff.toFixed(1)}s ago`);
        } else {
          setDataAgeStr(`${Math.floor(diff / 60)}m ago`);
        }
      }
      setSubsCount(health.subscriptionsCount);
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    api.getStrategyProfiles().then((data) => {
      if (data && data.selected_strategy) {
        setActiveStrategy(data.selected_strategy);
      }
    }).catch(() => {});
  }, []);

  // Sync WebSocket state and real-time tick flash
  useEffect(() => {
    const unsubStatus = wsClient.onStatusChange((status) => {
      setConnectionState(status);
    });

    const unsubMsg = wsClient.subscribe((msg: any) => {
      if (!msg || !msg.type) return;

      if (msg.type === 'TICK' || msg.type === 'OPTION_CHAIN_SPOT') {
        const d = msg.data;
        if (!d) return;
        setLastTickTime(new Date());

        if (d.is_index || msg.type === 'OPTION_CHAIN_SPOT') {
          const price = d.price || d.spot_price;
          if (price && price !== prevSpotRef.current) {
            setSpotFlash(price > prevSpotRef.current ? 'up' : 'down');
            prevSpotRef.current = price;
            setSpotPrice(price);
            setTimeout(() => setSpotFlash(null), 800);
          }
        } else {
          const price = d.price;
          if (price && price !== prevOptRef.current) {
            setOptFlash(price > prevOptRef.current ? 'up' : 'down');
            prevOptRef.current = price;
            setOptionPrem(price);
            setTimeout(() => setOptFlash(null), 800);
          }
        }
      } else if (msg.type === 'INITIAL_SNAPSHOT') {
        if (msg.data?.nifty_price) {
          setSpotPrice(msg.data.nifty_price);
          prevSpotRef.current = msg.data.nifty_price;
        }
        if (msg.data?.option_premium) {
          setOptionPrem(msg.data.option_premium);
          prevOptRef.current = msg.data.option_premium;
        }
        if (msg.data?.connection_state) {
          setConnectionState(msg.data.connection_state);
        }
      }
    });

    return () => {
      unsubStatus();
      unsubMsg();
    };
  }, []);

  // Update fallback from marketStatus prop if newer
  useEffect(() => {
    if (marketStatus?.nifty_price && !lastTickTime) {
      setSpotPrice(marketStatus.nifty_price);
    }
    if (marketStatus?.option_premium && !lastTickTime) {
      setOptionPrem(marketStatus.option_premium);
    }
  }, [marketStatus, lastTickTime]);

  const isDemo = marketStatus?.is_demo ?? true;
  const isMarketOpen = marketStatus?.is_market_open ?? false;
  const sessionStatus = marketStatus?.market_session_status || (isMarketOpen ? 'OPEN' : 'CLOSED');

  const renderHealthBadge = () => {
    switch (connectionState) {
      case 'CONNECTED':
        return (
          <span
            className="flex items-center gap-1.5 font-mono px-2.5 py-1 rounded border bg-emerald-950/60 border-emerald-500/40 text-emerald-300 text-xs font-bold shadow-sm"
            title={`Real-time WebSocket streaming active. Subscriptions: ${subsCount} feeds. Age: ${dataAgeStr}`}
          >
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <span>CONNECTED</span>
            <span className="text-[10px] text-emerald-400/80 font-normal">({dataAgeStr})</span>
          </span>
        );
      case 'CONNECTING':
        return (
          <span
            className="flex items-center gap-1.5 font-mono px-2.5 py-1 rounded border bg-yellow-950/50 border-yellow-500/40 text-yellow-300 text-xs font-bold"
            title="Attempting connection to market data feed"
          >
            <span className="w-2 h-2 rounded-full bg-yellow-400 animate-ping" />
            <span>CONNECTING</span>
          </span>
        );
      case 'RECONNECTING':
        return (
          <span
            className="flex items-center gap-1.5 font-mono px-2.5 py-1 rounded border bg-amber-950/50 border-amber-500/40 text-amber-300 text-xs font-bold"
            title="Socket dropped. Automatically reconnecting with backoff..."
          >
            <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
            <span>RECONNECTING</span>
          </span>
        );
      case 'STALE DATA':
        return (
          <span
            className="flex items-center gap-1.5 font-mono px-2.5 py-1 rounded border bg-orange-950/60 border-orange-500/40 text-orange-300 text-xs font-bold"
            title="No market ticks received in >15s. Automated entries paused."
          >
            <AlertTriangle className="w-3.5 h-3.5 text-orange-400" />
            <span>STALE DATA</span>
            <span className="text-[10px] text-orange-400/80 font-normal">({dataAgeStr})</span>
          </span>
        );
      case 'MARKET CLOSED':
        return (
          <span
            className="flex items-center gap-1.5 font-mono px-2.5 py-1 rounded border bg-blue-950/60 border-blue-500/40 text-blue-300 text-xs font-bold"
            title="Market hours closed (09:15-15:30 IST weekdays). Showing last settled prices."
          >
            <Clock className="w-3.5 h-3.5 text-blue-400" />
            <span>MARKET CLOSED</span>
          </span>
        );
      default:
        return (
          <span
            className="flex items-center gap-1.5 font-mono px-2.5 py-1 rounded border bg-rose-950/60 border-rose-500/40 text-rose-300 text-xs font-bold"
            title="Feed disconnected. Check broker credentials or network."
          >
            <WifiOff className="w-3.5 h-3.5 text-rose-400" />
            <span>DISCONNECTED</span>
          </span>
        );
    }
  };

  return (
    <header className="bg-surface border-b border-border sticky top-0 z-40">
      {/* Top Bar: Brand, Live Tickers, Status Badges */}
      <div className="px-4 py-2 flex items-center justify-between">
        {/* Left: Mobile Toggle & Brand / Mode */}
        <div className="flex items-center space-x-3">
          {/* Mobile Sidebar Hamburger Button */}
          <button
            onClick={onToggleMobileSidebar}
            aria-label="Open navigation menu"
            className="lg:hidden p-2 rounded-lg text-gray-400 hover:text-white hover:bg-surface/80 border border-border"
          >
            <Menu className="w-5 h-5 text-blue-400" />
          </button>

          <div className="flex items-center space-x-2">
            <div className="w-8 h-8 rounded-lg bg-blue-600/20 border border-blue-500/40 flex items-center justify-center font-bold text-blue-400">
              NX
            </div>
            <div>
              <span className="font-extrabold tracking-wider text-base text-white">NEXTRADE</span>
              <span className="text-[10px] text-gray-400 block -mt-1 font-mono">ALGO TERMINAL</span>
            </div>
          </div>

          <div className="hidden sm:flex items-center space-x-2 pl-3 border-l border-border">
            <span className="px-2 py-0.5 text-xs font-semibold rounded bg-amber-500/10 text-amber-400 border border-amber-500/30 flex items-center gap-1 font-mono">
              <ShieldAlert className="w-3 h-3" />
              PAPER TRADING
            </span>

            {isDemo ? (
              <span className="px-2 py-0.5 text-xs font-semibold rounded bg-purple-500/10 text-purple-400 border border-purple-500/30 font-mono">
                SYNTHETIC FEED
              </span>
            ) : (
              <span className="px-2 py-0.5 text-xs font-semibold rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 font-mono">
                KOTAK NEO LIVE
              </span>
            )}
          </div>
        </div>

        {/* Center: Live Tickers with Flash Animations */}
        <div className="flex items-center space-x-5 text-sm font-mono">
          <div className="flex items-center space-x-2">
            <span className="text-gray-400 text-xs">NIFTY 50:</span>
            <span
              className={`font-bold text-base transition-colors duration-300 px-1 rounded ${
                spotFlash === 'up'
                  ? 'bg-emerald-500/20 text-emerald-300'
                  : spotFlash === 'down'
                  ? 'bg-rose-500/20 text-rose-300'
                  : 'text-white'
              }`}
            >
              {spotPrice ? spotPrice.toFixed(2) : '24,500.00'}
            </span>
          </div>

          <div className="hidden md:flex items-center space-x-2">
            <span className="text-gray-400 text-xs">{marketStatus?.option_symbol || 'ATM CE'}:</span>
            <span
              className={`font-bold text-base transition-colors duration-300 px-1 rounded ${
                optFlash === 'up'
                  ? 'bg-emerald-500/20 text-emerald-300'
                  : optFlash === 'down'
                  ? 'bg-rose-500/20 text-rose-300'
                  : 'text-blue-400'
              }`}
            >
              ₹{optionPrem ? optionPrem.toFixed(2) : '145.00'}
            </span>
          </div>

          <div className="hidden lg:flex items-center space-x-2 text-xs">
            <span className="text-gray-400">ATM:</span>
            <span className="text-gray-200 font-semibold">{marketStatus?.atm_strike || 24500}</span>
            <span className="text-gray-400">LOT:</span>
            <span className="text-gray-200 font-semibold">{marketStatus?.lot_size || 65}</span>
          </div>
        </div>

        {/* Right: Operational Status & Connection Health Monitor */}
        <div className="flex items-center space-x-2.5">
          {/* Active Strategy Badge */}
          <span className="hidden xl:flex items-center gap-1 font-mono text-xs px-2 py-1 rounded bg-blue-950/40 border border-blue-800/60 text-blue-300">
            <Zap className="w-3.5 h-3.5 text-amber-400" />
            {activeStrategy === 'AI_MICRO_SCALPER_V1'
              ? 'AI MICRO-SCALPER V1'
              : activeStrategy === 'SUPERTREND_EMA'
              ? 'SUPERTREND EMA'
              : activeStrategy === 'UT_BOT'
              ? 'UT BOT'
              : 'EMA/RSI'}
          </span>

          {/* Market Session Status */}
          <span
            className={`hidden sm:flex items-center gap-1 font-mono text-xs px-2 py-1 rounded border ${
              isMarketOpen
                ? 'bg-emerald-950/40 border-emerald-800/60 text-emerald-300'
                : 'bg-surface border-border text-gray-400'
            }`}
          >
            <Clock className="w-3 h-3" />
            {sessionStatus}
          </span>

          {/* Connection & Data Health Monitor Badge */}
          {renderHealthBadge()}
        </div>
      </div>
    </header>
  );
};
