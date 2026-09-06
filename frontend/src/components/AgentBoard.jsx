import { ENGINE_ORDER, ENGINE_NAMES, sigColor, pct, SESSION_LABEL } from "@/lib/format";

export function VoteRow({ k, v, weight, compact = false, editable = false, onWeightChange }) {
  const sig = v?.signal || "neutral", conf = v?.confidence ?? 0;
  return (
    <div className={`px-3 ${compact ? "py-1" : "py-1.5"} border-b border-[rgba(31,41,55,.6)] row-hover`} data-testid={`agent-card-${k}`}>
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="pip" style={{ background: sigColor(sig) }} />
          <span className="mono text-[11px] font-medium truncate">{ENGINE_NAMES[k] || k}</span>
          {k === "elliott" && <span className="badge neutral" title="deliberately downweighted">low w</span>}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {editable ? (
            <span className="flex items-center gap-1">
              <span className="text-mute mono text-[9px]">w</span>
              <input className="input w-12 text-[9px] py-0.5" type="number" step="0.05" min="0" max="1"
                     value={weight ?? 1} onChange={(e) => onWeightChange?.(k, Number(e.target.value))}
                     data-testid={`live-weight-${k}`} onClick={(e) => e.stopPropagation()} />
            </span>
          ) : (
            weight !== undefined && <span className="text-mute mono text-[9px]">w{weight}</span>
          )}
          <span className="mono text-[10px] text-dim w-9 text-right">{(conf * 100).toFixed(0)}%</span>
          <span className={`badge ${sig}`} data-testid={`agent-signal-${k}`}>{sig}</span>
        </div>
      </div>
      <div className="conf-track mt-1"><div className="conf-fill" style={{ width: `${conf * 100}%`, background: sigColor(sig) }} /></div>
      {!compact && <div className="text-[10px] text-dim mt-1 leading-snug truncate" title={v?.reason} data-testid={`agent-reason-${k}`}>{v?.reason || "awaiting first bar close"}</div>}
    </div>
  );
}

export function ConsensusStrip({ consensus, bias, session, summary, gateReason, fire }) {
  if (!consensus) return <div className="px-3 py-2 text-mute text-[10px] mono">awaiting first M5 close…</div>;
  const d = consensus.direction, score = consensus.score ?? 0;
  const w = Math.min(100, Math.abs(score) / 0.6 * 100);
  return (
    <div className="px-3 py-2 border-b border-[var(--hair)] bg-[var(--elev)]" data-testid="consensus-strip">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`badge ${d}`} data-testid="consensus-direction">{d}</span>
          <span className="mono text-[13px] font-semibold" style={{ color: sigColor(d) }} data-testid="consensus-score">{score >= 0 ? "+" : ""}{score.toFixed(3)}</span>
          <span className="text-mute mono text-[10px]">{consensus.aligned}/{consensus.total} aligned · thr {consensus.threshold} / {consensus.min_aligned}</span>
        </div>
        <span className={`badge ${fire ? "gold" : "neutral"}`} data-testid="entry-fire-badge">{fire ? "ENTRY ARMED" : "GATED"}</span>
      </div>
      <div className="conf-track mt-1.5 relative">
        <div className="absolute left-1/2 top-0 bottom-0 w-px bg-[var(--hair-2)]" />
        <div className="conf-fill" style={{ left: score >= 0 ? "50%" : `${50 - w / 2}%`, width: `${w / 2}%`, background: sigColor(d) }} />
      </div>
      <div className="mt-1.5 text-[10px] leading-snug text-dim" data-testid="consensus-summary">{summary}</div>
      <div className="mt-1 flex items-center gap-2 text-[10px] mono flex-wrap">
        <span className="text-mute">BIAS</span>
        <span className={`badge ${bias?.direction || "neutral"}`} data-testid="bias-direction">{bias?.direction || "—"}</span>
        <span className="text-mute">D1 {bias?.d1_score >= 0 ? "+" : ""}{bias?.d1_score?.toFixed(2)} · H4 {bias?.h4_score >= 0 ? "+" : ""}{bias?.h4_score?.toFixed(2)}</span>
        <span className="text-mute">· {SESSION_LABEL[session] || session}</span>
      </div>
      {gateReason && <div className="mt-1 text-[10px] text-[var(--orange)] leading-snug" data-testid="gate-reason">{gateReason}</div>}
    </div>
  );
}

export default function AgentBoard({ analysis, weights = {}, compact = false, editableWeights = false, onWeightChange, onResetWeights }) {
  const votes = analysis?.votes || {};
  return (
    <div className="panel flex flex-col h-full min-h-0" data-testid="agent-board-container">
      <div className="panel-head">
        <span>10-engine consensus · M5 entry</span>
        <span className="flex items-center gap-2">
          {editableWeights && <button className="btn text-[9px]" onClick={onResetWeights} data-testid="live-reset-weights">reset weights</button>}
          <span className="text-mute">{analysis?.time ? new Date(analysis.time).toISOString().slice(11, 16) + "Z" : ""}</span>
        </span>
      </div>
      <ConsensusStrip consensus={analysis?.entry} bias={analysis?.bias} session={analysis?.session} summary={analysis?.summary} gateReason={analysis?.gate_reason} fire={analysis?.fire} />
      <div className="flex-1 overflow-y-auto min-h-0">
        {ENGINE_ORDER.map((k) => <VoteRow key={k} k={k} v={votes[k]} weight={weights[k]} compact={compact} editable={editableWeights} onWeightChange={onWeightChange} />)}
      </div>
      <TFStrip tfs={analysis?.timeframes} />
    </div>
  );
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
            <div className="mono text-[11px] font-semibold" style={{ color: sigColor(d) }}>{c ? `${c.score >= 0 ? "+" : ""}${c.score.toFixed(2)}` : "—"}</div>
            <div className="text-[9px] text-dim mono">{c ? `${c.aligned}/${c.total}` : ""}</div>
          </div>
        );
      })}
    </div>
  );
}