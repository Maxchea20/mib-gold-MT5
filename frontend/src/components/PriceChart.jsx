import { useEffect, useRef, useState, useCallback } from "react";
import { createChart, CandlestickSeries, HistogramSeries, createSeriesMarkers, ColorType, CrosshairMode } from "lightweight-charts";
import { api } from "@/lib/api";

const TFS = ["D1", "H4", "H1", "M5"];

export default function PriceChart({ layers = [], barUpdates, tick, title = "XAUUSD" }) {
  const elRef = useRef(null);
  const chartRef = useRef(null);
  const seriesRef = useRef(null);
  const volRef = useRef(null);
  const linesRef = useRef([]);
  const markersRef = useRef(null);
  const lastBarRef = useRef(null);
  const [tf, setTf] = useState("M5");
  const [count, setCount] = useState(0);

  useEffect(() => {
    const chart = createChart(elRef.current, {
      layout: { background: { type: ColorType.Solid, color: "#07090e" }, textColor: "#9ca3af", fontFamily: "JetBrains Mono", fontSize: 10 },
      grid: { vertLines: { color: "rgba(31,41,55,.5)" }, horzLines: { color: "rgba(31,41,55,.5)" } },
      crosshair: { mode: CrosshairMode.Normal, vertLine: { color: "#eab308", width: 1, style: 3 }, horzLine: { color: "#eab308", width: 1, style: 3 } },
      rightPriceScale: { borderColor: "#1f2937" }, timeScale: { borderColor: "#1f2937", timeVisible: true, secondsVisible: false },
      autoSize: true, localization: { locale: "en-US", dateFormat: "yyyy-MM-dd" },
    });
    const s = chart.addSeries(CandlestickSeries, { upColor: "#10b981", downColor: "#ef4444", borderUpColor: "#10b981", borderDownColor: "#ef4444", wickUpColor: "#10b981", wickDownColor: "#ef4444" });
    const v = chart.addSeries(HistogramSeries, { priceFormat: { type: "volume" }, priceScaleId: "vol", color: "rgba(107,114,128,.35)" });
    chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.85, bottom: 0 } });
    chartRef.current = chart; seriesRef.current = s; volRef.current = v;
    markersRef.current = createSeriesMarkers(s, []);
    return () => chart.remove();
  }, []);

  const load = useCallback(async (t) => {
    const d = await api.chart(t, 500);
    seriesRef.current.setData(d.bars.map(({ time, open, high, low, close }) => ({ time, open, high, low, close })));
    volRef.current.setData(d.bars.map((b) => ({ time: b.time, value: b.volume, color: b.close >= b.open ? "rgba(16,185,129,.25)" : "rgba(239,68,68,.25)" })));
    lastBarRef.current = d.bars[d.bars.length - 1] || null;
    setCount(d.bars.length);
    chartRef.current.timeScale().scrollToRealTime();
  }, []);

  useEffect(() => { load(tf); }, [tf, load]);

  // new completed bars pushed from the backend
  useEffect(() => {
    if (!barUpdates?.bars?.[tf]) return;
    for (const b of barUpdates.bars[tf]) {
      if (!lastBarRef.current || b.time >= lastBarRef.current.time) {
        seriesRef.current.update({ time: b.time, open: b.open, high: b.high, low: b.low, close: b.close });
        volRef.current.update({ time: b.time, value: b.volume, color: b.close >= b.open ? "rgba(16,185,129,.25)" : "rgba(239,68,68,.25)" });
        lastBarRef.current = b;
      }
    }
  }, [barUpdates, tf]);

  // live tick paints the forming candle
  useEffect(() => {
    if (!tick || !lastBarRef.current) return;
    const secs = { M5: 300, H1: 3600, H4: 14400, D1: 86400 }[tf];
    const tSec = Math.floor(new Date(tick.time).getTime() / 1000);
    const bucket = Math.floor(tSec / secs) * secs;
    const lb = lastBarRef.current;
    if (bucket > lb.time) {
      const nb = { time: bucket, open: tick.mid, high: tick.mid, low: tick.mid, close: tick.mid, volume: 1 };
      lastBarRef.current = nb; seriesRef.current.update(nb);
    } else if (bucket === lb.time) {
      lb.high = Math.max(lb.high, tick.mid); lb.low = Math.min(lb.low, tick.mid); lb.close = tick.mid;
      seriesRef.current.update({ time: lb.time, open: lb.open, high: lb.high, low: lb.low, close: lb.close });
    }
  }, [tick, tf]);

  // layer entry / SL / trail overlays
  useEffect(() => {
    const s = seriesRef.current; if (!s) return;
    linesRef.current.forEach((l) => s.removePriceLine(l)); linesRef.current = [];
    const markers = [];
    layers.forEach((l) => {
      const c = l.direction === "long" ? "#10b981" : "#ef4444";
      linesRef.current.push(s.createPriceLine({ price: l.entry, color: c, lineWidth: 1, lineStyle: 0, title: `L${l.layer_number} ${l.direction.toUpperCase()} ${l.lots}` }));
      linesRef.current.push(s.createPriceLine({ price: l.sl, color: "#f97316", lineWidth: 1, lineStyle: 2, title: `L${l.layer_number} SL` }));
      if (l.trail_level) linesRef.current.push(s.createPriceLine({ price: l.trail_level, color: "#06b6d4", lineWidth: 1, lineStyle: 3, title: `L${l.layer_number} trail TP` }));
      const t = Math.floor(new Date(l.timestamp).getTime() / 1000);
      const secs = { M5: 300, H1: 3600, H4: 14400, D1: 86400 }[tf];
      markers.push({ time: Math.floor(t / secs) * secs, position: l.direction === "long" ? "belowBar" : "aboveBar", color: c, shape: l.direction === "long" ? "arrowUp" : "arrowDown", text: `L${l.layer_number}` });
    });
    markers.sort((a, b) => a.time - b.time);
    markersRef.current?.setMarkers(markers);
  }, [layers, tf]);

  return (
    <div className="flex flex-col h-full min-h-0" data-testid="gold-chart-container">
      <div className="h-8 flex items-center justify-between px-3 bg-[var(--surface)] border-b border-[var(--hair)]">
        <div className="flex items-center gap-3">
          <span className="mono text-[10px] tracking-[.14em] uppercase text-dim">{title}</span>
          <span className="text-mute text-[10px] mono">{count} bars · {tf}</span>
        </div>
        <div className="flex gap-1">
          {TFS.map((t) => <button key={t} className={`btn ${t === tf ? "active" : ""}`} data-testid={`timeframe-btn-${t}`} onClick={() => setTf(t)}>{t}</button>)}
        </div>
      </div>
      <div ref={elRef} className="flex-1 min-h-0" />
    </div>
  );
}
