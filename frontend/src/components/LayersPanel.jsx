import { X } from "lucide-react";
import { usd, px, rTxt, hhmmss } from "@/lib/format";

export default function LayersPanel({ layers = [], account, onClose, tick }) {
  return (
    <div className="panel flex flex-col h-full min-h-0" data-testid="active-layers-panel">
      <div className="panel-head">
        <span>Active layers · {layers.length}/{account?.max_layers ?? 3} per direction · shared 10% stop</span>
        <span className="text-mute">risk used {usd(account?.risk_used_usd ?? 0)} · floating <span className={account?.floating_pnl >= 0 ? "text-bull" : "text-bear"}>{usd(account?.floating_pnl ?? 0, true)}</span></span>
      </div>
      <div className="flex-1 overflow-auto min-h-0">
        {layers.length === 0 ? (
          <div className="h-full flex items-center justify-center text-mute mono text-[10px] tracking-widest uppercase" data-testid="layers-empty">no open layers · waiting for top-down confluence</div>
        ) : (
          <table className="tbl">
            <thead><tr><th>Layer</th><th>Dir / Lots</th><th>Entry</th><th>Now</th><th>R-multiple</th><th>Floating $</th><th>SL dist</th><th>SL</th><th>Trailing TP</th><th>Risk</th><th></th></tr></thead>
            <tbody>
              {layers.map((l) => (
                <tr key={l.id} className="row-hover mono text-[11px]" data-testid={`layer-row-${l.id}`}>
                  <td><span className="text-gold font-semibold">L{l.layer_number}</span> <span className="text-mute">{hhmmss(l.timestamp)}</span></td>
                  <td><span className={`badge ${l.direction}`}>{l.direction}</span> <span className="text-dim ml-1">{l.lots}</span></td>
                  <td>{px(l.entry)}</td>
                  <td>{px(l.current_price)}</td>
                  <td className={l.r_multiple >= 0 ? "text-bull" : "text-bear"} data-testid={`layer-r-${l.id}`}>{rTxt(l.r_multiple)}</td>
                  <td className={l.pnl_usd >= 0 ? "text-bull" : "text-bear"} data-testid={`layer-pnl-${l.id}`}>{l.pnl_text}</td>
                  <td>{px(l.sl_distance)}</td>
                  <td className="text-[var(--orange)]">{px(l.sl)}</td>
                  <td className="text-cyan">{l.trail_active ? px(l.trail_level) : <span className="text-mute">arms at +1R</span>}</td>
                  <td className="text-dim">{usd(l.risk_usd)}</td>
                  <td><button className="btn danger" onClick={() => onClose(l.id)} data-testid={`close-layer-${l.id}`} title="close layer"><X size={10} /></button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
