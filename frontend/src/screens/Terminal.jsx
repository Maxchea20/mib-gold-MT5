import { useEffect, useState } from "react";
import PriceChart from "@/components/PriceChart";
import AgentBoard from "@/components/AgentBoard";
import LayersPanel from "@/components/LayersPanel";
import { api } from "@/lib/api";
import { hhmmss } from "@/lib/format";

export default function Terminal({ feed }) {
  const { status, tick, layers, analysis, account, barUpdates, lastTrades, setStatus } = feed;
  const [events, setEvents] = useState([]);
  useEffect(() => { api.events().then(setEvents).catch(() => {}); }, [lastTrades]);

  const toggleAuto = async () => {
    const r = await api.setAutoTrade(!status?.auto_trade);
    setStatus((s) => ({ ...s, auto_trade: r.auto_trade }));
  };
  const closeLayer = async (id) => { try { await api.closeLayer(id); } catch (e) { console.error(e); } };

  return (
    <div className="flex-1 flex min-h-0" data-testid="terminal-screen">
      <div className="flex-1 flex flex-col min-w-0 border-r border-[var(--hair)]">
        <div className="flex-1 min-h-0"><PriceChart layers={layers} barUpdates={barUpdates} tick={tick} /></div>
        <div className="h-40 shrink-0 border-t border-[var(--hair)]">
          <LayersPanel layers={layers} account={account} book={status?.book_rules} onClose={closeLayer} tick={tick} />
        </div>
      </div>
      <aside className="w-[420px] shrink-0 flex flex-col min-h-0">
        <div className="h-[46%] min-h-[280px] shrink-0 border-b border-[var(--hair)]">
          <AgentBoard analysis={analysis} theses={status?.theses || []} book={status?.book_rules} />
        </div>
        <div className="flex-1 min-h-0 panel border-0 flex flex-col">
          <div className="panel-head">
            <span>Execution log</span>
            <button className={`btn ${status?.auto_trade ? "active" : ""}`} onClick={toggleAuto} data-testid="auto-trade-toggle">
              {status?.auto_trade ? "auto-trade ON" : "auto-trade PAUSED"}
            </button>
          </div>
          <div className="flex-1 overflow-y-auto min-h-0 px-3 py-1 mono text-[11px]" data-testid="execution-log">
            {events.length === 0 && (
              <div className="text-mute py-2">no fills yet · {status?.last_m5 ? `last M5 close ${hhmmss(status.last_m5)}` : "warming up"}</div>
            )}
            {[...events].reverse().map((e, i) => (
              <div key={i} className="py-1 border-b border-[rgba(31,41,55,.5)] flex gap-2 leading-snug">
                <span className="text-mute shrink-0">{hhmmss(e.time)}</span>
                <span className={e.msg.startsWith("OPEN") || e.msg.startsWith("THESIS") ? "text-bull" : "text-dim"}>{e.msg}</span>
              </div>
            ))}
          </div>
        </div>
      </aside>
    </div>
  );
}
