import { useEffect, useState } from "react";
import { ShieldAlert, ShieldCheck, Brain } from "lucide-react";
import { countdown } from "@/lib/format";

export default function NewsBanner({ news, advisory, simTime }) {
  const [, force] = useState(0);
  useEffect(() => { const t = setInterval(() => force((x) => x + 1), 1000); return () => clearInterval(t); }, []);
  const blocked = news?.blocked;
  // countdown is anchored on the feed's own clock (sim or real) so it stays honest at accelerated speeds
  const ref = simTime ? new Date(simTime).getTime() : Date.now();
  let toEvent = null, toClear = null;
  if (blocked && news.event) {
    toEvent = (new Date(news.event.time).getTime() - ref) / 1000;
    toClear = toEvent + news.window_after_min * 60;
  }
  const next = news?.upcoming?.[0];
  const toNext = next ? (new Date(next.time).getTime() - ref) / 1000 : null;
  return (
    <div data-testid="news-gate-banner" data-blocked={blocked ? "true" : "false"}
      className={`h-7 shrink-0 flex items-center justify-between px-4 mono text-[10px] tracking-[.08em] border-b transition-colors duration-300 ${blocked ? "bg-[rgba(239,68,68,.16)] border-[#dc2626] text-[#fca5a5]" : "bg-[var(--surface)] border-[var(--hair)] text-dim"}`}>
      <div className="flex items-center gap-3">
        {blocked ? <ShieldAlert size={13} className="text-bear pulse" /> : <ShieldCheck size={13} className="text-bull" />}
        {blocked ? (
          <>
            <span className="uppercase font-semibold text-bear">News gate active</span>
            <span className="text-white">{news.event.title}</span>
            <span>{toEvent > 0 ? `releases in ${countdown(toEvent)}` : `released ${countdown(-toEvent)} ago`}</span>
            <span className="text-mute">·</span>
            <span>entries unlock in <span className="text-white">{countdown(toClear)}</span></span>
            <span className="text-mute">· all new entries blocked · trailing stops still managed</span>
          </>
        ) : (
          <>
            <span className="uppercase text-bull">Gate clear</span>
            {next ? <span>next high-impact: <span className="text-white">{next.title}</span> ({next.country}) in {countdown(toNext)} · window ±{news.window_before_min}m</span>
              : <span>no high-impact USD events loaded {news?.fetch_error ? "· feed error, using cache/manual" : ""}</span>}
          </>
        )}
      </div>
      <div className="flex items-center gap-3">
        {advisory && (
          <span className="flex items-center gap-1" data-testid="ai-advisory-flag">
            <Brain size={12} className="text-cyan" />
            <span className="text-cyan uppercase">AI bias {advisory.bias}</span>
            <span className="text-dim truncate max-w-[380px]">{advisory.note}</span>
          </span>
        )}
        <span className="text-mute">{news?.events_loaded ?? 0} events · hard gate: rule-based, 0 latency</span>
      </div>
    </div>
  );
}
