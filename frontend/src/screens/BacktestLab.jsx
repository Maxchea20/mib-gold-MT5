import { useEffect, useMemo, useRef, useState } from "react";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { Play, Pause, SkipBack, SkipForward } from "lucide-react";
import AgentBoard from "@/components/AgentBoard";
import ReplayChart from "@/components/ReplayChart";
import TradeCard from "@/components/TradeCard";
import { api } from "@/lib/api";
import { pct, rTxt, usd, ENGINE_ORDER, dt } from "@/lib/format";

const Field = ({ label, children }) => (<label className="flex flex-col gap-0.5"><span className="text-[9px] mono uppercase tracking-widest text-mute">{label}</span>{children}</label>);

export default function BacktestLab({ feed, config }) {
  const [form, setForm] = useState({ days: 10, start_balance: 100, max_layers: 3, budget_pct: 0.1, slippage_points: 5, use_news_gate: true,
    bias_min_score: 0.10, struct_oppose_score: 0.15, min_risk_usd: 10, max_risk_usd: 100,
    weights: { trend: 1, sr: 1, breakout: 0.9, momentum: 0.8, volume: 0.6, fibonacci: 0.7, elliott: 0.35, fvg: 0.9, pattern: 0.8, structure: 1 },
    session_thresholds: { asian: 0.34, london: 0.26, ny_overlap: 0.24, ny: 0.28, off: 0.42 },
    session_min_aligned: { asian: 5, london: 4, ny_overlap: 4, ny: 4, off: 6 } });
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [runId, setRunId] = useState(null);
  const [progress, setProgress] = useState(0);
  const [result, setResult] = useState(null);
  const [trades, setTrades] = useState([]);
  const [bars, setBars] = useState([]);
  const [idx, setIdx] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(5);
  const [history, setHistory] = useState([]);
  const [err, setErr] = useState(null);
  const timer = useRef(null);

  useEffect(() => { api.backtests().then(setHistory).catch(() => {}); }, [result]);
  useEffect(() => {
    const b = feed.backtest; if (!b || b.id !== runId) return;
    setProgress(b.progress);
    if (b.done) finish(runId);
  }, [feed.backtest, runId]); // eslint-disable-line

  const finish = async (id) => {
    const r = await api.backtest(id);
    if (r.status === "error") { setErr(r.error); return; }
    setResult(r);
    const t = await api.backtestTrades(id); setTrades(t);
    let all = [], start = 0, total = 1;
    while (start < total) { const page = await api.backtestBars(id, start, 2000); total = page.total; all = all.concat(page.bars); start += 2000; if (!page.bars.length) break; }
    setBars(all); setIdx(Math.max(0, all.length - 1));
  };

  const run = async () => {
    setErr(null); setResult(null); setTrades([]); setBars([]); setProgress(0);
    try { const r = await api.runBacktest(form); setRunId(r.id); } catch (e) { setErr(e?.response?.data?.detail || e.message); }
  };

  useEffect(() => {
    if (!playing) { clearInterval(timer.current); return; }
    timer.current = setInterval(() => setIdx((i) => (i + 1 >= bars.length ? (setPlaying(false), i) : i + 1)), 400 / speed);
    return () => clearInterval(timer.current);
  }, [playing, speed, bars.length]);

  const bar = bars[idx];
  const replayAnalysis = useMemo(() => {
    if (!bar) return null;
    const votes = Object.fromEntries(Object.entries(bar.votes).map(([k, [signal, confidence, reason]]) => [k, { signal, confidence, reason }]));
    const dir = bar.score > 0 ? "long" : bar.score < 0 ? "short" : "neutral";
    const aligned = Object.values(votes).filter((v) => v.signal === dir).length;
    const leaders = ENGINE_ORDER.filter((k) => votes[k]?.signal === dir).sort((a, b) => votes[b].confidence - votes[a].confidence).slice(0, 3);
    return { time: bar.time, session: bar.session, fire: bar.fire, gate_reason: bar.gate, votes,
      bias: { direction: bar.bias }, entry: { direction: dir, score: bar.score, aligned, total: 10, threshold: config?.session_thresholds?.[bar.session], min_aligned: config?.session_min_aligned?.[bar.session] },
      summary: dir === "neutral" ? "No consensus" : `${aligned}/10 engines aligned ${dir}${leaders.length ? ", led by " + leaders.map((k) => k).join(" + ") : ""}.` };
  }, [bar, config]);

  const curve = result?.equity_curve || [];
  const attribution = result?.attribution || {};
  const set = (k, num = true) => (e) => setForm((f) => ({ ...f, [k]: num ? Number(e.target.value) : e.target.checked }));
  const setSession = (session, key) => (e) => setForm((f) => ({ ...f, [key]: { ...f[key], [session]: Number(e.target.value) } }));
  const setWeight = (engine) => (e) => setForm((f) => ({ ...f, weights: { ...f.weights, [engine]: Number(e.target.value) } }));
  const running = runId && !result && !err;

  return (
    <div className="flex-1 flex min-h-0" data-testid="backtest-screen">
      <div className="w-[300px] shrink-0 border-r border-[var(--hair)] flex flex-col min-h-0 overflow-y-auto">
        <div className="panel-head">Backtest config · bar-by-bar M5</div>
        <div className="p-3 grid grid-cols-2 gap-2">
          <Field label="days"><input className="input" type="number" value={form.days} onChange={set("days")} data-testid="bt-days" /></Field>
          <Field label="start $"><input className="input" type="number" value={form.start_balance} onChange={set("start_balance")} data-testid="bt-balance" /></Field>
          <Field label="max layers"><input className="input" type="number" value={form.max_layers} onChange={set("max_layers")} data-testid="bt-layers" /></Field>
          <Field label="budget %"><input className="input" type="number" step="0.01" value={form.budget_pct} onChange={set("budget_pct")} data-testid="bt-budget" /></Field>
          <Field label="slippage pts"><input className="input" type="number" value={form.slippage_points} onChange={set("slippage_points")} data-testid="bt-slippage" /></Field>
          <Field label="news gate"><input type="checkbox" className="mt-1" checked={form.use_news_gate} onChange={set("use_news_gate", false)} data-testid="bt-newsgate" /></Field>
          <Field label="bias min score"><input className="input" type="number" step="0.01" value={form.bias_min_score} onChange={set("bias_min_score")} data-testid="bt-bias-min" /></Field>
          <Field label="struct oppose"><input className="input" type="number" step="0.01" value={form.struct_oppose_score} onChange={set("struct_oppose_score")} data-testid="bt-struct-oppose" /></Field>
          <Field label="min risk $"><input className="input" type="number" value={form.min_risk_usd} onChange={set("min_risk_usd")} data-testid="bt-min-risk" /></Field>
          <Field label="max risk $"><input className="input" type="number" value={form.max_risk_usd} onChange={set("max_risk_usd")} data-testid="bt-max-risk" /></Field>
        </div>
        <div className="px-3 pb-2 text-[10px] text-mute leading-snug">
          Risk per trade clamps to [min, max] regardless of equity — prevents a winning streak from silently ballooning position size.
        </div>
        <div className="px-3 pb-2">
          <button className="btn w-full" onClick={() => setShowAdvanced((s) => !s)} data-testid="bt-toggle-advanced">
            {showAdvanced ? "hide" : "show"} per-session gate thresholds
          </button>
        </div>
        {showAdvanced && (
          <div className="px-3 pb-3">
            <table className="tbl">
              <thead><tr><th>session</th><th>score thr</th><th>min aligned</th></tr></thead>
              <tbody>
                {Object.keys(form.session_thresholds).map((s) => (
                  <tr key={s} className="mono text-[10px]">
                    <td>{s}</td>
                    <td><input className="input" type="number" step="0.01" value={form.session_thresholds[s]} onChange={setSession(s, "session_thresholds")} data-testid={`bt-thr-${s}`} /></td>
                    <td><input className="input" type="number" value={form.session_min_aligned[s]} onChange={setSession(s, "session_min_aligned")} data-testid={`bt-minaligned-${s}`} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="px-3 pb-3 flex flex-col gap-2">
          <button className="btn active" onClick={run} disabled={!!running} data-testid="bt-run">{running ? `running ${(progress * 100).toFixed(0)}%` : "run backtest"}</button>
          {running && <div className="conf-track"><div className="conf-fill bg-gold" style={{ width: `${progress * 100}%` }} /></div>}
          {err && <div className="text-bear text-[10px] mono" data-testid="bt-error">{err}</div>}
          <div className="text-[10px] text-mute leading-snug">Data: {feed.status?.connection?.source || "adapter"} M1 → resampled M5/H1/H4/D1. Spread {feed.status?.symbol?.spread_price?.toFixed(2)} simulated, stops filled worst-case + slippage.</div>
        </div>
        {result && (
          <div className="border-t border-[var(--hair)]">
            <div className="panel-head">Results · {result.id}</div>
            <div className="p-3 grid grid-cols-2 gap-y-1 mono text-[11px]" data-testid="bt-stats">
              <span className="text-mute">trades</span><span>{result.stats.trades}</span>
              <span className="text-mute">win rate</span><span>{pct(result.stats.win_rate)}</span>
              <span className="text-mute">profit factor</span><span>{result.stats.profit_factor ?? "—"}</span>
              <span className="text-mute">avg R</span><span>{rTxt(result.stats.avg_r)}</span>
              <span className="text-mute">net</span><span className={result.stats.net_pnl >= 0 ? "text-bull" : "text-bear"}>{result.stats.net_pnl_text}</span>
              <span className="text-mute">return</span><span>{pct(result.stats.return_pct, 2)}</span>
              <span className="text-mute">final</span><span className="text-gold">{usd(result.final_balance)}</span>
              <span className="text-mute">exits</span><span className="text-dim">{Object.entries(result.stats.by_exit || {}).map(([k, v]) => `${k}:${v}`).join(" ")}</span>
            </div>
          </div>
        )}
        <div className="border-t border-[var(--hair)] mt-auto">
          <div className="panel-head">Previous runs</div>
          {history.map((h) => (
            <div key={h.id} className="px-3 py-1.5 mono text-[10px] flex justify-between border-b border-[rgba(31,41,55,.6)]">
              <span className="text-dim">{dt(h.created)}</span><span>{h.stats?.trades}t</span><span className={h.stats?.net_pnl >= 0 ? "text-bull" : "text-bear"}>{usd(h.stats?.net_pnl, true)}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="flex-1 flex flex-col min-w-0 min-h-0">
        <div className="h-[220px] shrink-0 panel border-0 border-b flex flex-col">
          <div className="panel-head"><span>Equity curve</span><span className="text-mute">{result ? `${result.range.start.slice(0, 10)} → ${result.range.end.slice(0, 10)} · ${result.range.m5_bars} M5 bars` : "no run"}</span></div>
          <div className="flex-1 min-h-0" data-testid="equity-curve">
            {curve.length > 0 && (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={curve} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <defs><linearGradient id="eq" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#eab308" stopOpacity={0.35} /><stop offset="100%" stopColor="#eab308" stopOpacity={0} /></linearGradient></defs>
                  <XAxis dataKey="time" tick={{ fontSize: 9, fill: "#6b7280", fontFamily: "JetBrains Mono" }} tickFormatter={(t) => t.slice(5, 10)} minTickGap={60} stroke="#1f2937" />
                  <YAxis domain={["auto", "auto"]} tick={{ fontSize: 9, fill: "#6b7280", fontFamily: "JetBrains Mono" }} width={54} stroke="#1f2937" />
                  <Tooltip contentStyle={{ background: "#0c1017", border: "1px solid #374151", fontSize: 10, fontFamily: "JetBrains Mono" }} labelFormatter={(t) => dt(t)} />
                  <Area type="stepAfter" dataKey="equity" stroke="#eab308" fill="url(#eq)" strokeWidth={1.5} isAnimationActive={false} />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>
        <div className="flex-1 min-h-0 flex">
          <div className="flex-1 flex flex-col min-w-0 border-r border-[var(--hair)]">
            <div className="flex-1 min-h-0">{bars.length > 0 ? <ReplayChart bars={bars} idx={idx} /> : <div className="h-full flex items-center justify-center text-mute mono text-[10px] uppercase tracking-widest">run a backtest to scrub through history</div>}</div>
            <div className="h-12 shrink-0 flex items-center gap-2 px-3 border-t border-[var(--hair)] bg-[var(--surface)]">
              <button className="btn" onClick={() => setIdx(0)} data-testid="scrub-start"><SkipBack size={10} /></button>
              <button className="btn" onClick={() => setPlaying((p) => !p)} disabled={!bars.length} data-testid="scrub-play">{playing ? <Pause size={10} /> : <Play size={10} />}</button>
              <button className="btn" onClick={() => setIdx(bars.length - 1)} data-testid="scrub-end"><SkipForward size={10} /></button>
              {[1, 5, 20].map((s) => <button key={s} className={`btn ${speed === s ? "active" : ""}`} onClick={() => setSpeed(s)}>{s}x</button>)}
              <input type="range" min={0} max={Math.max(0, bars.length - 1)} value={idx} onChange={(e) => setIdx(Number(e.target.value))} className="flex-1 accent-[#eab308]" data-testid="backtest-time-scrubber" />
              <span className="mono text-[10px] text-dim w-40 text-right">{bar ? dt(bar.time) : "—"} · {idx + 1}/{bars.length}</span>
              {bar && <span className="mono text-[10px] text-gold w-20 text-right">{usd(bar.equity)}</span>}
            </div>
          </div>
          <div className="w-[380px] shrink-0 min-h-0">{<AgentBoard analysis={replayAnalysis} weights={config?.weights} compact />}</div>
        </div>
      </div>

      <div className="w-[420px] shrink-0 border-l border-[var(--hair)] flex flex-col min-h-0">
        <div className="panel-head flex items-center justify-between">
          <span>Per-engine attribution</span>
          <button className="btn text-[9px]" onClick={() => setForm((f) => ({ ...f, weights: { trend: 1, sr: 1, breakout: 0.9, momentum: 0.8, volume: 0.6, fibonacci: 0.7, elliott: 0.35, fvg: 0.9, pattern: 0.8, structure: 1 } }))} data-testid="bt-reset-weights">
            reset weights
          </button>
        </div>
        <div className="px-3 pt-2 pb-1 text-[10px] text-mute leading-snug">
          Edit weight (w) then Run Backtest to test the change — applies to this run only.
        </div>
        <div className="overflow-auto" data-testid="attribution-table">
          <table className="tbl">
            <thead><tr><th>Engine</th><th>w</th><th>Lead WR</th><th>Agr W/L</th><th>Edge</th><th>Conf W/L</th><th>Verdict</th></tr></thead>
            <tbody>
              {ENGINE_ORDER.map((k) => { const a = attribution[k]; return (
                <tr key={k} className="mono text-[10px]" data-testid={`attribution-row-${k}`}>
                  <td className={k === "elliott" ? "text-dim" : ""}>{a?.engine || k}</td>
                  <td><input className="input w-14" type="number" step="0.05" min="0" max="1" value={form.weights[k] ?? 1} onChange={setWeight(k)} data-testid={`bt-weight-${k}`} /></td>
                  <td>{a?.strongest_win_rate == null ? "—" : `${pct(a.strongest_win_rate, 0)} (${a.strongest_count})`}</td>
                  <td>{a ? `${pct(a.agreement_on_wins, 0)}/${pct(a.agreement_on_losses, 0)}` : "—"}</td>
                  <td className={a?.edge > 0 ? "text-bull" : a?.edge < 0 ? "text-bear" : ""}>{a ? (a.edge >= 0 ? "+" : "") + a.edge.toFixed(2) : "—"}</td>
                  <td className="text-dim">{a ? `${a.avg_conf_wins == null ? "—" : (a.avg_conf_wins * 100).toFixed(0)}/${a.avg_conf_losses == null ? "—" : (a.avg_conf_losses * 100).toFixed(0)}` : "—"}</td>
                  <td><span className={`badge ${a?.recommendation === "upweight" ? "long" : a?.recommendation === "drop" || a?.recommendation === "downweight" ? "short" : "neutral"}`}>{a?.recommendation || "—"}</span></td>
                </tr>); })}
            </tbody>
          </table>
        </div>
        <div className="panel-head border-t">Backtested trades · {trades.length}</div>
        <div className="flex-1 overflow-y-auto min-h-0 p-2 flex flex-col gap-1.5" data-testid="bt-trades">
          {trades.map((t) => <TradeCard key={t.id} trade={t} />)}
        </div>
      </div>
    </div>
  );
}