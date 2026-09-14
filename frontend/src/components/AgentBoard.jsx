import { sigColor, SESSION_LABEL } from "@/lib/format";

export default function AgentBoard({ analysis, theses = [], book }) {
  const fire = analysis?.fire;
  const gate = analysis?.gate_reason;
  const bias = analysis?.bias || {};
  const entry = analysis?.entry || {};
  const th = theses[0];
  const follow = (th?.followups || []).slice(-8).reverse();
  const state = fire ? "FIRE" : gate ? "WAIT" : "SCAN";
  const stateCls = fire ? "text-gold" : "text-[var(--orange)]";

  return (
    <div className="panel flex flex-col h-full min-h-0" data-testid="agent-board-container">
      <div className="panel-head">
        <span>Desk · L{book?.layers ?? 1} · {book?.lot ?? 0.02} · SL {book?.sl ?? 1.5} / TP {book?.tp ?? 3}</span>
        <span className="text-mute">{analysis?.time ? new Date(analysis.time).toISOString().slice(11, 16) + "Z" : ""}</span>
      </div>

      <div className="px-3 py-2 border-b border-[var(--hair)] bg-[var(--elev)]">
        <div className="flex items-center justify-between">
          <span className={`mono text-[15px] font-semibold ${stateCls}`}>{state}</span>
          <span className={`badge ${bias.direction || "neutral"}`}>{bias.direction || "—"}</span>
        </div>
        <div className="mt-1 text-[11px] leading-snug text-dim">
          {fire ? "M5 passed. Next close can fill L1." : (gate || "warming")}
        </div>
        <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-[10px] mono text-mute">
          <span>M5 {fmt(entry.score)} · {entry.aligned ?? 0}/{entry.total ?? 10} need {entry.threshold}/{entry.min_aligned}</span>
          <span>{SESSION_LABEL[analysis?.session] || analysis?.session || "—"}</span>
          <span>H1 {fmt(bias.h1_score)} · H4 {fmt(bias.h4_score)}</span>
        </div>
      </div>

      <div className="px-3 py-2 border-b border-[var(--hair)]">
        <div className="text-[9px] uppercase tracking-widest text-mute mb-1">Thesis</div>
        {th ? (
          <>
            <div className="text-[11px] leading-snug">{th.plan}</div>
            <div className="mt-1 mono text-[10px] text-dim">
              {th.direction} @{th.entry} · SL {th.sl} · TP {th.tp ?? "—"} · {th.session}
            </div>
          </>
        ) : (
          <div className="text-[11px] text-mute">No open clip. Brain idle until L1 fills, then one note per minute.</div>
        )}
      </div>

      <div className="flex-1 overflow-y-auto min-h-0 px-3 py-2">
        <div className="text-[9px] uppercase tracking-widest text-mute mb-1">Follow-ups</div>
        {follow.length === 0 && <div className="text-[10px] text-mute mono">—</div>}
        {follow.map((f, i) => (
          <div key={i} className="py-0.5 mono text-[10px] border-b border-[rgba(31,41,55,.4)] flex gap-2">
            <span className="text-mute shrink-0">{String(f.time || "").slice(11, 16)}</span>
            <span className={f.action === "time_stop" ? "text-bear" : f.action === "open" ? "text-gold" : "text-dim"}>{f.msg}</span>
          </div>
        ))}
      </div>

      <TFStrip tfs={analysis?.timeframes} />
    </div>
  );
}

function fmt(n) {
  if (n == null || Number.isNaN(Number(n))) return "—";
  const x = Number(n);
  return `${x >= 0 ? "+" : ""}${x.toFixed(2)}`;
}

function TFStrip({ tfs }) {
  if (!tfs) return null;
  return (
    <div className="grid grid-cols-5 border-t border-[var(--hair)]" data-testid="timeframe-consensus-strip">
      {["D1", "H4", "H1", "M15", "M5"].map((tf) => {
        const c = tfs[tf]?.consensus; const d = c?.direction || "neutral";
        return (
          <div key={tf} className="px-2 py-1.5 border-r border-[var(--hair)] last:border-r-0 text-center">
            <div className="text-[9px] text-mute mono tracking-widest">{tf}</div>
            <div className="mono text-[11px] font-semibold" style={{ color: sigColor(d) }}>{c ? fmt(c.score) : "—"}</div>
            <div className="text-[9px] text-dim mono">{c ? `${c.aligned}/${c.total}` : ""}</div>
          </div>
        );
      })}
    </div>
  );
}
