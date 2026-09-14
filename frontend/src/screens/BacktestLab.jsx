import { useEffect, useRef, useState } from "react";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import TradeCard from "@/components/TradeCard";
import { api } from "@/lib/api";
import { pct, rTxt, usd, ENGINE_ORDER, dt } from "@/lib/format";

const Field = ({ label, children }) => (<label className="flex flex-col gap-0.5"><span className="text-[9px] mono uppercase tracking-widest text-mute">{label}</span>{children}</label>);
const DEFAULT_CSV = "data/GOLD#_M1_202606031118_202609141118.csv";

export default function BacktestLab({ feed }) {
  const [form, setForm] = useState({
    days: 90, start_balance: 13688, max_layers: 3, budget_pct: 0.1, slippage_points: 5, use_news_gate: true,
    csv_path: DEFAULT_CSV, bias_min_score: 0.10, struct_oppose_score: 0.15, min_risk_usd: 10, max_risk_usd: 100,
    weights: { trend: 1, sr: 1, breakout: 0.9, momentum: 0.8, volume: 0.6, fibonacci: 0.7, elliott: 0.35, fvg: 0.9, pattern: 0.8, structure: 1 },
  });
  const [runId, setRunId] = useState(null);
  const [progress, setProgress] = useState(0);
  const [result, setResult] = useState(null);
  const [trades, setTrades] = useState([]);
  const [err, setErr] = useState(null);
  const [showCfg, setShowCfg] = useState(false);

  useEffect(() => {
    const b = feed.backtest; if (!b || b.id !== runId) return;
    setProgress(b.progress);
    if (b.done) finish(runId);
  }, [feed.backtest, runId]); // eslint-disable-line

  const finish = async (id) => {
    const r = await api.backtest(id);
    if (r.status === "error") { setErr(r.error); return; }
    setResult(r);
    setTrades(await api.backtestTrades(id));
  };

  const run = async () => {
    setErr(null); setResult(null); setTrades([]); setProgress(0);
    const body = { ...form };
    if (!body.csv_path) delete body.csv_path;
    try { const r = await api.runBacktest(body); setRunId(r.id); } catch (e) { setErr(e?.response?.data?.detail || e.message); }
  };

  const set = (k, num = true) => (e) => setForm((f) => ({ ...f, [k]: num ? Number(e.target.value) : e.target.checked }));
  const running = runId && !result && !err;
  const s = result?.stats || {};
  const attr = result?.attribution || {};
  const exits = s.by_exit || {};
  const sl = exits.SL || 0;
  const trail = exits.TRAIL_TP || 0;
  const slPct = s.trades ? sl / s.trades : 0;
  const trailPct = s.trades ? trail / s.trades : 0;

  return (
    <div className="flex-1 flex min-h-0" data-testid="backtest-screen">
      <div className="w-[280px] shrink-0 border-r border-[var(--hair)] flex flex-col min-h-0 overflow-y-auto">
        <div className="panel-head">Run</div>
        <div className="p-3 flex flex-col gap-2">
          <button className="btn active" onClick={run} disabled={!!running}>{running ? `running ${(progress * 100).toFixed(0)}%` : "run backtest"}</button>
          {running && <div className="conf-track"><div className="conf-fill bg-gold" style={{ width: `${progress * 100}%` }} /></div>}
          {err && <div className="text-bear text-[10px] mono">{err}</div>}
          <button className="btn" onClick={() => setShowCfg((v) => !v)}>{showCfg ? "hide config" : "show config"}</button>
        </div>
        {showCfg && (
          <div className="px-3 pb-3 grid grid-cols-2 gap-2">
            <Field label="days"><input className="input" type="number" value={form.days} onChange={set("days")} /></Field>
            <Field label="start $"><input className="input" type="number" value={form.start_balance} onChange={set("start_balance")} /></Field>
            <Field label="layers"><input className="input" type="number" value={form.max_layers} onChange={set("max_layers")} /></Field>
            <Field label="budget"><input className="input" type="number" step="0.01" value={form.budget_pct} onChange={set("budget_pct")} /></Field>
            <Field label="news"><input type="checkbox" className="mt-1" checked={form.use_news_gate} onChange={set("use_news_gate", false)} /></Field>
            <div className="col-span-2"><Field label="csv"><input className="input" value={form.csv_path} onChange={(e) => setForm((f) => ({ ...f, csv_path: e.target.value }))} /></Field></div>
          </div>
        )}
        <div className="px-3 pb-3 text-[10px] text-mute">GOLD# M1 CSV · H1/M15/M5 · trail +1R · no time-stop</div>
      </div>

      <div className="flex-1 flex flex-col min-w-0 min-h-0">
        <div className="shrink-0 border-b border-[var(--hair)] p-3" data-testid="bt-report">
          <div className="text-[10px] mono uppercase tracking-widest text-mute mb-2">
            Report {result?.id || "—"} · {result?.range ? `${String(result.range.start).slice(0, 10)} → ${String(result.range.end).slice(0, 10)} · ${result.range.m5_bars} M5` : "no run"}
          </div>
          <div className="grid grid-cols-8 gap-3 mono text-[12px]">
            <Stat k="trades" v={s.trades ?? "—"} />
            <Stat k="win rate" v={s.win_rate == null ? "—" : pct(s.win_rate)} />
            <Stat k="PF" v={s.profit_factor ?? "—"} />
            <Stat k="avg R" v={s.avg_r == null ? "—" : rTxt(s.avg_r)} />
            <Stat k="net" v={s.net_pnl_text || usd(s.net_pnl)} good={s.net_pnl >= 0} />
            <Stat k="return" v={s.return_pct == null ? "—" : pct(s.return_pct, 2)} good={s.return_pct >= 0} />
            <Stat k="final" v={result ? usd(result.final_balance) : "—"} gold />
            <Stat k="SL / trail" v={s.trades ? `${(slPct * 100).toFixed(0)}% / ${(trailPct * 100).toFixed(0)}%` : "—"} />
          </div>
          <div className="mt-2 text-[10px] mono text-dim">
            exits {Object.entries(exits).map(([k, v]) => `${k}:${v}`).join("  ") || "—"}
          </div>
          <div className="mt-3 overflow-auto">
            <table className="tbl">
              <thead><tr><th>engine</th><th>lead n</th><th>lead WR</th><th>edge</th><th>verdict</th></tr></thead>
              <tbody>
                {ENGINE_ORDER.map((k) => {
                  const a = attr[k];
                  if (!a) return null;
                  return (
                    <tr key={k} className="mono text-[10px]">
                      <td>{a.engine || k}</td>
                      <td>{a.strongest_count ?? 0}</td>
                      <td>{a.strongest_win_rate == null ? "—" : pct(a.strongest_win_rate, 0)}</td>
                      <td className={a.edge > 0 ? "text-bull" : a.edge < 0 ? "text-bear" : ""}>{a.edge == null ? "—" : (a.edge >= 0 ? "+" : "") + Number(a.edge).toFixed(2)}</td>
                      <td>{a.recommendation || "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
        <div className="h-[240px] shrink-0 border-b border-[var(--hair)]">
          <div className="h-full" data-testid="equity-curve">
            {(result?.equity_curve || []).length > 0 && (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={result.equity_curve} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <defs><linearGradient id="eq" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#eab308" stopOpacity={0.35} /><stop offset="100%" stopColor="#eab308" stopOpacity={0} /></linearGradient></defs>
                  <XAxis dataKey="time" tick={{ fontSize: 9, fill: "#6b7280", fontFamily: "JetBrains Mono" }} tickFormatter={(t) => String(t).slice(5, 10)} minTickGap={60} stroke="#1f2937" />
                  <YAxis domain={["auto", "auto"]} tick={{ fontSize: 9, fill: "#6b7280", fontFamily: "JetBrains Mono" }} width={54} stroke="#1f2937" />
                  <Tooltip contentStyle={{ background: "#0c1017", border: "1px solid #374151", fontSize: 10 }} />
                  <Area type="stepAfter" dataKey="equity" stroke="#eab308" fill="url(#eq)" strokeWidth={1.5} isAnimationActive={false} />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>
        <div className="flex-1 min-h-0 overflow-y-auto p-2 flex flex-col gap-1.5">
          <div className="text-[10px] mono uppercase tracking-widest text-mute px-1">Trades · {trades.length}</div>
          {trades.map((t) => <TradeCard key={t.id} trade={t} />)}
        </div>
      </div>
    </div>
  );
}

function Stat({ k, v, good, gold }) {
  const cls = gold ? "text-gold" : good === true ? "text-bull" : good === false ? "text-bear" : "";
  return (
    <div>
      <div className="text-[9px] uppercase tracking-widest text-mute">{k}</div>
      <div className={`text-[13px] ${cls}`}>{v}</div>
    </div>
  );
}
