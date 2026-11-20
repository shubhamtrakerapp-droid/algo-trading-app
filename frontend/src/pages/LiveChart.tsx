import React, { useState, useEffect, useCallback, useRef } from 'react';
import { ChartComponent } from '../components/ChartComponent';
import { wsClient } from '../services/websocket';
import {
  Candle,
  MarketStatus,
  PaperPosition,
  ChartType,
  Timeframe,
  ChartMode,
  RangePreset,
  ChartTradeMarker,
  InstrumentItem,
  BacktestRunItem,
} from '../types';
import { api } from '../services/api';
import { formatCurrency, formatIST, getPnlColor, getPnlBg } from '../utils/formatters';
import {
  BarChart2,
  CandlestickChart,
  TrendingUp,
  Layers,
  Activity,
  Calendar,
  Clock,
  ShieldCheck,
  Search,
  Filter,
  RefreshCw,
  Maximize2,
  Minimize2,
  ChevronDown,
  X,
  Play,
  Award,
  AlertTriangle,
  Flame,
  ArrowRight,
} from 'lucide-react';

interface LiveChartProps {
  candles?: Candle[];
  marketStatus: MarketStatus | null;
  activePosition: PaperPosition | null;
  initialMode?: ChartMode;
  initialRunId?: number;
  initialSymbol?: string;
}

