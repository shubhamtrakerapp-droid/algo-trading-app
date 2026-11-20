import React, { useEffect, useRef, useState, useCallback } from 'react';
import {
  createChart,
  IChartApi,
  ISeriesApi,
  LineStyle,
  CrosshairMode,
  UTCTimestamp,
} from 'lightweight-charts';
import {
  ZoomIn,
  ZoomOut,
  RotateCcw,
  Compass,
  ArrowRight,
  MousePointer,
  TrendingUp,
  Minus,
  MoveVertical,
  Square,
  Tag,
  Type,
  Trash2,
  Sliders,
} from 'lucide-react';
import { Candle, PaperPosition, ChartType, ChartTradeMarker } from '../types';

export type DrawingType = 'cursor' | 'trend' | 'horizontal' | 'vertical' | 'rectangle' | 'price_label' | 'text';

interface SvgDrawing {
  id: string;
  type: DrawingType;
  points: { px: number; py: number }[]; // Normalized 0..1 coordinates
  color: string;
  text?: string;
  price?: number;
}

interface ChartComponentProps {
  candles: Candle[];
  activePosition?: PaperPosition | null;
  height?: number;
  chartType?: ChartType;
  symbolName?: string;
  tradeMarkers?: ChartTradeMarker[];
  onSelectMarker?: (marker: ChartTradeMarker) => void;
  onLoadMoreOlderCandles?: () => void;
  isLoadingMore?: boolean;
}

