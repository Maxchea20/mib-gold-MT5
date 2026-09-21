import { useEffect, useRef, useState, useCallback } from "react";
import { createChart, CandlestickSeries, HistogramSeries, createSeriesMarkers, ColorType, CrosshairMode } from "lightweight-charts";
import { api } from "@/lib/api";

const TFS = ["D1", "H4", "H1", "M15", "M5", "M1"];
const SECS = { M1: 60, M5: 300, M15: 900, H1: 3600, H4: 14400, D1: 86400 };

function structureScan(bars) {
  const k = 2;
  const marks = [];
  const lines = [];
  if (!bars || bars.length < k * 2 + 5) return { marks, lines };
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
  const hSlice = highs.slice(-20);
  const lSlice = lows.slice(-20);
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
  const events = [];
  let usedUp = null;
  let usedDn = null;
  for (let i = 0; i < bars.length; i++) {
    const bar = bars[i];
    const hs = highs.filter((h) => h.time < bar.time);
    const ls = lows.filter((l) => l.time < bar.time);
    if (hs.length < 2 || ls.length < 2) continue;
    const lastH = hs[hs.length - 1];
    const prevH = hs[hs.length - 2];
    const lastL = ls[ls.length - 1];
    const prevL = ls[ls.length - 2];
    const c = bar.close;
    if (c > lastH.high && lastH.high !== usedUp) {
      const choch = lastL.low < prevL.low;
      events.push({ time: bar.time, ev: choch ? "CHoCH" : "BOS", up: true, price: lastH.high });
      usedUp = lastH.high;
    }
    if (c < lastL.low && lastL.low !== usedDn) {
      const choch = lastH.high > prevH.high;
      events.push({ time: bar.time, ev: choch ? "CHoCH" : "BOS", up: false, price: lastL.low });
      usedDn = lastL.low;
    }
  }
  events.forEach((e) => {
    marks.push({
      time: e.time,
      position: e.up ? "belowBar" : "aboveBar",
      color: e.ev === "CHoCH" ? "#c084fc" : "#f472b6",
      shape: "circle",
      text: e.ev,
    });
  });
  events.slice(-4).forEach((e) => {
    lines.push({
      price: e.price,
      color: e.ev === "CHoCH" ? "#c084fc" : "#f472b6",
      title: `${e.ev} ${e.price.toFixed(2)}`,
    });
  });
  marks.sort((a, b) => a.time - b.time || String(a.text).localeCompare(String(b.text)));
  return { marks, lines };
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

  const paint = useCallback((extra = []) => {
    const s = seriesRef.current;
    if (!s) return;
    const scan = structureScan(barsRef.current);
    const all = [...scan.marks, ...extra].sort((a, b) => a.time - b.time);
    markersRef.current?.setMarkers(all);
    linesRef.current.forEach((l) => s.removePriceLine(l));
    linesRef.current = [];
    scan.lines.forEach((ln) => {
      linesRef.current.push(s.createPriceLine({
        price: ln.price, color: ln.color, lineWidth: 1, lineStyle: 2, title: ln.title,
      }));
    });
  }, []);

  const load = useCallback(async (t) => {
    const d = await api.chart(t, 500);
    const mapped = d.bars.map(({ time, open, high, low, close }) => ({ time, open, high, low, close }));
    barsRef.current = mapped;
    seriesRef.current.setData(mapped);
    volRef.current.setData(d.bars.map((b) => ({ time: b.time, value: b.volume, color: b.close >= b.open ? "rgba(16,185,129,.25)" : "rgba(239,68,68,.25)" })));
    lastBarRef.current = d.bars[d.bars.length - 1] || null;
    setCount(d.bars.length);
    paint();
    chartRef.current.timeScale().scrollToRealTime();
  }, [paint]);

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
        paint();
      }
    }
  }, [barUpdates, tf, paint]);

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
    const extra = [];
    layers.forEach((l) => {
      const c = l.direction === "long" ? "#10b981" : "#ef4444";
      const t = Math.floor(new Date(l.timestamp).getTime() / 1000);
      const secs = SECS[tf];
      extra.push({ time: Math.floor(t / secs) * secs, position: l.direction === "long" ? "belowBar" : "aboveBar", color: c, shape: l.direction === "long" ? "arrowUp" : "arrowDown", text: `L${l.layer_number}` });
    });
    paint(extra);
    const s = seriesRef.current;
    if (!s) return;
    layers.forEach((l) => {
      const c = l.direction === "long" ? "#10b981" : "#ef4444";
      linesRef.current.push(s.createPriceLine({ price: l.entry, color: c, lineWidth: 1, lineStyle: 0, title: `L${l.layer_number} ${l.direction.toUpperCase()} ${l.lots}` }));
      linesRef.current.push(s.createPriceLine({ price: l.sl, color: "#f97316", lineWidth: 1, lineStyle: 2, title: `L${l.layer_number} SL` }));
      if (l.tp) linesRef.current.push(s.createPriceLine({ price: l.tp, color: "#22c55e", lineWidth: 1, lineStyle: 2, title: `L${l.layer_number} TP` }));
    });
  }, [layers, tf, analysis, paint]);

  return (
    <div className="flex flex-col h-full min-h-0" data-testid="gold-chart-container">
      <div className="h-8 flex items-center justify-between px-3 bg-[var(--surface)] border-b border-[var(--hair)]">
        <div className="flex items-center gap-3">
          <span className="mono text-[10px] tracking-[.14em] uppercase text-dim">{title}</span>
          <span className="text-mute text-[10px] mono">{count} bars · {tf} · CHoCH/BOS history</span>
        </div>
        <div className="flex gap-1">
          {TFS.map((t) => <button key={t} className={`btn ${t === tf ? "active" : ""}`} data-testid={`timeframe-btn-${t}`} onClick={() => setTf(t)}>{t}</button>)}
        </div>
      </div>
      <div ref={elRef} className="flex-1 min-h-0" />
    </div>
  );
}
