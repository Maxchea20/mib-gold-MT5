import { useEffect, useRef } from "react";
import { createChart, CandlestickSeries, createSeriesMarkers, ColorType, CrosshairMode } from "lightweight-charts";

// Replay chart: renders bars up to the scrub index with entry/exit markers and layer SL lines.
export default function ReplayChart({ bars, idx }) {
  const elRef = useRef(null), chartRef = useRef(null), sRef = useRef(null), mRef = useRef(null), linesRef = useRef([]);
  useEffect(() => {
    const chart = createChart(elRef.current, {
      layout: { background: { type: ColorType.Solid, color: "#07090e" }, textColor: "#9ca3af", fontFamily: "JetBrains Mono", fontSize: 10 },
      grid: { vertLines: { color: "rgba(31,41,55,.5)" }, horzLines: { color: "rgba(31,41,55,.5)" } },
      crosshair: { mode: CrosshairMode.Normal }, rightPriceScale: { borderColor: "#1f2937" },
      timeScale: { borderColor: "#1f2937", timeVisible: true, secondsVisible: false }, autoSize: true, localization: { locale: "en-US", dateFormat: "yyyy-MM-dd" },
    });
    sRef.current = chart.addSeries(CandlestickSeries, { upColor: "#10b981", downColor: "#ef4444", borderUpColor: "#10b981", borderDownColor: "#ef4444", wickUpColor: "#10b981", wickDownColor: "#ef4444" });
    mRef.current = createSeriesMarkers(sRef.current, []);
    chartRef.current = chart;
    return () => chart.remove();
  }, []);

  useEffect(() => {
    if (!bars?.length || !sRef.current) return;
    const upto = bars.slice(Math.max(0, idx - 400), idx + 1);
    sRef.current.setData(upto.map((b) => ({ time: Math.floor(new Date(b.time).getTime() / 1000) - 300, open: b.o, high: b.h, low: b.l, close: b.c })));
    const markers = [];
    upto.forEach((b) => {
      const t = Math.floor(new Date(b.time).getTime() / 1000) - 300;
      if (b.opened) markers.push({ time: t, position: b.bias === "short" ? "aboveBar" : "belowBar", color: b.bias === "short" ? "#ef4444" : "#10b981", shape: b.bias === "short" ? "arrowDown" : "arrowUp", text: "IN" });
      if (b.closed?.length) markers.push({ time: t, position: "aboveBar", color: "#eab308", shape: "square", text: "OUT" });
    });
    mRef.current.setMarkers(markers);
    linesRef.current.forEach((l) => sRef.current.removePriceLine(l)); linesRef.current = [];
    (bars[idx]?.layers || []).forEach((l) => {
      linesRef.current.push(sRef.current.createPriceLine({ price: l.entry, color: l.dir === "long" ? "#10b981" : "#ef4444", lineWidth: 1, title: `entry ${l.dir}` }));
      linesRef.current.push(sRef.current.createPriceLine({ price: l.sl, color: "#f97316", lineWidth: 1, lineStyle: 2, title: "SL" }));
      if (l.trail) linesRef.current.push(sRef.current.createPriceLine({ price: l.trail, color: "#06b6d4", lineWidth: 1, lineStyle: 3, title: "trail" }));
    });
    chartRef.current.timeScale().scrollToRealTime();
  }, [bars, idx]);

  return <div ref={elRef} className="h-full w-full" data-testid="replay-chart" />;
}
