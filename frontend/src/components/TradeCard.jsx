import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { ENGINE_ORDER, ENGINE_NAMES, sigColor, px, rTxt, dt, SESSION_LABEL } from "@/lib/format";

export function JustificationCard({ trade }) {
  const votes = trade.agent_votes || {}, c = trade.consensus || {};
  return (
    <div className="grid grid-cols-[1fr_320px] gap-0 border-t border-[var(--hair)]" data-testid={`justification-card-${trade.id}`}>
      <div>
        <div className="panel-head" style={{ height: 26 }}><span>All 10 engine votes at entry</span><span className="text-mute">{c.aligned}/{c.total} aligned · score {c.score >= 0 ? "+" : ""}{c.score?.toFixed(3)}</span></div>
        <table className="tbl">
          <thead><tr><th>Engine</th><th>Vote</th><th>Conf</th><th>Reason</th></tr></thead>
          <tbody>
            {ENGINE_ORDER.map((k) => {
              const v = votes[k] || {}; const lead = (c.leaders || []).includes(k);
              return (
                <tr key={k} className="mono text-[10px]" data-testid={`vote-row-${k}`}>
                  <td className={lead ? "text-gold font-semibold" : ""}>{ENGINE_NAMES[k]}{lead && " ★"}</td>
                  <td><span className={`badge ${v.signal || "neutral"}`}>{v.signal || "n/a"}</span></td>
                  <td><div className="flex items-center gap-2"><div className="conf-track w-14"><div className="conf-fill" style={{ width: `${(v.confidence || 0) * 100}%`, background: sigColor(v.signal) }} /></div><span className="text-dim">{((v.confidence || 0) * 100).toFixed(0)}%</span></div></td>
                  <td className="text-dim font-sans">{v.reason}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="border-l border-[var(--hair)] p-3 flex flex-col gap-2 text-[11px]">
        <div className="text-[9px] mono uppercase tracking-widest text-mute">Rule-based summary</div>
        <div className="leading-snug" data-testid="trade-summary">{trade.summary}</div>
        <div className="text-[9px] mono uppercase tracking-widest text-mute mt-2">Bias gate</div>
        <div className="mono text-[10px] text-dim">HTF bias <span className={`badge ${trade.bias?.direction}`}>{trade.bias?.direction}</span> · D1 {trade.bias?.d1_score?.toFixed(2)} · H4 {trade.bias?.h4_score?.toFixed(2)}</div>
        <div className="text-[9px] mono uppercase tracking-widest text-mute mt-2">Execution</div>
        <div className="mono text-[10px] grid grid-cols-2 gap-x-3 gap-y-0.5 text-dim">
          <span>Layer</span><span className="text-white">#{trade.layer_number} · {trade.lots} lots</span>
          <span>Entry</span><span className="text-white">{px(trade.entry)}</span>
          <span>Initial SL</span><span className="text-[var(--orange)]">{px(trade.initial_sl)}</span>
          <span>TP mode</span><span className="text-cyan">{trade.tp_mode}</span>
          <span>Risk</span><span className="text-white">${trade.risk_usd}</span>
          <span>Session</span><span className="text-white">{SESSION_LABEL[trade.session] || trade.session}</span>
          <span>Mode</span><span className="text-white">{trade.mode}</span>
          {trade.status === "closed" && (<>
            <span>Exit</span><span className="text-white">{px(trade.exit_price)} · {trade.exit_reason}</span>
            <span>Closed</span><span className="text-white">{dt(trade.exit_time)}</span>
          </>)}
        </div>
        <div className="mt-auto pt-2 border-t border-[var(--hair)]">
          <div className="text-[9px] mono uppercase tracking-widest text-mute">Outcome</div>
          <div className="flex items-baseline gap-3 mt-1">
            <span className={`mono text-xl font-bold ${trade.pnl_usd >= 0 ? "text-bull" : "text-bear"}`} data-testid="trade-r">{rTxt(trade.r_multiple)}</span>
            <span className={`mono text-[12px] ${trade.pnl_usd >= 0 ? "text-bull" : "text-bear"}`} data-testid="trade-pnl-text">{trade.pnl_text}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function TradeCard({ trade, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  const win = trade.pnl_usd >= 0;
  return (
    <div className="panel rise" data-testid={`journal-trade-card-${trade.id}`}>
      <button className="w-full flex items-center gap-3 px-3 py-2 text-left row-hover" onClick={() => setOpen((o) => !o)} data-testid={`trade-card-toggle-${trade.id}`}>
        {open ? <ChevronDown size={12} className="text-mute" /> : <ChevronRight size={12} className="text-mute" />}
        <span className="mono text-[10px] text-mute w-28">{dt(trade.timestamp)}</span>
        <span className={`badge ${trade.direction}`}>{trade.direction}</span>
        <span className="mono text-[10px] text-gold">L{trade.layer_number}</span>
        <span className="mono text-[11px]">{px(trade.entry)} → {trade.status === "closed" ? px(trade.exit_price) : "open"}</span>
        <span className="badge neutral">{trade.exit_reason || "open"}</span>
        <span className="badge neutral">{SESSION_LABEL[trade.session] || trade.session}</span>
        <span className="text-dim text-[10px] truncate flex-1">{trade.summary}</span>
        <span className={`mono text-[12px] font-semibold ${win ? "text-bull" : "text-bear"}`}>{rTxt(trade.r_multiple)}</span>
        <span className={`mono text-[11px] w-32 text-right ${win ? "text-bull" : "text-bear"}`}>{trade.pnl_text}</span>
      </button>
      {open && <JustificationCard trade={trade} />}
    </div>
  );
}