export const LiveChart: React.FC<LiveChartProps> = ({
  marketStatus,
  activePosition,
  initialMode = 'LIVE',
  initialRunId,
  initialSymbol = 'NIFTY 50',
}) => {
  // Chart Mode State
  const [chartMode, setChartMode] = useState<ChartMode>(initialMode);
  const [dataSource, setDataSource] = useState<'REAL_MARKET' | 'SYNTHETIC_TEST'>('REAL_MARKET');

  // Instrument Selection
  const [selectedSymbol, setSelectedSymbol] = useState<string>(initialSymbol);
  const [instrumentInfo, setInstrumentInfo] = useState<any>(null);
  const [isInstrumentSearchOpen, setIsInstrumentSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<InstrumentItem[]>([]);

  // Timeframe and Range
  const [timeframe, setTimeframe] = useState<Timeframe>('1m');
  const [rangePreset, setRangePreset] = useState<RangePreset>('5D');
  const [startDate, setStartDate] = useState<string>('');
  const [endDate, setEndDate] = useState<string>('');
  const [isCustomRangeOpen, setIsCustomRangeOpen] = useState(false);

  // Style
  const [chartType, setChartType] = useState<ChartType>('candlestick');

  // Backtest Selection Mode
  const [selectedRunId, setSelectedRunId] = useState<number | undefined>(initialRunId);
  const [backtestRuns, setBacktestRuns] = useState<BacktestRunItem[]>([]);

  // Candle Data & Pagination
  const [candles, setCandles] = useState<Candle[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [hasMoreOlder, setHasMoreOlder] = useState(true);
  const [oldestTimestamp, setOldestTimestamp] = useState<number | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Trade Execution Markers
  const [tradeMarkers, setTradeMarkers] = useState<ChartTradeMarker[]>([]);
  const [selectedMarker, setSelectedMarker] = useState<ChartTradeMarker | null>(null);

  // Fullscreen state
  const [isFullscreen, setIsFullscreen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Load available instruments
  const loadInstruments = async (q = '') => {
    try {
      const res = await api.getChartInstruments(q);
      setSearchResults(res.instruments);
    } catch (e) {
      console.error('Failed to load instruments:', e);
    }
  };

  // Load completed backtest runs
  const loadBacktestRuns = async () => {
    try {
      const res = await api.getChartBacktestRuns();
      setBacktestRuns(res.runs);
      if (!selectedRunId && res.runs.length > 0) {
        setSelectedRunId(res.runs[0].run_id);
      }
    } catch (e) {
      console.error('Failed to load backtest runs:', e);
    }
  };

  useEffect(() => {
    loadInstruments();
    loadBacktestRuns();
  }, []);

  // Fetch primary candles
  const fetchCandles = useCallback(
    async (silent = false) => {
      if (!silent) setLoading(true);
      setErrorMsg(null);
      try {
        const res = await api.getCandles({
          symbol: selectedSymbol,
          timeframe,
          chartType,
          mode: chartMode,
          dataSource,
          rangePreset,
          startDate: rangePreset === 'CUSTOM' ? startDate : undefined,
          endDate: rangePreset === 'CUSTOM' ? endDate : undefined,
          limit: 400,
          runId: chartMode === 'BACKTEST' ? selectedRunId : undefined,
        });

        if (res.candles) {
          setCandles(res.candles);
          setHasMoreOlder(res.has_more ?? true);
          if (res.candles.length > 0) {
            setOldestTimestamp(res.candles[0].timestamp);
          }
        }
        if (res.instrument_info) {
          setInstrumentInfo(res.instrument_info);
        }
      } catch (err: any) {
        console.error('Failed to load chart candles:', err);
        setErrorMsg(err.message || 'Failed to fetch historical candles.');
      } finally {
        if (!silent) setLoading(false);
      }
    },
    [selectedSymbol, timeframe, chartType, chartMode, dataSource, rangePreset, startDate, endDate, selectedRunId]
  );

  // Load trade markers
  const fetchTradeMarkers = useCallback(async () => {
    try {
      const res = await api.getChartTradeMarkers({
        mode: chartMode === 'BACKTEST' ? 'BACKTEST' : 'LIVE',
        runId: chartMode === 'BACKTEST' ? selectedRunId : undefined,
        symbol: selectedSymbol,
        startDate: rangePreset === 'CUSTOM' ? startDate : undefined,
        endDate: rangePreset === 'CUSTOM' ? endDate : undefined,
      });
      setTradeMarkers(res.markers || []);
    } catch (e) {
      console.error('Failed to load trade markers:', e);
    }
  }, [chartMode, selectedRunId, selectedSymbol, rangePreset, startDate, endDate]);

  // Initial and reactive fetch
  useEffect(() => {
    fetchCandles();
    fetchTradeMarkers();
  }, [fetchCandles, fetchTradeMarkers]);

  // Real-time WebSocket streaming for LIVE mode
  useEffect(() => {
    if (chartMode !== 'LIVE') return;

    // Register active symbol on backend feed
    wsClient.subscribeSymbols([selectedSymbol]);

    const unsubscribe = wsClient.subscribe((msg: any) => {
      if (!msg || !msg.type) return;

      const normSymbol = (sym?: string) => sym?.trim().toUpperCase() || '';
      const activeSym = normSymbol(selectedSymbol);

      // 1. Tick updates: update high, low, close of currently forming candle
      if (msg.type === 'TICK') {
        const tick = msg.data;
        if (!tick) return;
        const tickSym = normSymbol(tick.symbol);
        const matches =
          tickSym === activeSym ||
          (activeSym.includes('NIFTY 50') && tick.is_index) ||
          (activeSym.includes('ATM CE') && !tick.is_index && tickSym.includes('CE')) ||
          (activeSym.includes('ATM PE') && !tick.is_index && tickSym.includes('PE'));

        if (matches) {
          setCandles((prev) => {
            if (!prev || prev.length === 0) return prev;
            const last = prev[prev.length - 1];
            const tickEpoch = Math.floor(new Date(tick.timestamp).getTime() / 1000);
            const lastEpoch = last.timestamp;

            // Only update if within the same minute or slightly beyond
            if (Math.abs(tickEpoch - lastEpoch) <= 65) {
              const updated: Candle = {
                ...last,
                high: Math.max(last.high, tick.price),
                low: Math.min(last.low, tick.price),
                close: tick.price,
                volume: last.volume + (tick.volume ? 1 : 0),
              };
              return [...prev.slice(0, -1), updated];
            }
            return prev;
          });
        }
      }

      // 2. Forming Candle updates: authoritative bar from CandleBuilder
      else if (msg.type === 'FORMING_CANDLE') {
        const fc = msg.data;
        if (!fc) return;
        const fcSym = normSymbol(fc.symbol);
        const matches =
          fcSym === activeSym ||
          (activeSym.includes('NIFTY 50') && (fcSym === 'NIFTY 50' || fcSym === 'NIFTY')) ||
          (activeSym.includes('ATM CE') && fcSym.includes('CE')) ||
          (activeSym.includes('ATM PE') && fcSym.includes('PE'));

        if (matches) {
          setCandles((prev) => {
            if (!prev || prev.length === 0) return prev;
            const last = prev[prev.length - 1];
            if (last.timestamp === fc.timestamp) {
              const updated: Candle = {
                ...last,
                open: fc.open,
                high: Math.max(last.high, fc.high),
                low: Math.min(last.low, fc.low),
                close: fc.close,
                volume: fc.volume,
              };
              return [...prev.slice(0, -1), updated];
            } else if (fc.timestamp > last.timestamp) {
              // Seamlessly append new minute forming bar
              const newBar: Candle = {
                timestamp: fc.timestamp,
                open: fc.open,
                high: fc.high,
                low: fc.low,
                close: fc.close,
                volume: fc.volume,
              };
              return [...prev, newBar];
            }
            return prev;
          });
        }
      }

      // 3. Completed Candle updates: finalize the closed bar
      else if (msg.type === 'CANDLE_COMPLETED') {
        const cc = msg.data;
        if (!cc) return;
        const ccSym = normSymbol(cc.symbol);
        const matches =
          ccSym === activeSym ||
          (activeSym.includes('NIFTY 50') && (ccSym === 'NIFTY 50' || ccSym === 'NIFTY')) ||
          (activeSym.includes('ATM CE') && ccSym.includes('CE')) ||
          (activeSym.includes('ATM PE') && ccSym.includes('PE'));

        if (matches) {
          setCandles((prev) => {
            if (!prev || prev.length === 0) return prev;
            const last = prev[prev.length - 1];
            if (last.timestamp === cc.timestamp) {
              const finalized: Candle = {
                ...last,
                open: cc.open,
                high: cc.high,
                low: cc.low,
                close: cc.close,
                volume: cc.volume,
              };
              return [...prev.slice(0, -1), finalized];
            } else if (cc.timestamp > last.timestamp) {
              const newBar: Candle = {
                timestamp: cc.timestamp,
                open: cc.open,
                high: cc.high,
                low: cc.low,
                close: cc.close,
                volume: cc.volume,
              };
              return [...prev, newBar];
            }
            return prev;
          });
          // Refresh markers when candle completes
          fetchTradeMarkers();
        }
      }

      // 4. Trade execution: update markers immediately
      else if (msg.type === 'TRADE_EXECUTED' || msg.type === 'AUTO_EXIT_TRIGGERED' || msg.type === 'POSITION_UPDATE') {
        fetchTradeMarkers();
      }
    });

    return () => {
      unsubscribe();
      wsClient.unsubscribeSymbols([selectedSymbol]);
    };
  }, [chartMode, selectedSymbol, fetchTradeMarkers]);

  // Lazy-load older candles when scrolling backwards
  const handleLoadMoreOlderCandles = async () => {
    if (loadingOlder || !hasMoreOlder || !oldestTimestamp) return;
    setLoadingOlder(true);
    try {
      const res = await api.getCandles({
        symbol: selectedSymbol,
        timeframe,
        chartType,
        mode: chartMode,
        dataSource,
        beforeTimestamp: oldestTimestamp,
        limit: 300,
        runId: chartMode === 'BACKTEST' ? selectedRunId : undefined,
      });

      if (res.candles && res.candles.length > 0) {
        // Prepend older unique candles
        setCandles((prev) => {
          const seen = new Set(prev.map((c) => c.timestamp));
          const older = res.candles.filter((c) => !seen.has(c.timestamp));
          return [...older, ...prev];
        });
        setOldestTimestamp(res.candles[0].timestamp);
        setHasMoreOlder(res.has_more);
      } else {
        setHasMoreOlder(false);
      }
    } catch (e) {
      console.error('Failed to fetch older candles:', e);
    } finally {
      setLoadingOlder(false);
    }
  };

  // Fullscreen toggle
  const toggleFullscreen = () => {
    if (!containerRef.current) return;
    if (!document.fullscreenElement) {
      containerRef.current.requestFullscreen().then(() => setIsFullscreen(true)).catch(() => {});
    } else {
      document.exitFullscreen().then(() => setIsFullscreen(false)).catch(() => {});
    }
  };

  // Derived contracts
  const atmCeSymbol = marketStatus?.option_symbol || 'NIFTY ATM CE';
  const atmStrike = marketStatus?.atm_strike || 24500;
  const atmPeSymbol = `NIFTY ${atmStrike} PE`;

  // Latest candle LTP
  const latestCandle = candles.length > 0 ? candles[candles.length - 1] : null;

  return (
    <div ref={containerRef} className="space-y-4 bg-background">
      {/* 1. Top Control Bar: Mode, Instruments, Range, Timeframe */}
      <div className="bg-card border border-border rounded-xl p-3 space-y-3 shadow-sm">
        {/* Row 1: Mode Switcher & Real-time Feeds status */}
        <div className="flex flex-wrap items-center justify-between gap-3 pb-2 border-b border-border/40 font-mono text-xs">
          {/* Mode Tabs */}
          <div className="bg-surface p-1 rounded-lg border border-border flex items-center gap-1 font-bold overflow-x-auto max-w-full">
            <button
              onClick={() => setChartMode('LIVE')}
              className={`px-2.5 sm:px-3 py-1.5 rounded-md flex items-center gap-1.5 transition-all whitespace-nowrap text-[11px] sm:text-xs ${
                chartMode === 'LIVE'
                  ? 'bg-emerald-600 text-white shadow-sm'
                  : 'text-gray-400 hover:text-white hover:bg-surface/80'
              }`}
            >
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              LIVE PAPER
            </button>
            <button
              onClick={() => setChartMode('BACKTEST')}
              className={`px-2.5 sm:px-3 py-1.5 rounded-md flex items-center gap-1.5 transition-all whitespace-nowrap text-[11px] sm:text-xs ${
                chartMode === 'BACKTEST'
                  ? 'bg-blue-600 text-white shadow-sm'
                  : 'text-gray-400 hover:text-white hover:bg-surface/80'
              }`}
            >
              <Play className="w-3.5 h-3.5" />
              BACKTEST REPLAY
            </button>
            <button
              onClick={() => setChartMode('HISTORICAL')}
              className={`px-2.5 sm:px-3 py-1.5 rounded-md flex items-center gap-1.5 transition-all whitespace-nowrap text-[11px] sm:text-xs ${
                chartMode === 'HISTORICAL'
                  ? 'bg-purple-600 text-white shadow-sm'
                  : 'text-gray-400 hover:text-white hover:bg-surface/80'
              }`}
            >
              <Calendar className="w-3.5 h-3.5" />
              HISTORICAL BROWSER
            </button>
          </div>

          {/* Right Status Badge */}
          <div className="flex items-center space-x-3 text-[11px]">
            {chartMode === 'LIVE' && (
              <span className="flex items-center space-x-1 text-emerald-400 font-bold bg-emerald-950/40 border border-emerald-800/50 px-2.5 py-1 rounded-md">
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
                <span>
                  {marketStatus?.is_demo ? 'SIMULATED DEMO FEED' : 'KOTAK NEO LIVE STREAM'}
                </span>
              </span>
            )}
            {chartMode === 'BACKTEST' && (
              <div className="flex items-center space-x-2">
                <span className="text-gray-400">Backtest Run:</span>
                <select
                  value={selectedRunId || ''}
                  onChange={(e) => setSelectedRunId(parseInt(e.target.value, 10))}
                  className="bg-surface border border-border rounded px-2.5 py-1 text-white font-bold focus:outline-none focus:border-blue-500 cursor-pointer"
                >
                  {backtestRuns.length === 0 ? (
                    <option value="">No completed runs found</option>
                  ) : (
                    backtestRuns.map((r) => (
                      <option key={r.run_id} value={r.run_id}>
                        Run #{r.run_id} &bull; {r.strategy_id} &bull; {r.instrument_symbol} ({r.start_date} to {r.end_date})
                      </option>
                    ))
                  )}
                </select>
              </div>
            )}
            {chartMode === 'HISTORICAL' && (
              <div className="flex items-center space-x-2">
                <span className="text-gray-400">Data Source:</span>
                <select
                  value={dataSource}
                  onChange={(e) => setDataSource(e.target.value as any)}
                  className="bg-surface border border-border rounded px-2 py-1 text-white font-bold focus:outline-none focus:border-purple-500 cursor-pointer"
                >
                  <option value="REAL_MARKET">Kotak Neo Authentic Historical</option>
                  <option value="SYNTHETIC_TEST">Deterministic Synthetic Test Data</option>
                </select>
              </div>
            )}

            <button
              onClick={() => fetchCandles()}
              className="p-1.5 rounded-lg bg-surface border border-border hover:bg-surface/80 text-gray-400 hover:text-white transition-colors"
              title="Refresh Candles"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-blue-400' : ''}`} />
            </button>

            <button
              onClick={toggleFullscreen}
              className="p-1.5 rounded-lg bg-surface border border-border hover:bg-surface/80 text-gray-400 hover:text-white transition-colors"
              title={isFullscreen ? 'Exit Fullscreen' : 'Fullscreen Chart'}
            >
              {isFullscreen ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
            </button>
          </div>
        </div>

        {/* Row 2: Instrument Pills, Timeframes, Range Presets & Chart Styles */}
        <div className="flex flex-wrap items-center justify-between gap-3 font-mono text-xs">
          {/* Instruments */}
          <div className="flex flex-wrap items-center gap-1.5">
            <button
              onClick={() => setSelectedSymbol('NIFTY 50')}
              className={`px-3 py-1.5 rounded-lg font-bold transition-all ${
                selectedSymbol === 'NIFTY 50'
                  ? 'bg-blue-600 text-white shadow-sm'
                  : 'bg-surface text-gray-400 hover:text-white border border-border'
              }`}
            >
              NIFTY 50 INDEX
            </button>

            <button
              onClick={() => setSelectedSymbol(atmCeSymbol)}
              className={`px-3 py-1.5 rounded-lg font-bold transition-all ${
                selectedSymbol === atmCeSymbol
                  ? 'bg-blue-600 text-white shadow-sm'
                  : 'bg-surface text-gray-400 hover:text-white border border-border'
              }`}
            >
              {atmCeSymbol}
            </button>

            <button
              onClick={() => setSelectedSymbol(atmPeSymbol)}
              className={`px-3 py-1.5 rounded-lg font-bold transition-all ${
                selectedSymbol === atmPeSymbol
                  ? 'bg-blue-600 text-white shadow-sm'
                  : 'bg-surface text-gray-400 hover:text-white border border-border'
              }`}
            >
              {atmPeSymbol}
            </button>

            <button
              onClick={() => setIsInstrumentSearchOpen(!isInstrumentSearchOpen)}
              className="px-2.5 py-1.5 rounded-lg bg-surface border border-border hover:bg-surface/80 text-purple-400 hover:text-purple-300 font-bold flex items-center gap-1"
            >
              <Search className="w-3.5 h-3.5" />
              <span>More Strikes</span>
              <ChevronDown className="w-3 h-3" />
            </button>
          </div>

          {/* Timeframe Selector (all 9 timeframes) */}
          <div className="flex items-center space-x-1 bg-surface p-1 rounded-lg border border-border">
            {(['1m', '2m', '3m', '5m', '15m', '30m', '1h', '4h', '1D'] as Timeframe[]).map((tf) => (
              <button
                key={tf}
                onClick={() => setTimeframe(tf)}
                className={`px-2 py-1 rounded text-xs transition-colors ${
                  timeframe === tf
                    ? 'bg-blue-600 text-white font-bold shadow-sm'
                    : 'text-gray-400 hover:text-white hover:bg-card'
                }`}
              >
                {tf}
              </button>
            ))}
          </div>

          {/* Date Range Presets */}
          <div className="flex items-center space-x-1 bg-surface p-1 rounded-lg border border-border">
            {(['TODAY', '1D', '5D', '1M', '3M', '6M', '1Y', 'CUSTOM'] as RangePreset[]).map((rp) => (
              <button
                key={rp}
                onClick={() => {
                  setRangePreset(rp);
                  if (rp === 'CUSTOM') {
                    setIsCustomRangeOpen(true);
                  }
                }}
                className={`px-2 py-1 rounded text-[11px] transition-colors ${
                  rangePreset === rp
                    ? 'bg-purple-600 text-white font-bold shadow-sm'
                    : 'text-gray-400 hover:text-white hover:bg-card'
                }`}
              >
                {rp}
              </button>
            ))}
          </div>

          {/* Chart Style (Candle, Heikin Ashi, Bar, Line, Area) */}
          <div className="flex items-center space-x-1 bg-surface p-1 rounded-lg border border-border">
            <button
              onClick={() => setChartType('candlestick')}
              title="Candlestick Chart"
              className={`p-1.5 rounded transition-colors ${
                chartType === 'candlestick' ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-white'
              }`}
            >
              <CandlestickChart className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => setChartType('heikin_ashi')}
              title="Heikin Ashi Smoothed Candles"
              className={`p-1.5 rounded transition-colors ${
                chartType === 'heikin_ashi' ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-white'
              }`}
            >
              <Activity className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => setChartType('bar')}
              title="Bar Chart"
              className={`p-1.5 rounded transition-colors ${
                chartType === 'bar' ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-white'
              }`}
            >
              <BarChart2 className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => setChartType('line')}
              title="Line Chart"
              className={`p-1.5 rounded transition-colors ${
                chartType === 'line' ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-white'
              }`}
            >
              <TrendingUp className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => setChartType('area')}
              title="Area Chart"
              className={`p-1.5 rounded transition-colors ${
                chartType === 'area' ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-white'
              }`}
            >
              <Layers className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {/* Custom Range Picker Drawer (when CUSTOM range selected) */}
        {isCustomRangeOpen && (
          <div className="bg-surface/80 border border-purple-500/40 rounded-xl p-3 flex flex-wrap items-center justify-between gap-3 text-xs font-mono">
            <div className="flex items-center space-x-3">
              <span className="text-purple-400 font-bold flex items-center gap-1">
                <Calendar className="w-3.5 h-3.5" /> Custom Date Range:
              </span>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="bg-card border border-border rounded px-2.5 py-1 text-white font-bold"
              />
              <span className="text-gray-500">to</span>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="bg-card border border-border rounded px-2.5 py-1 text-white font-bold"
              />
              <button
                onClick={() => {
                  fetchCandles();
                  setIsCustomRangeOpen(false);
                }}
                className="px-3 py-1 bg-purple-600 hover:bg-purple-500 text-white font-bold rounded"
              >
                Apply
              </button>
            </div>
            <button
              onClick={() => setIsCustomRangeOpen(false)}
              className="text-gray-400 hover:text-white"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        )}

        {/* Instrument Search Modal / Dropdown */}
        {isInstrumentSearchOpen && (
          <div className="bg-surface/90 border border-border rounded-xl p-3 space-y-2 text-xs font-mono animate-in fade-in duration-150">
            <div className="flex items-center justify-between pb-2 border-b border-border/40">
              <span className="font-bold text-white">Select Chart Instrument or Option Contract:</span>
              <button
                onClick={() => setIsInstrumentSearchOpen(false)}
                className="text-gray-400 hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <input
              type="text"
              placeholder="Search strike, CE, PE (e.g. 24500, PE, CE)..."
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                loadInstruments(e.target.value);
              }}
              className="w-full bg-card border border-border rounded px-3 py-1.5 text-white font-bold"
              autoFocus
            />
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2 max-h-48 overflow-y-auto pt-1">
              {searchResults.map((inst, i) => (
                <div
                  key={i}
                  onClick={() => {
                    setSelectedSymbol(inst.symbol);
                    setIsInstrumentSearchOpen(false);
                  }}
                  className="p-2 rounded-lg bg-card border border-border hover:border-purple-500 cursor-pointer transition-colors"
                >
                  <div className="font-bold text-white flex items-center justify-between">
                    <span>{inst.symbol}</span>
                    <span
                      className={`text-[9px] px-1 rounded ${
                        inst.type === 'CE'
                          ? 'bg-emerald-500/10 text-emerald-400'
                          : inst.type === 'PE'
                          ? 'bg-rose-500/10 text-rose-400'
                          : 'bg-blue-500/10 text-blue-400'
                      }`}
                    >
                      {inst.type}
                    </span>
                  </div>
                  <div className="text-[10px] text-gray-400 mt-1 flex justify-between">
                    <span>LTP: ₹{inst.current_price.toFixed(1)}</span>
                    {inst.strike && <span>Strike: {inst.strike}</span>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Error / Data Quality Notice Banner */}
      {errorMsg && (
        <div className="bg-rose-950/40 border border-rose-800/60 rounded-xl p-3 px-4 text-xs font-mono text-rose-300 flex items-center justify-between gap-3 shadow-lg">
          <div className="flex items-center space-x-2">
            <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
            <span>{errorMsg}</span>
          </div>
          <button
            onClick={() => fetchCandles()}
            className="px-2.5 py-1 bg-rose-700/60 hover:bg-rose-600 border border-rose-500 rounded text-white text-xs font-bold transition-colors flex items-center gap-1.5 shrink-0"
          >
            <RefreshCw className="w-3 h-3" />
            <span>Retry</span>
          </button>
        </div>
      )}

      {/* 2. Real-time Ticker & Market Telemetry Strip */}
      <div className="bg-surface/50 border border-border rounded-xl px-4 py-2.5 flex flex-wrap items-center justify-between text-xs font-mono text-gray-300 gap-3">
        <div className="flex flex-wrap items-center gap-4">
          <div>
            <span className="text-gray-500">INSTRUMENT: </span>
            <span className="font-bold text-white">{selectedSymbol}</span>
            {instrumentInfo?.strike && (
              <span className="ml-2 px-1.5 py-0.5 rounded text-[10px] bg-purple-500/10 text-purple-300 border border-purple-500/20">
                Strike {instrumentInfo.strike} {instrumentInfo.option_type}
              </span>
            )}
          </div>

          <div>
            <span className="text-gray-500">LTP: </span>
            <span className="font-extrabold text-emerald-400">
              {latestCandle ? `₹${latestCandle.close.toFixed(2)}` : 'Loading...'}
            </span>
          </div>

          {latestCandle && (
            <div className="hidden lg:flex items-center space-x-3 text-gray-400 text-[11px]">
              <span>O: {latestCandle.open.toFixed(2)}</span>
              <span>H: {latestCandle.high.toFixed(2)}</span>
              <span>L: {latestCandle.low.toFixed(2)}</span>
              <span>C: {latestCandle.close.toFixed(2)}</span>
              <span>Vol: {latestCandle.volume.toLocaleString()}</span>
            </div>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-4 text-[11px]">
          <div>
            <span className="text-gray-500">BARS: </span>
            <span className="text-white font-bold">{candles.length}</span>
            {loadingOlder && <span className="ml-1 text-purple-400 animate-pulse">(fetching older...)</span>}
          </div>

          <div>
            <span className="text-gray-500">MARKERS: </span>
            <span className="text-purple-400 font-bold">{tradeMarkers.length} Trade Points</span>
          </div>

          <div>
            <span className="text-gray-500">TIMEFRAME: </span>
            <span className="text-blue-400 font-bold">{timeframe}</span>
          </div>
        </div>
      </div>

      {/* 3. TradingView Interactive Canvas */}
      <div className="relative border border-border rounded-xl overflow-hidden shadow-lg">
        {loading && candles.length === 0 && (
          <div className="absolute inset-0 bg-background/70 backdrop-blur-sm flex flex-col items-center justify-center z-30 font-mono text-xs text-gray-300">
            <RefreshCw className="w-7 h-7 text-purple-400 animate-spin mb-2" />
            <span>Loading complete historical data for {selectedSymbol}...</span>
          </div>
        )}

        <ChartComponent
          candles={candles}
          activePosition={activePosition}
          height={isFullscreen ? 800 : 580}
          chartType={chartType}
          symbolName={selectedSymbol}
          tradeMarkers={tradeMarkers}
          onSelectMarker={(m) => setSelectedMarker(m)}
          onLoadMoreOlderCandles={handleLoadMoreOlderCandles}
          isLoadingMore={loadingOlder}
        />
      </div>

      {/* 4. Trade Marker Inspection Modal / Popover */}
      {selectedMarker && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-card border border-border rounded-2xl w-full max-w-lg shadow-2xl overflow-hidden font-mono text-xs animate-in zoom-in-95 duration-150">
            {/* Modal Header */}
            <div className="px-5 py-3.5 border-b border-border flex items-center justify-between bg-surface/60">
              <div className="flex items-center space-x-2">
                <Award className="w-4 h-4 text-purple-400" />
                <span className="font-bold text-white">
                  {selectedMarker.trade_type === 'ENTRY' ? 'BUY Trade Entry Marker' : `${selectedMarker.exit_reason} Exit Marker`}
                </span>
                <span
                  className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                    selectedMarker.trade_type === 'ENTRY'
                      ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                      : selectedMarker.net_pnl && selectedMarker.net_pnl > 0
                      ? 'bg-emerald-500/20 text-emerald-300'
                      : 'bg-rose-500/20 text-rose-300'
                  }`}
                >
                  #{selectedMarker.trade_id}
                </span>
              </div>
              <button
                onClick={() => setSelectedMarker(null)}
                className="p-1 rounded bg-surface border border-border text-gray-400 hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Modal Body: Complete Audited Trade Parameters */}
            <div className="p-5 space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div className="bg-surface/50 border border-border p-2.5 rounded-lg">
                  <span className="text-[10px] text-gray-500 block">CONTRACT</span>
                  <span className="font-bold text-white">{selectedMarker.contract}</span>
                </div>
                <div className="bg-surface/50 border border-border p-2.5 rounded-lg">
                  <span className="text-[10px] text-gray-500 block">STRATEGY</span>
                  <span className="font-bold text-purple-400">{selectedMarker.strategy_id}</span>
                </div>
                <div className="bg-surface/50 border border-border p-2.5 rounded-lg">
                  <span className="text-[10px] text-gray-500 block">FILL PRICE</span>
                  <span className="font-bold text-emerald-400">₹{selectedMarker.price.toFixed(2)}</span>
                </div>
                <div className="bg-surface/50 border border-border p-2.5 rounded-lg">
                  <span className="text-[10px] text-gray-500 block">QUANTITY</span>
                  <span className="font-bold text-white">{selectedMarker.quantity}</span>
                </div>
              </div>

              {selectedMarker.trade_type === 'EXIT' && (
                <div className="border border-border rounded-xl p-3 bg-surface/30 space-y-2">
                  <span className="text-[10px] text-gray-500 block">MATHEMATICAL RECONCILIATION</span>
                  <div className="grid grid-cols-3 gap-2 text-center">
                    <div>
                      <span className="text-[10px] text-gray-500 block">GROSS P&amp;L</span>
                      <span className={`font-bold ${getPnlColor(selectedMarker.gross_pnl)}`}>
                        {formatCurrency(selectedMarker.gross_pnl)}
                      </span>
                    </div>
                    <div>
                      <span className="text-[10px] text-gray-500 block">FLAT CHARGES</span>
                      <span className="text-gray-300 font-bold">₹{Number(selectedMarker.charges ?? 20.0).toFixed(2)}</span>
                    </div>
                    <div>
                      <span className="text-[10px] text-gray-500 block">NET P&amp;L</span>
                      <span className={`font-extrabold ${getPnlColor(selectedMarker.net_pnl)}`}>
                        {formatCurrency(selectedMarker.net_pnl)}
                      </span>
                    </div>
                  </div>
                </div>
              )}

              <div className="space-y-1 text-gray-400 text-[11px]">
                <div className="flex justify-between">
                  <span>Entry Time:</span>
                  <span className="text-white">{formatIST(selectedMarker.entry_time)}</span>
                </div>
                {selectedMarker.exit_time && (
                  <div className="flex justify-between">
                    <span>Exit Time:</span>
                    <span className="text-white">{formatIST(selectedMarker.exit_time)}</span>
                  </div>
                )}
                {selectedMarker.sl_trigger && (
                  <div className="flex justify-between">
                    <span>SL Trigger Level:</span>
                    <span className="text-rose-400">₹{selectedMarker.sl_trigger.toFixed(2)}</span>
                  </div>
                )}
                {selectedMarker.target_trigger && (
                  <div className="flex justify-between">
                    <span>Target Trigger Level:</span>
                    <span className="text-emerald-400">₹{selectedMarker.target_trigger.toFixed(2)}</span>
                  </div>
                )}
              </div>
            </div>

            {/* Modal Footer */}
            <div className="px-5 py-3 border-t border-border bg-surface/30 flex justify-end">
              <button
                onClick={() => setSelectedMarker(null)}
                className="px-4 py-1.5 rounded-lg bg-surface border border-border hover:bg-surface/80 text-white font-bold"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
