import { sigColor, SESSION_LABEL } from "@/lib/format";

const SHORT_TFS = ["M1", "M5", "M15", "H1", "H4"];

export default function AgentBoard({ analysis, theses = [], book }) {
  const fire = analysis?.fire;
  const gate = analysis?.gate_reason;
  const bias = analysis?.bias || {};
  const entry = analysis?.entry || {};
  const th = theses[0];
  const follow = (th?.followups || []).slice(-12).reverse();
  const state = fire ? "FIRE" : gate ? "WAIT" : "SCAN";
  const stateTone = fire ? "gold" : gate ? "wait" : "scan";

  return (
    <div className="flex flex-col h-full min-h-0 bg-[var(--surface)]" data-testid="agent-board-container">
      <TFStrip tfs={analysis?.timeframes} />

      <div className="px-3 py-2 border-b border-[var(--hair)] flex items-center justify-between">
        <div className="mono text-[10px] tracking-[.12em] uppercase text-mute">
          Desk · L{book?.layers ?? 1} · {book?.lot ?? 0.02} · SL {book?.sl ?? 1.5} / TP {book?.tp ?? 3}
        </div>
        <div className="mono text-[10px] text-mute">
          {analysis?.time ? new Date(analysis.time).toISOString().slice(11, 16) + "Z" : ""}
        </div>
      </div>

      <div className={`px-3 py-2.5 border-b border-[var(--hair)] state-${stateTone}`}>
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className={`mono text-[18px] font-semibold leading-none ${fire ? "text-gold" : gate ? "text-[var(--orange)]" : "text-cyan"}`}>
              {state}
            </div>
            <div className="mt-1.5 text-[12px] leading-snug text-[var(--t1)]">
              {fire ? "M5 passed. Next close can fill L1." : (gate || "warming")}
            </div>
          </div>
          <span className={`badge ${bias.direction || "neutral"}`}>{bias.direction || "—"}</span>
        </div>
        <div className="mt-2 grid grid-cols-3 gap-2 mono text-[10px]">
          <Meta k="M5 score" v={`${fmt(entry.score)} · ${entry.aligned ?? 0}/${entry.total ?? 10}`} />
          <Meta k="Need" v={`${entry.threshold ?? "—"} / ${entry.min_aligned ?? "—"}`} />
          <Meta k="Session" v={SESSION_LABEL[analysis?.session] || analysis?.session || "—"} />
        </div>
      </div>

      <div className="px-3 py-2 border-b border-[var(--hair)]">
        <div className="text-[9px] uppercase tracking-[.16em] text-mute mb-1">Thesis</div>
        {th ? (
          <>
            <div className="text-[12px] leading-snug">{th.plan}</div>
            <div className="mt-1.5 flex flex-wrap gap-2 mono text-[10px] text-dim">
              <span className={`badge ${th.direction}`}>{th.direction}</span>
              <span>@{th.entry}</span>
              <span className="text-[var(--orange)]">SL {th.sl}</span>
              <span className="text-cyan">TP {th.tp ?? "—"}</span>
              <span>{th.session}</span>
            </div>
          </>
        ) : (
          <div className="text-[11px] text-mute leading-snug">
            No open clip. Brain idle until L1 fills, then one note per minute.
          </div>
        )}
      </div>

      <div className="flex-1 min-h-0 flex flex-col">
        <div className="px-3 pt-2 text-[9px] uppercase tracking-[.16em] text-mute">Follow-ups</div>
        <div className="flex-1 overflow-y-auto min-h-0 px-3 py-1">
          {follow.length === 0 && <div className="text-[10px] text-mute mono py-1">No notes yet.</div>}
          {follow.map((f, i) => (
            <div key={i} className="py-1 border-b border-[rgba(31,41,55,.4)] flex gap-2 mono text-[10px]">
              <span className="text-mute shrink-0 w-10">{String(f.time || "").slice(11, 16)}</span>
              <span className={f.action === "time_stop" ? "text-bear" : f.action === "open" ? "text-gold" : "text-dim"}>{f.msg}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Meta({ k, v }) {
  return (
    <div className="bg-[var(--bg)] border border-[var(--hair)] px-2 py-1.5">
      <div className="text-[8px] uppercase tracking-widest text-mute">{k}</div>
      <div className="text-[11px] text-[var(--t1)]">{v}</div>
    </div>
  );
}

function fmt(n) {
  if (n == null || Number.isNaN(Number(n))) return "—";
  const x = Number(n);
  return `${x >= 0 ? "+" : ""}${x.toFixed(2)}`;
}

function TFStrip({ tfs }) {
  return (
    <div className="grid grid-cols-5 border-b border-[var(--hair)]" data-testid="timeframe-consensus-strip">
      {SHORT_TFS.map((tf) => {
        const c = tfs?.[tf]?.consensus;
        const d = c?.direction || "neutral";
        return (
          <div key={tf} className="px-1.5 py-2 border-r border-[var(--hair)] last:border-r-0 text-center bg-[var(--head)]">
            <div className="text-[9px] text-mute mono tracking-[.14em]">{tf}</div>
            <div className="mono text-[13px] font-semibold leading-tight" style={{ color: sigColor(d) }}>{c ? fmt(c.score) : "—"}</div>
            <div className="text-[9px] text-dim mono">{c ? `${c.aligned}/${c.total}` : "—"}</div>
          </div>
        );
      })}
    </div>
  );
}
