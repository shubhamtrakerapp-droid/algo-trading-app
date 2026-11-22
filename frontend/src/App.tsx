import React, { useEffect, useState } from 'react';
import { Navbar } from './components/Navbar';
import { Sidebar } from './components/Sidebar';
import { BottomNav } from './components/BottomNav';
import { Dashboard } from './pages/Dashboard';
import { LiveChart } from './pages/LiveChart';
import { OptionChain } from './pages/OptionChain';
import { Strategy } from './pages/Strategy';
import { PaperTrading } from './pages/PaperTrading';
import { OpenPositions } from './pages/OpenPositions';
import { TradeHistory } from './pages/TradeHistory';
import { Backtesting } from './pages/Backtesting';
import { Analytics } from './pages/Analytics';
import { Settings } from './pages/Settings';
import { AIMicroScalper } from './pages/AIMicroScalper';
import { PCRAnalysis } from './pages/PCRAnalysis';
import { ErrorBoundary } from './components/ErrorBoundary';
import { AuthProvider } from './context/AuthContext';

import { MarketStatus, PaperAccountStatus, StrategyStatus, Candle } from './types';
import { api } from './services/api';
import { wsClient } from './services/websocket';
import { AlertCircle, CheckCircle2 } from 'lucide-react';

const defaultMarketStatus: MarketStatus = {
  is_connected: true,
  is_demo: true,
  broker_name: 'Kotak Neo (Simulated Demo)',
  feed_status: 'ONLINE',
  is_stale: false,
  last_tick_time: null,
  nifty_price: 24500.0,
  option_symbol: 'NIFTY ATM CE',
  option_premium: 145.0,
  atm_strike: 24500.0,
  expiry: 'WEEKLY',
  lot_size: 65,
  instrument_token: 'OPT_24500_CE',
  timestamp: new Date().toISOString(),
};

const defaultPaperStatus: PaperAccountStatus = {
  initial_capital: 100000.0,
  cash_balance: 100000.0,
  portfolio_value: 100000.0,
  realized_pnl: 0.0,
  unrealized_pnl: 0.0,
  daily_pnl: 0.0,
  total_trades: 0,
  win_rate: 0.0,
  active_position: null,
  default_lots: 1,
  max_loss_per_trade: 1000.0,
  target_points: 4.0,
  stop_points: 4.0,
  force_exit_time_ist: '15:20',
};

const defaultStrategyStatus: StrategyStatus = {
  status: 'ACTIVE',
  condition_1: false,
  condition_2: false,
  condition_3: false,
  condition_4: false,
  signal: 'NONE',
  is_buy: false,
};

