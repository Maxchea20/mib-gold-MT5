import { NavLink } from "react-router-dom";
import { Activity, Radio, Wifi, WifiOff } from "lucide-react";
import { usd, SESSION_LABEL } from "@/lib/format";

function Metric({ label, value, sub, cls = "", testId }) {
  return (
    <div className="flex flex-col justify-center px-4 border-r border-[var(--hair)] h-full min-w-[120px]" data-testid={testId}>
      <span className="text-[9px] uppercase tracking-[.14em] text-mute mono">{label}</span>
      <span className={`mono text-[15px] font-semibold leading-tight ${cls}`}>{value}</span>
      {sub && <span className="text-[10px] text-dim mono">{sub}</span>}
    </div>
  );
}

export default function TopBar({ status, account, tick, connected, transport }) {
  const eq = account?.equity, today = account?.today_pnl ?? 0;
  const book = status?.book_rules || {};
  const lot = Number(book.lot ?? 0.02);
  const sl = book.sl ?? 1.5;
  const tp = book.tp ?? 3;
  const layers = book.layers ?? account?.max_layers ?? 1;
  const clip = lot * sl * 100;
  const session = status?.session;
  const tabs = [["terminal", "/", "Terminal"], ["journal", "/journal", "Journal"], ["backtest", "/backtest", "Backtest Lab"]];
  return (
    <header className="h-12 flex items-stretch bg-[var(--surface)] border-b border-[var(--hair)] shrink-0 z-40" data-testid="top-status-bar">
      <div className="flex items-center gap-2 px-4 border-r border-[var(--hair)]">
        <span className="pip bg-gold" />
        <span className="mono font-bold tracking-[.2em] text-[13px] text-gold">MIB-GOLD</span>
        <span className="badge gold ml-1" data-testid="mode-badge">{status?.mode || "..."}</span>
      </div>
      <Metric label="Equity" value={usd(eq)} sub={`bal ${usd(account?.balance)}`} cls="text-gold" testId="metric-account-equity" />
      <Metric label="Today P&L" value={usd(today, true)} sub={`floating ${usd(account?.floating_pnl ?? 0, true)}`} cls={today >= 0 ? "text-bull" : "text-bear"} testId="metric-today-pnl" />
      <div className="flex flex-col justify-center px-4 border-r border-[var(--hair)] min-w-[190px]" data-testid="metric-risk-gauge">
        <div className="flex justify-between text-[9px] uppercase tracking-[.14em] text-mute mono"><span>Keeper book</span><span>L{layers}</span></div>
        <span className="mono text-[15px] font-semibold leading-tight">{lot} lot - SL {sl} / TP {tp}</span>
        <span className="text-[10px] text-dim mono">clip {usd(clip)} - no trail - news +/-30m</span>
      </div>
      <Metric label="XAUUSD" value={tick ? tick.bid.toFixed(2) : "-"} sub={tick ? `ask ${tick.ask.toFixed(2)} - spr ${(tick.ask - tick.bid).toFixed(2)}` : ""} testId="metric-price" />
      <Metric label="Session" value={SESSION_LABEL[session] || "-"} sub={tick ? new Date(tick.time).toISOString().slice(0, 16).replace("T", " ") + "Z" : ""} cls="text-cyan" testId="metric-session" />
      <div className="flex-1" />
      <nav className="flex items-stretch">
        {tabs.map(([k, to, label]) => (
          <NavLink key={k} to={to} end={to === "/"} data-testid={`nav-tab-${k}`}
            className={({ isActive }) => `px-5 flex items-center mono text-[10px] tracking-[.16em] uppercase border-l border-[var(--hair)] transition-colors duration-150 ${isActive ? "text-gold bg-[rgba(234,179,8,.08)] shadow-[inset_0_-2px_0_var(--gold)]" : "text-dim hover:text-white"}`}>
            {label}
          </NavLink>
        ))}
      </nav>
      <div className="flex items-center gap-2 px-4 border-l border-[var(--hair)] mono text-[10px]" data-testid="connection-indicator">
        {connected ? <Wifi size={12} className="text-bull" /> : <WifiOff size={12} className="text-bear" />}
        <span className={connected ? "text-bull" : "text-dim"}>{transport}</span>
        <Radio size={12} className={status?.connection?.connected ? "text-cyan" : "text-mute"} />
        <span className="text-dim">{status?.connection?.mode === "mt5" ? "MT5 bridge" : `sim ${status?.connection?.speed || ""}x`}</span>
        <Activity size={12} className={status?.auto_trade ? "text-gold" : "text-mute"} />
      </div>
    </header>
  );
}