export const ChartComponent: React.FC<ChartComponentProps> = ({
  candles,
  activePosition,
  height = 540,
  chartType = 'candlestick',
  symbolName = 'NIFTY 50',
  tradeMarkers = [],
  onSelectMarker,
  onLoadMoreOlderCandles,
  isLoadingMore = false,
}) => {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const subContainerRef = useRef<HTMLDivElement>(null);
  const overlayRef = useRef<SVGSVGElement>(null);

  const chartRef = useRef<IChartApi | null>(null);
  const subChartRef = useRef<IChartApi | null>(null);

  const mainSeriesRef = useRef<ISeriesApi<any> | null>(null);
  const ema9SeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
  const ema21SeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
  const ema50SeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
  const vwapSeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
  const utStopSeriesRef = useRef<ISeriesApi<'Line'> | null>(null);

  const subSeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
  const entryLineRef = useRef<any>(null);
  const targetLineRef = useRef<any>(null);
  const stopLineRef = useRef<any>(null);

  const [initError, setInitError] = useState<string | null>(null);
  const [crosshairMagnet, setCrosshairMagnet] = useState(false);
  const [subChartMode, setSubChartMode] = useState<'rsi' | 'atr'>('rsi');

  // Indicators visibility state
  const [indicators, setIndicators] = useState({
    ema9: true,
    ema21: true,
    ema50: true,
    vwap: true,
    utStop: true,
    subChart: true,
  });

  // Drawing tools state
  const [activeTool, setActiveTool] = useState<DrawingType>('cursor');
  const [drawings, setDrawings] = useState<SvgDrawing[]>(() => {
    try {
      const saved = localStorage.getItem('nextrade_chart_drawings');
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });
  const [isDrawing, setIsDrawing] = useState(false);
  const [currentPoints, setCurrentPoints] = useState<{ px: number; py: number }[]>([]);

  // Persist drawings to localStorage
  useEffect(() => {
    try {
      localStorage.setItem('nextrade_chart_drawings', JSON.stringify(drawings));
    } catch (e) {
      console.error('Failed to save drawings:', e);
    }
  }, [drawings]);

  // 1. Initialize Main and Sub Charts
  useEffect(() => {
    if (!chartContainerRef.current) return;

    try {
      const containerWidth = chartContainerRef.current.clientWidth || 800;
      const mainChartHeight = indicators.subChart ? Math.max(300, height - 140) : height;

      // Create main TradingView chart
      const chart = createChart(chartContainerRef.current, {
        width: containerWidth,
        height: mainChartHeight,
        layout: {
          background: { color: '#0b0e14' },
          textColor: '#9ca3af',
          fontFamily: "'JetBrains Mono', monospace",
        },
        grid: {
          vertLines: { color: '#141a24' },
          horzLines: { color: '#141a24' },
        },
        handleScroll: {
          mouseWheel: true,
          pressedMouseMove: true,
          horzTouchDrag: true,
          vertTouchDrag: true,
        },
        handleScale: {
          axisPressedMouseMove: {
            time: true,
            price: true,
          },
          mouseWheel: true,
          pinch: true,
        },
        timeScale: {
          borderColor: '#232b3b',
          timeVisible: true,
          secondsVisible: false,
          rightOffset: 12,
          barSpacing: 10,
          minBarSpacing: 2,
          fixLeftEdge: false,
          fixRightEdge: false,
        },
        rightPriceScale: {
          borderColor: '#232b3b',
          autoScale: true,
          scaleMargins: {
            top: 0.12,
            bottom: 0.15,
          },
        },
        crosshair: {
          mode: CrosshairMode.Normal,
          vertLine: {
            color: '#3b82f6',
            width: 1,
            style: LineStyle.Dotted,
            labelBackgroundColor: '#181f2c',
          },
          horzLine: {
            color: '#3b82f6',
            width: 1,
            style: LineStyle.Dotted,
            labelBackgroundColor: '#181f2c',
          },
        },
      });

      // Add main series depending on chartType
      let mainSeries: ISeriesApi<any>;
      if (chartType === 'bar') {
        mainSeries = chart.addBarSeries({
          upColor: '#10b981',
          downColor: '#ef4444',
        });
      } else if (chartType === 'line') {
        mainSeries = chart.addLineSeries({
          color: '#3b82f6',
          lineWidth: 2,
        });
      } else if (chartType === 'area') {
        mainSeries = chart.addAreaSeries({
          topColor: 'rgba(59, 130, 246, 0.4)',
          bottomColor: 'rgba(59, 130, 246, 0.02)',
          lineColor: '#3b82f6',
          lineWidth: 2,
        });
      } else {
        // 'candlestick' or 'heikin_ashi'
        mainSeries = chart.addCandlestickSeries({
          upColor: '#10b981',
          downColor: '#ef4444',
          borderUpColor: '#10b981',
          borderDownColor: '#ef4444',
          wickUpColor: '#10b981',
          wickDownColor: '#ef4444',
        });
      }

      // Add Indicator Series
      const ema9Series = chart.addLineSeries({
        color: '#eab308',
        lineWidth: 1,
        title: 'EMA 9',
      });
      const ema21Series = chart.addLineSeries({
        color: '#06b6d4',
        lineWidth: 1,
        title: 'EMA 21',
      });
      const ema50Series = chart.addLineSeries({
        color: '#a855f7',
        lineWidth: 2,
        title: 'EMA 50',
      });
      const vwapSeries = chart.addLineSeries({
        color: '#f97316',
        lineWidth: 1,
        title: 'VWAP',
      });
      const utStopSeries = chart.addLineSeries({
        color: '#f59e0b',
        lineWidth: 2,
        lineStyle: LineStyle.Solid,
        title: 'UT Stop',
      });

      chartRef.current = chart;
      mainSeriesRef.current = mainSeries;
      ema9SeriesRef.current = ema9Series;
      ema21SeriesRef.current = ema21Series;
      ema50SeriesRef.current = ema50Series;
      vwapSeriesRef.current = vwapSeries;
      utStopSeriesRef.current = utStopSeries;

      // 2. Initialize Sub-Chart (RSI / ATR)
      if (indicators.subChart && subContainerRef.current) {
        const subChart = createChart(subContainerRef.current, {
          width: containerWidth,
          height: 125,
          layout: {
            background: { color: '#0b0e14' },
            textColor: '#9ca3af',
            fontFamily: "'JetBrains Mono', monospace",
          },
          grid: {
            vertLines: { color: '#141a24' },
            horzLines: { color: '#141a24' },
          },
          handleScroll: {
            mouseWheel: true,
            pressedMouseMove: true,
            horzTouchDrag: true,
          },
          handleScale: {
            mouseWheel: true,
            pinch: true,
          },
          timeScale: {
            borderColor: '#232b3b',
            timeVisible: true,
            visible: true,
          },
          rightPriceScale: {
            borderColor: '#232b3b',
            scaleMargins: { top: 0.1, bottom: 0.1 },
          },
        });

        const subSeries = subChart.addLineSeries({
          color: subChartMode === 'rsi' ? '#3b82f6' : '#10b981',
          lineWidth: 2,
          title: subChartMode === 'rsi' ? 'RSI 14' : 'ATR 10',
        });

        if (subChartMode === 'rsi') {
          subSeries.createPriceLine({
            price: 50.0,
            color: '#f59e0b',
            lineWidth: 1,
            lineStyle: LineStyle.Dashed,
            axisLabelVisible: true,
            title: 'SIGNAL (50)',
          });
        }

        subChartRef.current = subChart;
        subSeriesRef.current = subSeries;

        // Mutual time sync
        let isSyncing = false;
        chart.timeScale().subscribeVisibleTimeRangeChange((range) => {
          if (isSyncing || !range || !subChartRef.current) return;
          isSyncing = true;
          try {
            subChartRef.current.timeScale().setVisibleRange(range);
          } catch {} finally {
            isSyncing = false;
          }
        });

        subChart.timeScale().subscribeVisibleTimeRangeChange((range) => {
          if (isSyncing || !range || !chartRef.current) return;
          isSyncing = true;
          try {
            chartRef.current.timeScale().setVisibleRange(range);
          } catch {} finally {
            isSyncing = false;
          }
        });
      }

      // Trade marker click detection
      chart.subscribeClick((param) => {
        if (!param || !param.time || !onSelectMarker || !tradeMarkers || tradeMarkers.length === 0) return;
        const clickedTime = param.time as number;
        // Find matching marker within 180s tolerance for multi-timeframe bars
        const match = tradeMarkers.find((m) => Math.abs(m.time - clickedTime) <= 180);
        if (match) {
          onSelectMarker(match);
        }
      });

      // Backward infinite scroll lazy-loading
      chart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
        if (!range || !onLoadMoreOlderCandles || isLoadingMore) return;
        if (range.from < 5) {
          onLoadMoreOlderCandles();
        }
      });

      const handleResize = () => {
        if (chartContainerRef.current && chartRef.current) {
          const w = chartContainerRef.current.clientWidth;
          if (w > 0) chartRef.current.applyOptions({ width: w });
        }
        if (subContainerRef.current && subChartRef.current) {
          const w = subContainerRef.current.clientWidth;
          if (w > 0) subChartRef.current.applyOptions({ width: w });
        }
      };
      window.addEventListener('resize', handleResize);

      return () => {
        window.removeEventListener('resize', handleResize);
        try {
          chart.remove();
        } catch {}
        try {
          if (subChartRef.current) subChartRef.current.remove();
        } catch {}
      };
    } catch (e: any) {
      console.error('Error creating charts:', e);
      setInitError(e.message || 'Failed to initialize chart');
    }
  }, [height, chartType, indicators.subChart, subChartMode]);

  // Update Data, Indicators, and Markers
  useEffect(() => {
    if (!candles || candles.length === 0 || !mainSeriesRef.current) return;

    try {
      const sortedCandles = [...candles].sort((a, b) => a.timestamp - b.timestamp);
      const uniqueCandles: Candle[] = [];
      const seenTimes = new Set<number>();

      for (const c of sortedCandles) {
        if (c.timestamp && !seenTimes.has(c.timestamp)) {
          seenTimes.add(c.timestamp);
          uniqueCandles.push(c);
        }
      }

      // Format main series data based on chart type
      if (chartType === 'line' || chartType === 'area') {
        const lineData = uniqueCandles.map((c) => ({
          time: c.timestamp as UTCTimestamp,
          value: c.close,
        }));
        mainSeriesRef.current.setData(lineData);
      } else if (chartType === 'heikin_ashi') {
        const haData = uniqueCandles.map((c) => ({
          time: c.timestamp as UTCTimestamp,
          open: c.ha_open ?? c.open,
          high: c.ha_high ?? c.high,
          low: c.ha_low ?? c.low,
          close: c.ha_close ?? c.close,
        }));
        mainSeriesRef.current.setData(haData);
      } else {
        // Candlestick & Bar
        const barData = uniqueCandles.map((c) => ({
          time: c.timestamp as UTCTimestamp,
          open: c.open,
          high: c.high,
          low: c.low,
          close: c.close,
        }));
        mainSeriesRef.current.setData(barData);
      }

      // Update Indicators
      if (ema9SeriesRef.current) {
        ema9SeriesRef.current.setData(
          indicators.ema9
            ? uniqueCandles.filter((c) => c.ema_9).map((c) => ({ time: c.timestamp as UTCTimestamp, value: c.ema_9 }))
            : []
        );
      }
      if (ema21SeriesRef.current) {
        ema21SeriesRef.current.setData(
          indicators.ema21
            ? uniqueCandles.filter((c) => c.ema_21).map((c) => ({ time: c.timestamp as UTCTimestamp, value: c.ema_21 }))
            : []
        );
      }
      if (ema50SeriesRef.current) {
        ema50SeriesRef.current.setData(
          indicators.ema50
            ? uniqueCandles.filter((c) => c.ema_50).map((c) => ({ time: c.timestamp as UTCTimestamp, value: c.ema_50 }))
            : []
        );
      }
      if (vwapSeriesRef.current) {
        vwapSeriesRef.current.setData(
          indicators.vwap
            ? uniqueCandles.filter((c) => c.vwap).map((c) => ({ time: c.timestamp as UTCTimestamp, value: c.vwap }))
            : []
        );
      }
      if (utStopSeriesRef.current) {
        utStopSeriesRef.current.setData(
          indicators.utStop
            ? uniqueCandles
                .filter((c) => c.trailing_stop !== undefined && c.trailing_stop !== null && c.trailing_stop > 0)
                .map((c) => ({ time: c.timestamp as UTCTimestamp, value: c.trailing_stop! }))
            : []
        );
      }

      // Update Sub-Chart (RSI or ATR)
      if (subSeriesRef.current && indicators.subChart) {
        if (subChartMode === 'rsi') {
          subSeriesRef.current.setData(
            uniqueCandles.filter((c) => c.rsi_14).map((c) => ({ time: c.timestamp as UTCTimestamp, value: c.rsi_14 }))
          );
        } else {
          subSeriesRef.current.setData(
            uniqueCandles
              .filter((c) => c.atr !== undefined && c.atr !== null)
              .map((c) => ({ time: c.timestamp as UTCTimestamp, value: c.atr! }))
          );
        }
      }

      // Confirmed Signal & Trade Execution Markers
      const markers: any[] = [];
      if (tradeMarkers && tradeMarkers.length > 0) {
        tradeMarkers.forEach((tm) => {
          markers.push({
            time: tm.time as UTCTimestamp,
            position: tm.position,
            color: tm.color,
            shape: tm.shape,
            text: tm.text,
            id: tm.id,
          });
        });
      } else {
        uniqueCandles.forEach((c) => {
          if (c.signal_type === 'BUY' || (c as any).is_ut_buy) {
            markers.push({
              time: c.timestamp as UTCTimestamp,
              position: 'belowBar',
              color: '#10b981',
              shape: 'arrowUp',
              text: 'BUY',
            });
          } else if (c.signal_type === 'SELL' || (c as any).is_ut_sell) {
            markers.push({
              time: c.timestamp as UTCTimestamp,
              position: 'aboveBar',
              color: '#ef4444',
              shape: 'arrowDown',
              text: 'SELL',
            });
          }
        });
      }

      markers.sort((a, b) => a.time - b.time);

      if (mainSeriesRef.current.setMarkers) {
        mainSeriesRef.current.setMarkers(markers);
      }
    } catch (e) {
      console.error('Error updating chart data:', e);
    }
  }, [candles, chartType, indicators, subChartMode, tradeMarkers]);

  // Update Entry, Target and Stop Price Lines
  useEffect(() => {
    if (!mainSeriesRef.current) return;

    try {
      if (entryLineRef.current) {
        mainSeriesRef.current.removePriceLine(entryLineRef.current);
        entryLineRef.current = null;
      }
      if (targetLineRef.current) {
        mainSeriesRef.current.removePriceLine(targetLineRef.current);
        targetLineRef.current = null;
      }
      if (stopLineRef.current) {
        mainSeriesRef.current.removePriceLine(stopLineRef.current);
        stopLineRef.current = null;
      }

      if (activePosition && activePosition.status === 'OPEN') {
        entryLineRef.current = mainSeriesRef.current.createPriceLine({
          price: activePosition.entry_price,
          color: '#3b82f6',
          lineWidth: 2,
          lineStyle: LineStyle.Solid,
          axisLabelVisible: true,
          title: `ENTRY ₹${activePosition.entry_price.toFixed(2)}`,
        });

        targetLineRef.current = mainSeriesRef.current.createPriceLine({
          price: activePosition.target_price,
          color: '#10b981',
          lineWidth: 2,
          lineStyle: LineStyle.Dashed,
          axisLabelVisible: true,
          title: `TARGET (+${activePosition.configured_target_points ?? 4.0}) ₹${activePosition.target_price.toFixed(2)}`,
        });

        stopLineRef.current = mainSeriesRef.current.createPriceLine({
          price: activePosition.stop_price,
          color: '#ef4444',
          lineWidth: 2,
          lineStyle: LineStyle.Dashed,
          axisLabelVisible: true,
          title: `STOP (-${activePosition.effective_stop_distance ?? activePosition.configured_sl_points ?? 2.0}) ₹${activePosition.stop_price.toFixed(2)}`,
        });
      }
    } catch (e) {
      console.error('Error setting price lines:', e);
    }
  }, [activePosition]);

  // TradingView Interactive Navigation Handlers
  const handleZoomIn = () => {
    if (!chartRef.current) return;
    const timeScale = chartRef.current.timeScale();
    const currentRange = timeScale.getVisibleLogicalRange();
    if (currentRange) {
      const barsCount = currentRange.to - currentRange.from;
      const zoomFactor = barsCount * 0.2;
      timeScale.setVisibleLogicalRange({
        from: currentRange.from + zoomFactor,
        to: currentRange.to - zoomFactor,
      });
    }
  };

  const handleZoomOut = () => {
    if (!chartRef.current) return;
    const timeScale = chartRef.current.timeScale();
    const currentRange = timeScale.getVisibleLogicalRange();
    if (currentRange) {
      const barsCount = currentRange.to - currentRange.from;
      const zoomFactor = barsCount * 0.25;
      timeScale.setVisibleLogicalRange({
        from: currentRange.from - zoomFactor,
        to: currentRange.to + zoomFactor,
      });
    }
  };

  const handleResetView = () => {
    if (!chartRef.current) return;
    chartRef.current.timeScale().fitContent();
    chartRef.current.priceScale('right').applyOptions({ autoScale: true });
  };

  const handleScrollToRealtime = () => {
    if (!chartRef.current) return;
    chartRef.current.timeScale().scrollToRealTime();
  };

  const toggleCrosshairMode = () => {
    if (!chartRef.current) return;
    const newMagnet = !crosshairMagnet;
    setCrosshairMagnet(newMagnet);
    chartRef.current.applyOptions({
      crosshair: {
        mode: newMagnet ? CrosshairMode.Magnet : CrosshairMode.Normal,
      },
    });
  };

  // Drawing Tools Mouse Handlers
  const getCoordinates = useCallback((e: React.MouseEvent<SVGSVGElement>) => {
    if (!overlayRef.current) return { px: 0, py: 0 };
    const rect = overlayRef.current.getBoundingClientRect();
    const x = Math.max(0, Math.min(e.clientX - rect.left, rect.width));
    const y = Math.max(0, Math.min(e.clientY - rect.top, rect.height));
    return {
      px: x / rect.width,
      py: y / rect.height,
    };
  }, []);

  const handleMouseDown = (e: React.MouseEvent<SVGSVGElement>) => {
    if (activeTool === 'cursor') return;
    const coords = getCoordinates(e);

    if (activeTool === 'horizontal' || activeTool === 'vertical' || activeTool === 'price_label') {
      // Single-point drawings
      const newDrawing: SvgDrawing = {
        id: `draw_${Date.now()}`,
        type: activeTool,
        points: [coords],
        color: activeTool === 'price_label' ? '#3b82f6' : '#f59e0b',
        text: activeTool === 'price_label' ? 'PRICE' : undefined,
      };
      setDrawings((prev) => [...prev, newDrawing]);
      setActiveTool('cursor');
    } else if (activeTool === 'text') {
      const userText = window.prompt('Enter annotation text:', 'Key Level / Breakout');
      if (userText) {
        const newDrawing: SvgDrawing = {
          id: `draw_${Date.now()}`,
          type: 'text',
          points: [coords],
          color: '#38bdf8',
          text: userText,
        };
        setDrawings((prev) => [...prev, newDrawing]);
      }
      setActiveTool('cursor');
    } else {
      // Two-point drag drawings ('trend', 'rectangle')
      setIsDrawing(true);
      setCurrentPoints([coords]);
    }
  };

  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!isDrawing || activeTool === 'cursor') return;
    const coords = getCoordinates(e);
    if (currentPoints.length === 1) {
      setCurrentPoints([currentPoints[0], coords]);
    } else if (currentPoints.length === 2) {
      setCurrentPoints([currentPoints[0], coords]);
    }
  };

  const handleMouseUp = () => {
    if (!isDrawing) return;
    if (currentPoints.length === 2) {
      const newDrawing: SvgDrawing = {
        id: `draw_${Date.now()}`,
        type: activeTool,
        points: currentPoints,
        color: activeTool === 'trend' ? '#38bdf8' : '#a855f7',
      };
      setDrawings((prev) => [...prev, newDrawing]);
    }
    setIsDrawing(false);
    setCurrentPoints([]);
    setActiveTool('cursor');
  };

  const handleClearDrawings = () => {
    setDrawings([]);
    try {
      localStorage.removeItem('nextrade_chart_drawings');
    } catch {}
  };

  if (initError) {
    return (
      <div className="p-8 text-center text-xs font-mono text-gray-400 bg-surface rounded-xl border border-border">
        Chart loading error: {initError}
      </div>
    );
  }

  return (
    <div className="flex flex-col w-full bg-background rounded-xl border border-border overflow-hidden">
      {/* Top TradingView Toolbar */}
      <div className="px-4 py-2.5 bg-surface/80 border-b border-border flex flex-wrap items-center justify-between gap-2 text-xs font-mono">
        {/* Left: Indicator Toggle Pills */}
        <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
          <span className="text-gray-400 font-semibold uppercase mr-1">{symbolName}</span>

          <button
            onClick={() => setIndicators((prev) => ({ ...prev, ema9: !prev.ema9 }))}
            className={`px-2 py-0.5 rounded border transition-colors flex items-center gap-1 ${
              indicators.ema9
                ? 'bg-yellow-500/20 border-yellow-500 text-yellow-300'
                : 'bg-card border-border/60 text-gray-500 hover:text-gray-300'
            }`}
          >
            <span className="w-1.5 h-1.5 rounded-full bg-yellow-400 inline-block" /> EMA 9
          </button>

          <button
            onClick={() => setIndicators((prev) => ({ ...prev, ema21: !prev.ema21 }))}
            className={`px-2 py-0.5 rounded border transition-colors flex items-center gap-1 ${
              indicators.ema21
                ? 'bg-cyan-500/20 border-cyan-500 text-cyan-300'
                : 'bg-card border-border/60 text-gray-500 hover:text-gray-300'
            }`}
          >
            <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 inline-block" /> EMA 21
          </button>

          <button
            onClick={() => setIndicators((prev) => ({ ...prev, ema50: !prev.ema50 }))}
            className={`px-2 py-0.5 rounded border transition-colors flex items-center gap-1 ${
              indicators.ema50
                ? 'bg-purple-500/20 border-purple-500 text-purple-300'
                : 'bg-card border-border/60 text-gray-500 hover:text-gray-300'
            }`}
          >
            <span className="w-1.5 h-1.5 rounded-full bg-purple-400 inline-block" /> EMA 50
          </button>

          <button
            onClick={() => setIndicators((prev) => ({ ...prev, vwap: !prev.vwap }))}
            className={`px-2 py-0.5 rounded border transition-colors flex items-center gap-1 ${
              indicators.vwap
                ? 'bg-orange-500/20 border-orange-500 text-orange-300'
                : 'bg-card border-border/60 text-gray-500 hover:text-gray-300'
            }`}
          >
            <span className="w-1.5 h-1.5 rounded-full bg-orange-400 inline-block" /> VWAP
          </button>

          <button
            onClick={() => setIndicators((prev) => ({ ...prev, utStop: !prev.utStop }))}
            className={`px-2 py-0.5 rounded border transition-colors flex items-center gap-1 ${
              indicators.utStop
                ? 'bg-amber-500/20 border-amber-500 text-amber-300'
                : 'bg-card border-border/60 text-gray-500 hover:text-gray-300'
            }`}
          >
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400 inline-block" /> UT Stop
          </button>

          <button
            onClick={() => setIndicators((prev) => ({ ...prev, subChart: !prev.subChart }))}
            className={`px-2 py-0.5 rounded border transition-colors flex items-center gap-1 ${
              indicators.subChart
                ? 'bg-blue-500/20 border-blue-500 text-blue-300'
                : 'bg-card border-border/60 text-gray-500 hover:text-gray-300'
            }`}
          >
            <Sliders className="w-3 h-3" /> Sub-Chart
          </button>
        </div>

        {/* Right: TradingView Interaction & Scale Buttons */}
        <div className="flex items-center space-x-1.5">
          <button
            onClick={handleZoomIn}
            title="Zoom In"
            className="p-1.5 rounded hover:bg-card border border-border/60 text-gray-300 hover:text-white transition-colors"
          >
            <ZoomIn className="w-3.5 h-3.5" />
          </button>

          <button
            onClick={handleZoomOut}
            title="Zoom Out"
            className="p-1.5 rounded hover:bg-card border border-border/60 text-gray-300 hover:text-white transition-colors"
          >
            <ZoomOut className="w-3.5 h-3.5" />
          </button>

          <button
            onClick={handleResetView}
            title="Reset Scale / Fit Content"
            className="p-1.5 rounded hover:bg-card border border-border/60 text-gray-300 hover:text-white transition-colors"
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>

          <button
            onClick={handleScrollToRealtime}
            title="Scroll to Latest Candle"
            className="p-1.5 rounded hover:bg-card border border-border/60 text-gray-300 hover:text-white transition-colors flex items-center gap-1 text-[11px]"
          >
            <ArrowRight className="w-3.5 h-3.5 text-blue-400" />
            <span className="hidden md:inline">Latest</span>
          </button>

          <button
            onClick={toggleCrosshairMode}
            title={`Crosshair Mode: ${crosshairMagnet ? 'Magnet (Snaps to price)' : 'Free Movement'}`}
            className={`p-1.5 rounded border text-[11px] transition-colors flex items-center gap-1 ${
              crosshairMagnet
                ? 'bg-blue-600/20 border-blue-500/50 text-blue-300'
                : 'hover:bg-card border-border/60 text-gray-400 hover:text-white'
            }`}
          >
            <Compass className="w-3.5 h-3.5" />
            <span className="hidden md:inline">{crosshairMagnet ? 'Magnet' : 'Crosshair'}</span>
          </button>
        </div>
      </div>

      {/* Main Chart Area with Drawing Sidebar and Canvas */}
      <div className="flex w-full relative">
        {/* Left Drawing Tools Vertical Toolbar */}
        <div className="w-10 bg-surface/50 border-r border-border flex flex-col items-center py-2 space-y-1 z-10 shrink-0">
          <button
            onClick={() => setActiveTool('cursor')}
            title="Cursor / Pan Mode"
            className={`p-1.5 rounded transition-colors ${
              activeTool === 'cursor' ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-white hover:bg-card'
            }`}
          >
            <MousePointer className="w-4 h-4" />
          </button>

          <button
            onClick={() => setActiveTool('trend')}
            title="Trend Line (Click and drag)"
            className={`p-1.5 rounded transition-colors ${
              activeTool === 'trend' ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-white hover:bg-card'
            }`}
          >
            <TrendingUp className="w-4 h-4" />
          </button>

          <button
            onClick={() => setActiveTool('horizontal')}
            title="Horizontal Line (Click chart)"
            className={`p-1.5 rounded transition-colors ${
              activeTool === 'horizontal' ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-white hover:bg-card'
            }`}
          >
            <Minus className="w-4 h-4" />
          </button>

          <button
            onClick={() => setActiveTool('vertical')}
            title="Vertical Line (Click chart)"
            className={`p-1.5 rounded transition-colors ${
              activeTool === 'vertical' ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-white hover:bg-card'
            }`}
          >
            <MoveVertical className="w-4 h-4" />
          </button>

          <button
            onClick={() => setActiveTool('rectangle')}
            title="Rectangle (Click and drag)"
            className={`p-1.5 rounded transition-colors ${
              activeTool === 'rectangle' ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-white hover:bg-card'
            }`}
          >
            <Square className="w-4 h-4" />
          </button>

          <button
            onClick={() => setActiveTool('price_label')}
            title="Price Tag (Click chart)"
            className={`p-1.5 rounded transition-colors ${
              activeTool === 'price_label' ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-white hover:bg-card'
            }`}
          >
            <Tag className="w-4 h-4" />
          </button>

          <button
            onClick={() => setActiveTool('text')}
            title="Text Note (Click chart)"
            className={`p-1.5 rounded transition-colors ${
              activeTool === 'text' ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-white hover:bg-card'
            }`}
          >
            <Type className="w-4 h-4" />
          </button>

          <div className="w-6 border-b border-border my-1" />

          {drawings.length > 0 && (
            <button
              onClick={handleClearDrawings}
              title="Clear All Drawings"
              className="p-1.5 rounded text-red-400 hover:text-red-300 hover:bg-red-500/10 transition-colors"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          )}
        </div>

        {/* Chart Canvas & SVG Overlay */}
        <div className="relative flex-1 min-h-[300px] overflow-hidden">
          <div ref={chartContainerRef} className="w-full h-full cursor-crosshair" />

          {/* SVG Drawing Layer */}
          <svg
            ref={overlayRef}
            className={`absolute inset-0 w-full h-full ${
              activeTool === 'cursor' ? 'pointer-events-none' : 'pointer-events-auto cursor-crosshair'
            }`}
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
          >
            {/* Existing Persisted Drawings */}
            {drawings.map((d) => {
              if (d.type === 'trend' && d.points.length >= 2) {
                return (
                  <line
                    key={d.id}
                    x1={`${d.points[0].px * 100}%`}
                    y1={`${d.points[0].py * 100}%`}
                    x2={`${d.points[1].px * 100}%`}
                    y2={`${d.points[1].py * 100}%`}
                    stroke={d.color}
                    strokeWidth="2"
                    strokeDasharray="4,4"
                  />
                );
              }
              if (d.type === 'horizontal' && d.points.length >= 1) {
                return (
                  <g key={d.id}>
                    <line
                      x1="0%"
                      y1={`${d.points[0].py * 100}%`}
                      x2="100%"
                      y2={`${d.points[0].py * 100}%`}
                      stroke={d.color}
                      strokeWidth="1.5"
                      strokeDasharray="5,5"
                    />
                    <text
                      x="98%"
                      y={`${d.points[0].py * 100}%`}
                      fill={d.color}
                      fontSize="10"
                      textAnchor="end"
                      dy="-4"
                      className="font-mono select-none"
                    >
                      LEVEL
                    </text>
                  </g>
                );
              }
              if (d.type === 'vertical' && d.points.length >= 1) {
                return (
                  <line
                    key={d.id}
                    x1={`${d.points[0].px * 100}%`}
                    y1="0%"
                    x2={`${d.points[0].px * 100}%`}
                    y2="100%"
                    stroke={d.color}
                    strokeWidth="1.5"
                    strokeDasharray="5,5"
                  />
                );
              }
              if (d.type === 'rectangle' && d.points.length >= 2) {
                const x = Math.min(d.points[0].px, d.points[1].px) * 100;
                const y = Math.min(d.points[0].py, d.points[1].py) * 100;
                const w = Math.abs(d.points[1].px - d.points[0].px) * 100;
                const h = Math.abs(d.points[1].py - d.points[0].py) * 100;
                return (
                  <rect
                    key={d.id}
                    x={`${x}%`}
                    y={`${y}%`}
                    width={`${w}%`}
                    height={`${h}%`}
                    stroke={d.color}
                    strokeWidth="1.5"
                    fill={d.color}
                    fillOpacity="0.15"
                  />
                );
              }
              if (d.type === 'price_label' && d.points.length >= 1) {
                return (
                  <g key={d.id} transform={`translate(${d.points[0].px * 100}%, ${d.points[0].py * 100}%)`}>
                    <rect x="5" y="-12" width="60" height="20" rx="3" fill="#1e293b" stroke={d.color} strokeWidth="1" />
                    <text x="12" y="2" fill="#fff" fontSize="10" className="font-mono select-none">
                      {d.text || 'LABEL'}
                    </text>
                  </g>
                );
              }
              if (d.type === 'text' && d.points.length >= 1) {
                return (
                  <text
                    key={d.id}
                    x={`${d.points[0].px * 100}%`}
                    y={`${d.points[0].py * 100}%`}
                    fill={d.color}
                    fontSize="11"
                    className="font-mono select-none font-semibold"
                    dy="-6"
                  >
                    {d.text}
                  </text>
                );
              }
              return null;
            })}

            {/* In-progress Drag Preview */}
            {isDrawing && currentPoints.length >= 2 && (
              <>
                {activeTool === 'trend' && (
                  <line
                    x1={`${currentPoints[0].px * 100}%`}
                    y1={`${currentPoints[0].py * 100}%`}
                    x2={`${currentPoints[1].px * 100}%`}
                    y2={`${currentPoints[1].py * 100}%`}
                    stroke="#38bdf8"
                    strokeWidth="2"
                    strokeDasharray="3,3"
                  />
                )}
                {activeTool === 'rectangle' && (
                  <rect
                    x={`${Math.min(currentPoints[0].px, currentPoints[1].px) * 100}%`}
                    y={`${Math.min(currentPoints[0].py, currentPoints[1].py) * 100}%`}
                    width={`${Math.abs(currentPoints[1].px - currentPoints[0].px) * 100}%`}
                    height={`${Math.abs(currentPoints[1].py - currentPoints[0].py) * 100}%`}
                    stroke="#a855f7"
                    strokeWidth="1.5"
                    fill="#a855f7"
                    fillOpacity="0.2"
                  />
                )}
              </>
            )}
          </svg>
        </div>
      </div>

      {/* Sub-Chart (RSI or ATR) Panel */}
      {indicators.subChart && (
        <div className="flex flex-col border-t border-border">
          <div className="px-4 py-1.5 bg-surface/50 border-b border-border flex items-center justify-between text-[11px] font-mono text-gray-400">
            <div className="flex items-center space-x-3">
              <span className="font-semibold text-gray-300">
                {subChartMode === 'rsi' ? 'RSI (14) MOMENTUM PANEL' : 'ATR (10) VOLATILITY PANEL'}
              </span>
              <button
                onClick={() => setSubChartMode((m) => (m === 'rsi' ? 'atr' : 'rsi'))}
                className="px-2 py-0.5 rounded bg-card hover:bg-surface border border-border text-[10px] text-blue-400 transition-colors"
              >
                Switch to {subChartMode === 'rsi' ? 'ATR (10)' : 'RSI (14)'}
              </button>
            </div>
            {subChartMode === 'rsi' && <span className="text-amber-400">SIGNAL THRESHOLD: &gt; 50.0</span>}
          </div>
          <div ref={subContainerRef} className="w-full min-h-[125px]" />
        </div>
      )}
    </div>
  );
};
