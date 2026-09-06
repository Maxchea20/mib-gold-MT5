export const usd = (v, sign = false) => {
  if (v === undefined || v === null || Number.isNaN(v)) return "—";
  const s = `$${Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  return sign ? (v < 0 ? `-${s}` : `+${s}`) : s;
};
export const px = (v, d = 2) => (v === undefined || v === null ? "—" : Number(v).toFixed(d));
export const pct = (v, d = 1) => (v === undefined || v === null ? "—" : `${(v * 100).toFixed(d)}%`);
export const rTxt = (r) => (r === undefined || r === null ? "—" : `${r >= 0 ? "+" : ""}${Number(r).toFixed(2)}R`);
export const hhmmss = (iso) => (iso ? new Date(iso).toISOString().slice(11, 19) : "—");
export const dt = (iso) => (iso ? new Date(iso).toISOString().slice(0, 16).replace("T", " ") : "—");
export const countdown = (secs) => {
  const s = Math.max(0, Math.abs(Math.round(secs)));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(x).padStart(2, "0")}`;
};
export const sigColor = (s) => (s === "long" ? "var(--bull)" : s === "short" ? "var(--bear)" : "var(--t3)");
export const SESSION_LABEL = { asian: "Asian", london: "London", ny_overlap: "NY Overlap", ny: "New York", off: "Off-hours" };
export const ENGINE_NAMES = {
  trend: "Trend", sr: "Support/Resistance", breakout: "Breakout/Breakdown", momentum: "Momentum", volume: "Volume (tick proxy)",
  fibonacci: "Fibonacci", elliott: "Elliott Wave", fvg: "Fair Value Gap", pattern: "Pattern Recognition", structure: "Market Structure",
};
export const ENGINE_ORDER = ["trend", "sr", "breakout", "momentum", "volume", "fibonacci", "elliott", "fvg", "pattern", "structure"];
