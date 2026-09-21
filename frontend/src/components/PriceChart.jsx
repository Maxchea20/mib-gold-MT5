import { useEffect, useRef, useState, useCallback } from "react";
import { createChart, CandlestickSeries, HistogramSeries, createSeriesMarkers, ColorType, CrosshairMode } from "lightweight-charts";
import { api } from "@/lib/api";

const TFS = ["D1", "H4", "H1", "M15", "M5", "M1"];
const SECS = { M1: 60, M5: 300, M15: 900, H1: 3600, H4: 14400, D1: 86400 };

function structureMarks(bars) {
  const k = 2;
  if (!bars || bars.length < k * 2 + 3) return [];
  const highs = [];
  const lows = [];
  for (let i = k; i < bars.length - k; i++) {
    const p = bars[i];
    let isH = true;
    let isL = true;
    for (let j = i - k; j <= i + k; j++) {
      if (bars[j].high > p.high) isH = false;
      if (bars[j].low < p.low) isL = false;
    }
    if (isH) highs.push(p);
    if (isL) lows.push(p);
  }
  const marks = [];
  const hSlice = highs.slice(-24);
  const lSlice = lows.slice(-24);
  hSlice.forEach((h, n) => {
    const prev = n === 0 ? null : hSlice[n - 1];
    const tag = !prev ? "H" : h.high > prev.high ? "HH" : "LH";
    marks.push({ time: h.time, position: "aboveBar", color: tag === "HH" ? "#fbbf24" : "#fdba74", shape: "arrowDown", text: tag });
  });
  lSlice.forEach((l, n) => {
    const prev = n === 0 ? null : lSlice[n - 1];
    const tag = !prev ? "L" : l.low < prev.low ? "LL" : "HL";
    marks.push({ time: l.time, position: "belowBar", color: tag === "LL" ? "#38bdf8" : "#67e8f9", shape: "arrowUp", text: tag });
  });
  if (highs.length >= 2 && lows.length >= 2) {
    const last = bars[bars.length - 1];
    const lastH = highs[highs.length - 1];
    const prevH = highs[highs.length - 2];
    const lastL = lows[lows.length - 1];
    const prevL = lows[lows.length - 2];
    const c = last.close;
    let ev = null;
    let color = "#c084fc";
    if (c > lastH.high && lastL.low < prevL.low) ev = "CHoCH";
    else if (c < lastL.low && lastH.high > prevH.high) ev = "CHoCH";
    else if (c > lastH.high && lastH.high > prevH.high) { ev = "BOS"; color = "#f472b6"; }
    else if (c < lastL.low && lastL.low < prevL.low) { ev = "BOS"; color = "#f472b6"; }
    if (ev) {
      const up = c > lastH.high;
      marks.push({
        time: last.time,
        position: up ? "belowBar" : "aboveBar",
        color,
        shape: "circle",
        text: ev,
      });
    }
  }
  marks.sort((a, b) => a.time - b.time || String(a.text).localeCompare(String(b.text)));
  return marks;
}

export default function PriceChart({ layers = [], barUpdates, tick, title = "XAUUSD", analysis }) {
  const elRef = useRef(null);
  const chartRef = useRef(null);
  const seriesRef = useRef(null);
  const volRef = useRef(null);
  const linesRef = useRef([]);
  const markersRef = useRef(null);
  const lastBarRef = useRef(null);
  const barsRef = useRef([]);
  const [tf, setTf] = useState("M15");
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

  const paintMarks = useCallback((extra = []) => {
    const struct = structureMarks(barsRef.current);
    const all = [...struct, ...extra].sort((a, b) => a.time - b.time);
    markersRef.current?.setMarkers(all);
  }, []);

  const load = useCallback(async (t) => {
    const d = await api.chart(t, 500);
    const mapped = d.bars.map(({ time, open, high, low, close }) => ({ time, open, high, low, close }));
    barsRef.current = mapped;
    seriesRef.current.setData(mapped);
    volRef.current.setData(d.bars.map((b) => ({ time: b.time, value: b.volume, color: b.close >= b.open ? "rgba(16,185,129,.25)" : "rgba(239,68,68,.25)" })));
    lastBarRef.current = d.bars[d.bars.length - 1] || null;
    setCount(d.bars.length);
    paintMarks();
    chartRef.current.timeScale().scrollToRealTime();
  }, [paintMarks]);

  useEffect(() => { load(tf); }, [tf, load]);

  useEffect(() => {
    if (!barUpdates?.bars?.[tf]) return;
    for (const b of barUpdates.bars[tf]) {
      if (!lastBarRef.current || b.time >= lastBarRef.current.time) {
        seriesRef.current.update({ time: b.time, open: b.open, high: b.high, low: b.low, close: b.close });
        volRef.current.update({ time: b.time, value: b.volume, color: b.close >= b.open ? "rgba(16,185,129,.25)" : "rgba(239,68,68,.25)" });
        lastBarRef.current = b;
        const bars = barsRef.current;
        if (bars.length && bars[bars.length - 1].time === b.time) bars[bars.length - 1] = b;
        else bars.push(b);
        paintMarks();
      }
    }
  }, [barUpdates, tf, paintMarks]);

  useEffect(() => {
    if (!tick || !lastBarRef.current) return;
    const secs = SECS[tf];
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

  useEffect(() => {
    const s = seriesRef.current; if (!s) return;
    linesRef.current.forEach((l) => s.removePriceLine(l)); linesRef.current = [];
    const extra = [];
    layers.forEach((l) => {
      const c = l.direction === "long" ? "#10b981" : "#ef4444";
      linesRef.current.push(s.createPriceLine({ price: l.entry, color: c, lineWidth: 1, lineStyle: 0, title: `L${l.layer_number} ${l.direction.toUpperCase()} ${l.lots}` }));
      linesRef.current.push(s.createPriceLine({ price: l.sl, color: "#f97316", lineWidth: 1, lineStyle: 2, title: `L${l.layer_number} SL` }));
      if (l.tp) linesRef.current.push(s.createPriceLine({ price: l.tp, color: "#22c55e", lineWidth: 1, lineStyle: 2, title: `L${l.layer_number} TP` }));
      const t = Math.floor(new Date(l.timestamp).getTime() / 1000);
      const secs = SECS[tf];
      extra.push({ time: Math.floor(t / secs) * secs, position: l.direction === "long" ? "belowBar" : "aboveBar", color: c, shape: l.direction === "long" ? "arrowUp" : "arrowDown", text: `L${l.layer_number}` });
    });
    paintMarks(extra);
  }, [layers, tf, analysis, paintMarks]);

  return (
    <div className="flex flex-col h-full min-h-0" data-testid="gold-chart-container">
      <div className="h-8 flex items-center justify-between px-3 bg-[var(--surface)] border-b border-[var(--hair)]">
        <div className="flex items-center gap-3">
          <span className="mono text-[10px] tracking-[.14em] uppercase text-dim">{title}</span>
          <span className="text-mute text-[10px] mono">{count} bars · {tf} · HH/HL/LL/LH · CHoCH/BOS</span>
        </div>
        <div className="flex gap-1">
          {TFS.map((t) => <button key={t} className={`btn ${t === tf ? "active" : ""}`} data-testid={`timeframe-btn-${t}`} onClick={() => setTf(t)}>{t}</button>)}
        </div>
      </div>
      <div ref={elRef} className="flex-1 min-h-0" />
    </div>
  );
}
