import { useEffect, useState } from "react";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { api } from "@/lib/api";
import { pct, rTxt, usd } from "@/lib/format";

const Field = ({ label, children }) => (<label className="flex flex-col gap-0.5"><span className="text-[9px] mono uppercase tracking-widest text-mute">{label}</span>{children}</label>);
const DEFAULT_CSV = "data/GOLD#_M1_202606031118_202609141118.csv";

function shortTime(t) {
  if (!t) return "-";
  return String(t).replace("T", " ").slice(5, 16);
}

export default function BacktestLab({ feed }) {
  const [form, setForm] = useState({
    days: 90, start_balance: 100, max_layers: 1, budget_pct: 0.1, slippage_points: 5, use_news_gate: true,
    csv_path: DEFAULT_CSV, fixed_lots: 0.02, sl_dollars: 1.5, tp_dollars: 4.5,
    bias_min_score: 0.10, struct_oppose_score: 0.15, min_risk_usd: 1, max_risk_usd: 100,
  });
  const [runId, setRunId] = useState(null);
  const [progress, setProgress] = useState(0);
  const [result, setResult] = useState(null);
  const [trades, setTrades] = useState([]);
  const [err, setErr] = useState(null);
  const [savedPath, setSavedPath] = useState(null);

  const finish = async (id) => {
    try {
      const r = await api.backtest(id);
      if (!r) return;
      if (r.status === "error") { setErr(r.error || "backtest error"); setProgress(1); return; }
      if (r.status === "running" || r.status === "pending") {
        if (typeof r.progress === "number") setProgress(r.progress);
        return;
      }
      if (r.stats || r.status === "done") {
        setResult(r); setProgress(1);
        if (Array.isArray(r.trades) && r.trades.length) setTrades(r.trades);
        else {
          try { setTrades(await api.backtestTrades(id)); }
          catch (e) {
            setErr((e?.response?.data?.detail || e.message || "trades fetch failed") + " - stats loaded, table empty");
            setTrades([]);
          }
        }
      }
    } catch (e) {
      setErr(e?.response?.data?.detail || e.message);
    }
  };

  useEffect(() => {
    const b = feed.backtest;
    if (!b || (runId && b.id !== runId)) return;
    if (typeof b.progress === "number") setProgress(b.progress);
    if (b.error) setErr(b.error);
    if (b.done && (runId || b.id)) finish(runId || b.id);
  }, [feed.backtest, runId]);

  useEffect(() => {
    if (!runId || result || err) return;
    finish(runId);
    const t = setInterval(() => finish(runId), 800);
    return () => clearInterval(t);
  }, [runId, result, err]);

  const run = async () => {
    setErr(null); setResult(null); setTrades([]); setProgress(0); setSavedPath(null);
    const body = { ...form, tp_dollars: Number(form.sl_dollars) * 3 };
    if (!body.csv_path) delete body.csv_path;
    try { const r = await api.runBacktest(body); setRunId(r.id); } catch (e) { setErr(e?.response?.data?.detail || e.message); }
  };

  const exportReport = async (kind) => {
    if (!runId) { setErr("Run a backtest first."); return; }
    try {
      const r = await api.exportBacktest(runId, kind);
      setErr(null);
      setSavedPath(r.path);
    } catch (e) {
      setErr(e?.response?.data?.detail || e.message || "export failed");
    }
  };

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : Number(e.target.value) }));
  const running = runId && !result && !err;
  const pctRun = Math.max(0, Math.min(100, progress * 100));
  const s = result?.stats || {};
  const exits = s.by_exit || {};
  const sln = exits.SL || 0;
  const trail = (exits.TRAIL_TP || 0) + (exits.TP || 0);

  return (
    <div className="flex-1 flex min-h-0">
      <div className="w-[260px] shrink-0 border-r border-[var(--hair)] overflow-y-auto">
        <div className="panel-head">C-Fast V2 - 15m arm - 4h weather - RR 1:3</div>
        <div className="p-3 grid grid-cols-2 gap-2">
          <Field label="capital $"><input className="input" type="number" value={form.start_balance} onChange={set("start_balance")} /></Field>
          <Field label="lot"><input className="input" type="number" step="0.01" value={form.fixed_lots} onChange={set("fixed_lots")} /></Field>
          <Field label="SL $"><input className="input" type="number" step="0.1" value={form.sl_dollars} onChange={set("sl_dollars")} /></Field>
          <Field label="TP $ (=3x SL)"><input className="input" type="number" step="0.1" value={(Number(form.sl_dollars) * 3).toFixed(2)} readOnly /></Field>
          <Field label="days"><input className="input" type="number" value={form.days} onChange={set("days")} /></Field>
          <Field label="layers"><input className="input" type="number" value={form.max_layers} onChange={set("max_layers")} /></Field>
        </div>
        <div className="px-3 pb-3 flex flex-col gap-2">
          <button className={`btn active w-full ${running ? "breathe" : ""}`} onClick={run} disabled={!!running}>
            {running ? `running ${pctRun.toFixed(0)}%` : "run C-Fast V2"}
          </button>
          {running && (
            <div className="conf-track h-2">
              <div className="conf-fill bg-gold breathe" style={{ width: `${Math.max(3, pctRun)}%` }} />
            </div>
          )}
          <button className="btn w-full" disabled={!runId} onClick={() => exportReport("json")}>download JSON</button>
          <button className="btn w-full" disabled={!runId} onClick={() => exportReport("txt")}>download TXT</button>
          {runId && <div className="text-[9px] mono text-mute break-all">{runId}</div>}
          {savedPath && <div className="text-bull text-[10px] mono break-all">saved {savedPath}</div>}
          {err && <div className="text-bear text-[10px] mono">{err}</div>}
        </div>
      </div>
      <div className="flex-1 flex flex-col min-w-0 min-h-0 overflow-y-auto">
        <div className="p-3 border-b border-[var(--hair)]">
          <div className="text-[10px] mono uppercase tracking-widest text-mute mb-2">
            C-Fast V2 {result?.id || "-"} - {result?.range ? `${String(result.range.start).slice(0, 10)} to ${String(result.range.end).slice(0, 10)}` : (running ? `walking ${pctRun.toFixed(0)}%` : "no run")}
          </div>
          <div className="grid grid-cols-8 gap-3 mono text-[12px]">
            <Stat k="trades" v={s.trades ?? "-"} />
            <Stat k="win rate" v={s.win_rate == null ? "-" : pct(s.win_rate)} />
            <Stat k="PF" v={s.profit_factor ?? "-"} />
            <Stat k="avg R" v={s.avg_r == null ? "-" : rTxt(s.avg_r)} />
            <Stat k="net" v={s.net_pnl_text || usd(s.net_pnl)} good={s.net_pnl >= 0} />
            <Stat k="return" v={s.return_pct == null ? "-" : pct(s.return_pct, 2)} good={s.return_pct >= 0} />
            <Stat k="final" v={result ? usd(result.final_balance) : "-"} gold />
            <Stat k="SL / TP" v={s.trades ? `${((sln / s.trades) * 100).toFixed(0)}% / ${((trail / s.trades) * 100).toFixed(0)}%` : "-"} />
          </div>
        </div>
        <div className="h-[160px] shrink-0 border-b border-[var(--hair)]">
          {(result?.equity_curve || []).length > 0 && (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={result.equity_curve} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <defs><linearGradient id="eq" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#eab308" stopOpacity={0.35} /><stop offset="100%" stopColor="#eab308" stopOpacity={0} /></linearGradient></defs>
                <XAxis dataKey="time" tick={{ fontSize: 9, fill: "#6b7280" }} tickFormatter={(t) => String(t).slice(5, 10)} minTickGap={40} stroke="#1f2937" />
                <YAxis domain={["auto", "auto"]} tick={{ fontSize: 9, fill: "#6b7280" }} width={48} stroke="#1f2937" />
                <Tooltip contentStyle={{ background: "#0c1017", border: "1px solid #374151", fontSize: 10 }} />
                <Area type="stepAfter" dataKey="equity" stroke="#eab308" fill="url(#eq)" strokeWidth={1.5} isAnimationActive={false} />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>
        <div className="flex-1 min-h-0 overflow-auto">
          <table className="tbl">
            <thead><tr><th>time</th><th>side</th><th>L</th><th>session</th><th>in</th><th>out</th><th>exit</th><th>R</th><th>pnl</th></tr></thead>
            <tbody>
              {trades.slice(0, 2000).map((t, i) => {
                const r = Number(t.r_multiple ?? 0); const pnl = Number(t.pnl ?? 0); const side = t.direction || "";
                return (
                  <tr key={t.id || i} className="mono text-[10px]">
                    <td>{shortTime(t.exit_time || t.timestamp)}</td>
                    <td className={side === "long" ? "text-bull" : "text-bear"}>{String(side).toUpperCase()}</td>
                    <td>L{t.layer_number}</td><td>{t.session}</td><td>{t.entry}</td><td>{t.exit_price}</td><td>{t.exit_reason}</td>
                    <td className={r >= 0 ? "text-bull" : "text-bear"}>{rTxt(r)}</td>
                    <td className={pnl >= 0 ? "text-bull" : "text-bear"}>{usd(pnl, true)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function Stat({ k, v, good, gold }) {
  const cls = gold ? "text-gold" : good === true ? "text-bull" : good === false ? "text-bear" : "";
  return (<div><div className="text-[9px] uppercase tracking-widest text-mute">{k}</div><div className={`text-[13px] ${cls}`}>{v}</div></div>);
}
