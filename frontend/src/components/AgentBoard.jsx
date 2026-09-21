import { SESSION_LABEL } from "@/lib/format";

export default function AgentBoard({ analysis, theses = [], book }) {
  const hunt = analysis?.hunt || {};
  const fire = hunt.action === "FIRE" || analysis?.fire;
  const why = (hunt.why_state && hunt.why_state[0]) || analysis?.gate_reason || "warming";
  const dir = (hunt.direction || analysis?.bias?.direction || "neutral").toString().toLowerCase();
  const th = theses[0];
  const follow = (th?.followups || []).slice(-12).reverse();
  const state = fire ? "FIRE" : "WAIT";
  const setupState = hunt.structure_state || (fire ? "FIRED" : "WAITING");
  const sl = book?.sl ?? 2.5;
  const tp = book?.tp ?? 5;
  const lot = book?.lot ?? 0.01;
  const ver = book?.version || "HUNT_PULLBACK_2.5_5";

  return (
    <div className="flex flex-col h-full min-h-0 bg-[var(--surface)]" data-testid="agent-board-container">
      <div className="grid grid-cols-4 border-b border-[var(--hair)]">
        <Cell k="15m" v={hunt.event || "-"} />
        <Cell k="4h wx" v={hunt.weather_flag || hunt.hunt?.weather || "-"} />
        <Cell k="setup" v={setupState} />
        <Cell k="RR" v={hunt.rr || "2.5:5"} gold />
      </div>

      <div className="px-3 py-2 border-b border-[var(--hair)] flex items-center justify-between">
        <div className="mono text-[10px] tracking-[.12em] uppercase text-mute">
          Hunt pullback - L{book?.layers ?? 1} - {lot} - SL {sl} / TP {tp} - {ver}
        </div>
        <div className="mono text-[10px] text-mute">
          {analysis?.time ? new Date(analysis.time).toISOString().slice(11, 16) + "Z" : ""}
        </div>
      </div>

      <div className={`px-3 py-2.5 border-b border-[var(--hair)] ${fire ? "state-gold" : "state-wait"}`}>
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className={`mono text-[18px] font-semibold leading-none ${fire ? "text-gold" : "text-[var(--orange)]"}`}>
              {state}
            </div>
            <div className="mt-1.5 text-[12px] leading-snug text-[var(--t1)]">{why}</div>
          </div>
          <span className={`badge ${dir}`}>{dir === "long" || dir === "short" ? dir.toUpperCase() : "FLAT"}</span>
        </div>
        <div className="mt-2 grid grid-cols-3 gap-2 mono text-[10px]">
          <Meta k="setup id" v={hunt.setup_id || hunt.event || "-"} />
          <Meta k="path" v={hunt.hunt?.m5_path || hunt.m5_path || "-"} />
          <Meta k="session" v={SESSION_LABEL[analysis?.session] || analysis?.session || "-"} />
        </div>
        {fire && (
          <div className="mt-2 grid grid-cols-3 gap-2 mono text-[10px]">
            <Meta k="entry" v={num(hunt.entry)} />
            <Meta k="SL" v={num(hunt.stop)} />
            <Meta k="TP" v={num(hunt.target)} />
          </div>
        )}
      </div>

      <div className="px-3 py-2 border-b border-[var(--hair)]">
        <div className="text-[9px] uppercase tracking-[.16em] text-mute mb-1">Open clip</div>
        {th ? (
          <>
            <div className="text-[12px] leading-snug">{th.plan || "Hunt pullback clip live."}</div>
            <div className="mt-1.5 flex flex-wrap gap-2 mono text-[10px] text-dim">
              <span className={`badge ${th.direction}`}>{th.direction}</span>
              <span>@{th.entry}</span>
              <span className="text-[var(--orange)]">SL {th.sl}</span>
              <span className="text-cyan">TP {th.tp ?? "-"}</span>
            </div>
          </>
        ) : (
          <div className="text-[11px] text-mute leading-snug">
            Flat. Waiting M5 pullback to the 15m FVG / broken level. No chase.
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

function Cell({ k, v, gold }) {
  return (
    <div className="px-1.5 py-2 border-r border-[var(--hair)] last:border-r-0 text-center bg-[var(--head)]">
      <div className="text-[9px] text-mute mono tracking-[.14em]">{k}</div>
      <div className={`mono text-[12px] font-semibold leading-tight ${gold ? "text-gold" : ""}`}>{v}</div>
    </div>
  );
}

function Meta({ k, v }) {
  return (
    <div className="bg-[var(--bg)] border border-[var(--hair)] px-2 py-1.5">
      <div className="text-[8px] uppercase tracking-widest text-mute">{k}</div>
      <div className="text-[11px] text-[var(--t1)] break-all">{v}</div>
    </div>
  );
}

function num(n) {
  if (n == null || Number.isNaN(Number(n))) return "-";
  return Number(n).toFixed(2);
}
