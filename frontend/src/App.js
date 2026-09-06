import { useEffect, useState } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import "@/App.css";
import useLiveFeed from "@/hooks/useLiveFeed";
import TopBar from "@/components/TopBar";
import NewsBanner from "@/components/NewsBanner";
import Terminal from "@/screens/Terminal";
import Journal from "@/screens/Journal";
import BacktestLab from "@/screens/BacktestLab";
import { api } from "@/lib/api";

export default function App() {
  const feed = useLiveFeed();
  const [config, setConfig] = useState(null);
  useEffect(() => { api.config().then(setConfig).catch(() => {}); }, []);
  return (
    <BrowserRouter>
      <div className="h-screen w-screen flex flex-col overflow-hidden bg-[var(--bg)]" data-testid="app-root">
        <div className="grain" />
        <TopBar status={feed.status} account={feed.account} tick={feed.tick} connected={feed.connected} transport={feed.transport} />
        <NewsBanner news={feed.news} advisory={feed.advisory} simTime={feed.tick?.time} />
        <Routes>
          <Route path="/" element={<Terminal feed={feed} config={config} />} />
          <Route path="/journal" element={<Journal feed={feed} />} />
          <Route path="/backtest" element={<BacktestLab feed={feed} config={config} />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}
