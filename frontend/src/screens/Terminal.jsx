import { useEffect, useState } from "react";
import PriceChart from "@/components/PriceChart";
import AgentBoard from "@/components/AgentBoard";
import LayersPanel from "@/components/LayersPanel";
import { api } from "@/lib/api";
import { hhmmss } from "@/lib/format";

export default function Terminal({ feed, config }) {
  const { status, tick, layers, analysis, account, barUpdates, lastTrades, setStatus } = feed;
  const [events, setEvents] = useState([]);
  const [liveWeights, setLiveWeights] = useState(null);
  useEffect(() => { api.events().then(setEvents).catch(() => {}); }, [lastTrades]);
  useEffect(() => { api.weights().then(setLiveWeights).catch(() => {}); }, []);

  const toggleAuto = async () => {
    const r = await api.setAutoTrade(!status?.auto_trade);
    setStatus((s) => ({ ...s, auto_trade: r.auto_trade }));
  };
  const closeLayer = async (id) => { try { await api.closeLayer(id); } catch (e) { console.error(e); } };
  const changeWeight = async (engine, value) => {
    setLiveWeights((w) => ({ ...w, [engine]: value })); // optimistic
    try { await api.setWeights({ [engine]: value }); } catch (e) { console.error(e); }
  };
  const resetWeights = async () => { try { setLiveWeights(await api.resetWeights()); } catch (e) { console.error(e); } };

  return (
    <div className="flex-1 flex min-h-0" data-testid="terminal-screen">
      <div className="flex-1 flex flex-col min-w-0 border-r border-[var(--hair)]">
        <div className="flex-1 min-h-0"><PriceChart layers={layers} barUpdates={barUpdates} tick={tick} /></div>
        <div className="h-52 shrink-0 border-t border-[var(--hair)]"><LayersPanel layers={layers} account={account} onClose={closeLayer} tick={tick} /></div>
      </div>
      <aside className="w-[400px] shrink-0 flex flex-col min-h-0">
        <div className="flex-1 min-h-0">
          <AgentBoard analysis={analysis} weights={liveWeights ?? config?.weights} editableWeights onWeightChange={changeWeight} onResetWeights={resetWeights} />
        </div>
        <div className="h-44 shrink-0 panel border-t flex flex-col min-h-0">
          <div className="panel-head">
            <span>Execution log</span>
            <button className={`btn ${status?.auto_trade ? "active" : ""}`} onClick={toggleAuto} data-testid="auto-trade-toggle">{status?.auto_trade ? "auto-trade ON" : "auto-trade PAUSED"}</button>
          </div>
          <div className="flex-1 overflow-y-auto min-h-0 px-3 py-1 mono text-[10px]" data-testid="execution-log">
            {events.length === 0 && <div className="text-mute py-2">no fills yet · {status?.last_m5 ? `last M5 close ${hhmmss(status.last_m5)}` : "warming up"}</div>}
            {[...events].reverse().map((e, i) => (
              <div key={i} className="py-0.5 border-b border-[rgba(31,41,55,.5)] flex gap-2">
                <span className="text-mute shrink-0">{hhmmss(e.time)}</span>
                <span className={e.msg.startsWith("OPEN") ? "text-bull" : "text-dim"}>{e.msg}</span>
              </div>
            ))}
          </div>
        </div>
      </aside>
    </div>
  );
}