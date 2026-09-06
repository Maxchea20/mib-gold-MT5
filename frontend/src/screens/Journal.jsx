import { useEffect, useState, useCallback } from "react";
import TradeCard from "@/components/TradeCard";
import { api } from "@/lib/api";
import { ENGINE_ORDER, ENGINE_NAMES, SESSION_LABEL, pct, rTxt } from "@/lib/format";

const Sel = ({ value, onChange, options, testId }) => (
  <select className="input" value={value} onChange={(e) => onChange(e.target.value)} data-testid={testId}>
    {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
  </select>
);

export default function Journal({ feed }) {
  const [f, setF] = useState({ direction: "", session: "", outcome: "", engine: "", mode: "", backtest_id: "" });
  const [trades, setTrades] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(false);
  const [runs, setRuns] = useState([]);

  useEffect(() => { api.backtests().then(setRuns).catch(() => {}); }, []);

  const load = useCallback(async () => {
    setLoading(true);
    const params = Object.fromEntries(Object.entries(f).filter(([, v]) => v));
    try {
      const [t, s] = await Promise.all([api.trades(params), api.tradeStats(params.mode || params.backtest_id ? { mode: f.mode || undefined, backtest_id: f.backtest_id || undefined } : {})]);
      setTrades(t); setStats(s);
    } finally { setLoading(false); }
  }, [f]);
  useEffect(() => { load(); }, [load, feed.lastTrades]);

  const set = (k) => (v) => setF((x) => ({ ...x, [k]: v }));
  return (
    <div className="flex-1 flex flex-col min-h-0" data-testid="journal-screen">
      <div className="h-10 shrink-0 flex items-center gap-2 px-4 bg-[var(--surface)] border-b border-[var(--hair)]">
        <span className="mono text-[10px] tracking-[.16em] uppercase text-dim mr-2">Trade journal · filters</span>
        <Sel testId="filter-direction" value={f.direction} onChange={set("direction")} options={[["", "direction: all"], ["long", "long"], ["short", "short"]]} />
        <Sel testId="filter-session" value={f.session} onChange={set("session")} options={[["", "session: all"], ...Object.entries(SESSION_LABEL)]} />
        <Sel testId="filter-outcome" value={f.outcome} onChange={set("outcome")} options={[["", "outcome: all"], ["win", "win"], ["loss", "loss"]]} />
        <Sel testId="filter-engine" value={f.engine} onChange={set("engine")} options={[["", "engine agreed: any"], ...ENGINE_ORDER.map((k) => [k, ENGINE_NAMES[k]])]} />
        <Sel testId="filter-mode" value={f.mode} onChange={set("mode")} options={[["", "mode: all"], ["paper", "paper"], ["live", "live"], ["backtest", "backtest"]]} />
        <Sel testId="filter-backtest" value={f.backtest_id} onChange={set("backtest_id")}
             options={[["", "backtest run: all"], ...runs.map((r) => [r.id, `${r.id.slice(0, 10)} · ${(r.created || "").slice(0, 16)} · ${r.stats?.trades ?? 0}t`])]} />
        <button className="btn" onClick={() => setF({ direction: "", session: "", outcome: "", engine: "", mode: "", backtest_id: "" })} data-testid="filter-reset">reset</button>
        <div className="flex-1" />
        {stats && (
          <div className="flex items-center gap-4 mono text-[10px]" data-testid="journal-stats">
            <span className="text-dim">trades <span className="text-white">{stats.trades}</span></span>
            <span className="text-dim">win rate <span className="text-white">{pct(stats.win_rate)}</span></span>
            <span className="text-dim">PF <span className="text-white">{stats.profit_factor ?? "—"}</span></span>
            <span className="text-dim">avg <span className="text-white">{rTxt(stats.avg_r)}</span></span>
            <span className={stats.net_pnl >= 0 ? "text-bull" : "text-bear"}>{stats.net_pnl_text}</span>
          </div>
        )}
      </div>
      <div className="flex-1 overflow-y-auto min-h-0 p-3 flex flex-col gap-2">
        {trades.length === 0 && <div className="text-mute mono text-[10px] uppercase tracking-widest p-6 text-center" data-testid="journal-empty">{loading ? "loading…" : "no closed trades match · run a backtest or let the paper loop trade"}</div>}
        {trades.map((t) => <TradeCard key={t.id} trade={t} />)}
      </div>
    </div>
  );
}