const MainApp: React.FC = () => {
  const [activeTab, setActiveTab] = useState<string>('dashboard');
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState<boolean>(() => {
    return localStorage.getItem('nextrade_sidebar_collapsed') === 'true';
  });
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState<boolean>(false);
  const [analyticsSource, setAnalyticsSource] = useState<'PAPER' | 'BACKTEST'>('PAPER');
  const [analyticsRunId, setAnalyticsRunId] = useState<number | undefined>(undefined);

  const [marketStatus, setMarketStatus] = useState<MarketStatus>(defaultMarketStatus);
  const [paperStatus, setPaperStatus] = useState<PaperAccountStatus>(defaultPaperStatus);
  const [strategyStatus, setStrategyStatus] = useState<StrategyStatus>(defaultStrategyStatus);
  const [candles, setCandles] = useState<Candle[]>([]);
  const [toastMessage, setToastMessage] = useState<{ text: string; type: 'success' | 'warning' | 'info' } | null>(null);

  const handleNavigateToAnalytics = (runId: number) => {
    setAnalyticsSource('BACKTEST');
    setAnalyticsRunId(runId);
    setActiveTab('analytics');
  };

  const showToast = (text: string, type: 'success' | 'warning' | 'info' = 'info') => {
    setToastMessage({ text, type });
    setTimeout(() => setToastMessage(null), 4000);
  };

  const refreshAll = async () => {
    try {
      const [mStatus, pStatus, sStatus, candleData] = await Promise.all([
        api.getMarketStatus(),
        api.getPaperStatus(),
        api.getStrategyStatus(),
        api.getCandles('NIFTY 50', 100),
      ]);
      setMarketStatus(mStatus);
      setPaperStatus(pStatus);
      setStrategyStatus(sStatus);
      if (candleData && candleData.candles) {
        setCandles(candleData.candles);
      }
    } catch (e) {
      console.error('Error fetching initial data:', e);
    }
  };

  useEffect(() => {
    refreshAll();
    wsClient.connect();

    const unsubscribe = wsClient.subscribe((msg) => {
      if (msg.type === 'INITIAL_SNAPSHOT') {
        const d = msg.data;
        setMarketStatus((prev) => ({
          ...prev,
          nifty_price: d.nifty_price ?? prev.nifty_price,
          option_premium: d.option_premium ?? prev.option_premium,
          is_connected: d.is_connected ?? prev.is_connected,
        }));
        if (d.active_position) {
          setPaperStatus((prev) => ({ ...prev, active_position: d.active_position }));
        }
      } else if (msg.type === 'TICK') {
        const tick = msg.data;
        if (tick.is_index) {
          setMarketStatus((prev) => ({ ...prev, nifty_price: tick.price }));
        } else {
          setMarketStatus((prev) => ({ ...prev, option_premium: tick.price }));
          setPaperStatus((prev) => {
            if (!prev.active_position) return prev;
            const pos = prev.active_position;
            const gross = (tick.price - pos.entry_price) * pos.quantity;
            const net = gross - pos.charges;
            return {
              ...prev,
              active_position: {
                ...pos,
                current_price: tick.price,
                gross_pnl: Math.round(gross * 100) / 100,
                net_pnl: Math.round(net * 100) / 100,
              },
            };
          });
        }
      } else if (msg.type === 'FORMING_CANDLE') {
        const fc = msg.data;
        if (fc && (fc.symbol === 'NIFTY 50' || fc.symbol === 'NIFTY')) {
          setCandles((prev) => {
            if (!prev || prev.length === 0) return prev;
            const last = prev[prev.length - 1];
            if (last.timestamp === fc.timestamp) {
              const updated = {
                ...last,
                open: fc.open,
                high: Math.max(last.high, fc.high),
                low: Math.min(last.low, fc.low),
                close: fc.close,
                volume: fc.volume,
              };
              return [...prev.slice(0, -1), updated];
            } else if (fc.timestamp > last.timestamp) {
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
      } else if (msg.type === 'CANDLE_COMPLETED') {
        const cc = msg.data;
        if (cc && (cc.symbol === 'NIFTY 50' || cc.symbol === 'NIFTY')) {
          setCandles((prev) => {
            if (!prev || prev.length === 0) return prev;
            const last = prev[prev.length - 1];
            if (last.timestamp === cc.timestamp) {
              const finalized = {
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
        }
      } else if (msg.type === 'STRATEGY_SIGNAL') {
        const sig = msg.data;
        setStrategyStatus(sig);
        if (sig.is_buy) {
          showToast(`BUY Signal Confirmed at ${sig.time_ist} IST (NIFTY ${sig.underlying_price})`, 'success');
        }
      } else if (msg.type === 'FEED_STATUS') {
        setMarketStatus((prev) => ({
          ...prev,
          is_connected: msg.data.status === 'CONNECTED' || msg.data.status === 'DEMO_CONNECTED',
        }));
      } else if (msg.type === 'STALE_DATA_WARNING') {
        showToast('Warning: Market data feed is stale. New automated trades paused.', 'warning');
      }
    });

    const interval = setInterval(() => {
      api.getMarketStatus().then((s) => s && setMarketStatus(s)).catch(() => {});
      api.getPaperStatus().then((s) => s && setPaperStatus(s)).catch(() => {});
      api.getStrategyStatus().then((s) => s && setStrategyStatus(s)).catch(() => {});
    }, 10000);

    return () => {
      unsubscribe();
      clearInterval(interval);
    };
  }, []);

  const handleOpenTrade = async () => {
    try {
      const res = await api.placeManualOrder(1);
      showToast(`Simulated Order FILLED: ${res.position.symbol} @ ₹${res.position.entry_price}`, 'success');
      refreshAll();
    } catch (e: any) {
      showToast(e.message || 'Order failed', 'warning');
    }
  };

  const handleCloseTrade = async () => {
    try {
      const res = await api.closePosition();
      showToast(`Position SQUARED OFF: ${res.trade?.exit_reason || 'Manual'} | P&L: ₹${res.trade?.net_pnl}`, 'info');
      refreshAll();
    } catch (e: any) {
      showToast(e.message || 'Close failed', 'warning');
    }
  };

  const handleResetPaper = async () => {
    try {
      const res = await api.resetPaperData();
      showToast(res.message || 'All demo trades and records cleared.', 'success');
      refreshAll();
    } catch (e: any) {
      showToast(e.message || 'Reset failed', 'warning');
    }
  };

  return (
    <div className="min-h-screen bg-background text-gray-100 flex font-sans">
      {/* Permanent Left Sidebar Navigation */}
      <Sidebar
        activeTab={activeTab}
        setActiveTab={(tab) => {
          setActiveTab(tab);
          setIsMobileSidebarOpen(false);
        }}
        isOpenMobile={isMobileSidebarOpen}
        onCloseMobile={() => setIsMobileSidebarOpen(false)}
        isCollapsed={isSidebarCollapsed}
        setIsCollapsed={setIsSidebarCollapsed}
      />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 h-screen overflow-y-auto">
        <Navbar
          marketStatus={marketStatus}
          onToggleMobileSidebar={() => setIsMobileSidebarOpen((prev) => !prev)}
        />

        {/* Main Viewport Container */}
        <main className="flex-1 w-full max-w-[1920px] mx-auto px-3 sm:px-5 lg:px-6 py-4 sm:py-6 pb-24 lg:pb-6">
          <ErrorBoundary fallbackTitle="Dashboard Page Error">
            {activeTab === 'dashboard' && (
              <Dashboard
                marketStatus={marketStatus}
                paperStatus={paperStatus}
                strategyStatus={strategyStatus}
                candles={candles}
                onOpenTrade={handleOpenTrade}
                onCloseTrade={handleCloseTrade}
                onNavigateTab={setActiveTab}
              />
            )}

            {activeTab === 'ai-micro-scalper' && <AIMicroScalper />}

            {activeTab === 'chart' && (
              <LiveChart
                candles={candles}
                marketStatus={marketStatus}
                activePosition={paperStatus?.active_position || null}
              />
            )}

            {activeTab === 'option-chain' && (
              <OptionChain
                onContractSelected={() => {
                  refreshAll();
                  showToast('ATM CE contract updated.', 'info');
                }}
              />
            )}

            {activeTab === 'pcr' && <PCRAnalysis />}

            {activeTab === 'strategy' && <Strategy strategyStatus={strategyStatus} />}

            {activeTab === 'paper-trading' && (
              <PaperTrading
                paperStatus={paperStatus}
                marketStatus={marketStatus}
                onOpenTrade={handleOpenTrade}
                onCloseTrade={handleCloseTrade}
                onResetPaper={handleResetPaper}
              />
            )}

            {activeTab === 'open-positions' && (
              <OpenPositions
                position={paperStatus?.active_position || null}
                onClosePosition={handleCloseTrade}
              />
            )}

            {activeTab === 'trade-history' && <TradeHistory onResetPaper={handleResetPaper} />}

            {activeTab === 'backtesting' && (
              <Backtesting onNavigateToAnalytics={handleNavigateToAnalytics} />
            )}

            {activeTab === 'analytics' && (
              <Analytics initialSource={analyticsSource} initialRunId={analyticsRunId} />
            )}

            {activeTab === 'settings' && <Settings marketStatus={marketStatus} onResetPaper={handleResetPaper} />}
          </ErrorBoundary>
        </main>

        {/* Desktop Footer (Hidden on small mobile where BottomNav sits) */}
        <footer className="border-t border-border/40 py-3 px-4 text-center text-xs font-mono text-gray-500 shrink-0 hidden sm:block">
          NEXTRADE &copy; {new Date().getFullYear()} &mdash; Automated Algorithm &amp; Paper Trading Terminal &bull;
          Paper Trading Mode Only &bull; Kotak Neo Integration
        </footer>

        {/* Mobile Bottom Navigation Bar */}
        <BottomNav
          activeTab={activeTab}
          setActiveTab={(tab) => {
            setActiveTab(tab);
            setIsMobileSidebarOpen(false);
          }}
          onToggleMore={() => setIsMobileSidebarOpen(true)}
          hasActivePosition={!!paperStatus?.active_position}
        />
      </div>

      {/* Toast Notification */}
      {toastMessage && (
        <div className="fixed bottom-6 right-6 z-50">
          <div
            className={`px-4 py-3 rounded-xl shadow-2xl border text-xs font-mono font-semibold flex items-center space-x-2.5 ${
              toastMessage.type === 'success'
                ? 'bg-emerald-950/90 border-emerald-700 text-emerald-200'
                : toastMessage.type === 'warning'
                ? 'bg-amber-950/90 border-amber-700 text-amber-200'
                : 'bg-blue-950/90 border-blue-700 text-blue-200'
            }`}
          >
            {toastMessage.type === 'success' ? (
              <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
            ) : (
              <AlertCircle className="w-4 h-4 text-amber-400 shrink-0" />
            )}
            <span>{toastMessage.text}</span>
          </div>
        </div>
      )}
    </div>
  );
};

export const App: React.FC = () => {
  return (
    <AuthProvider>
      <MainApp />
    </AuthProvider>
  );
};
