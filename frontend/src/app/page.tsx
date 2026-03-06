"use client";

import { useEffect, useState, useCallback } from "react";
import { RefreshCw } from "lucide-react";
import { Panel, Group as PanelGroup, Separator as PanelResizeHandle } from "react-resizable-panels";
import {
  fetchStatus, fetchAlarms, fetchRiskTrend,
  type DashboardStatus, type Alarm, type RiskPoint,
} from "@/lib/api";
import StatusCards    from "@/components/StatusCards";
import AlarmTable     from "@/components/AlarmTable";
import RiskTrendChart from "@/components/RiskTrendChart";
import VideoStream    from "@/components/VideoStream";
import ChatPanel      from "@/components/ChatPanel";

export default function DashboardPage() {
  const [status,  setStatus]  = useState<DashboardStatus | null>(null);
  const [alarms,  setAlarms]  = useState<Alarm[]>([]);
  const [trend,   setTrend]   = useState<RiskPoint[]>([]);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const [refreshing,  setRefreshing]  = useState(false);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      const [s, a, t] = await Promise.allSettled([fetchStatus(), fetchAlarms(), fetchRiskTrend()]);
      if (s.status === "fulfilled") setStatus(s.value);
      if (a.status === "fulfilled") setAlarms(a.value.items);
      if (t.status === "fulfilled") setTrend(t.value.items);
      setLastRefresh(new Date());
    } finally { setRefreshing(false); }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 10_000);
    return () => clearInterval(id);
  }, [refresh]);

  const risk = status?.riskLevel ?? "low";
  const riskColor = risk === "high" ? "var(--red)" : risk === "medium" ? "var(--orange)" : "var(--green)";
  const riskLabel = risk === "high" ? "高风险" : risk === "medium" ? "中风险" : "低风险";

  return (
    <div style={{
      display: "flex", flexDirection: "column", height: "100vh",
      overflow: "hidden", background: "var(--bg)", gap: 0, padding: 16,
    }}>
      {/* ── Header ─────────────────────────────────────────────── */}
      <header style={{
        display: "flex", alignItems: "center",
        height: 56, flexShrink: 0, padding: "0 20px",
        background: "rgba(255, 255, 255, 0.96)",
        backdropFilter: "blur(24px) saturate(180%)",
        WebkitBackdropFilter: "blur(24px) saturate(180%)",
        border: "0.5px solid var(--border)",
        borderRadius: "var(--radius)",
        boxShadow: "0 2px 12px rgba(0,0,0,0.06), 0 1px 3px rgba(0,0,0,0.04)",
      }}>

        {/* ── Logo ── */}
        <div style={{ display: "flex", alignItems: "center", gap: 12, flexShrink: 0 }}>
          <div style={{
            width: 38, height: 38, borderRadius: 12, flexShrink: 0,
            background: "linear-gradient(135deg, rgba(255,59,48,0.14) 0%, rgba(255,149,0,0.10) 100%)",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 20, lineHeight: 1,
          }}>🔥</div>
          <div>
            <div style={{ fontSize: 15, fontWeight: 800, color: "var(--t1)", letterSpacing: "-0.03em", lineHeight: 1.1 }}>
              FireGuard AI
            </div>
            <div style={{ fontSize: 11, color: "var(--t3)", lineHeight: 1, marginTop: 3, letterSpacing: "0.02em" }}>
              智能消防监控平台
            </div>
          </div>
        </div>

        {/* ── Divider ── */}
        <div style={{ width: 1, height: 32, background: "var(--sep)", margin: "0 20px", flexShrink: 0 }} />

        {/* ── Risk badge ── */}
        <span style={{
          borderRadius: 100, padding: "5px 14px",
          fontSize: 13, fontWeight: 700, letterSpacing: "-0.01em", flexShrink: 0,
          background: `color-mix(in srgb, ${riskColor} 13%, transparent)`,
          color: riskColor,
          border: `1px solid color-mix(in srgb, ${riskColor} 28%, transparent)`,
        }}>
          {riskLabel}
        </span>

        {/* ── Live status ── */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginLeft: 14, flexShrink: 0 }}>
          {status?.stream?.is_running ? (
            <>
              <span className="live-dot" style={{
                display: "inline-block", width: 8, height: 8, borderRadius: "50%",
                background: "var(--green)",
                boxShadow: "0 0 0 3px rgba(52,199,89,0.22)",
              }} />
              <span style={{ fontSize: 13, fontWeight: 500, color: "var(--t2)" }}>监控运行中</span>
            </>
          ) : (
            <>
              <span style={{
                display: "inline-block", width: 8, height: 8,
                borderRadius: "50%", background: "var(--t4)",
              }} />
              <span style={{ fontSize: 13, color: "var(--t3)" }}>监控已停止</span>
            </>
          )}
        </div>

        {/* ── Spacer ── */}
        <div style={{ flex: 1 }} />

        {/* ── Refresh ── */}
        <button onClick={refresh} disabled={refreshing} aria-label="刷新数据"
          style={{
            display: "flex", alignItems: "center", gap: 8,
            cursor: "pointer", padding: "8px 16px", borderRadius: 12,
            fontSize: 13, fontWeight: 500, color: "var(--t2)",
            background: "var(--panel-2)",
            border: "0.5px solid var(--border)",
            opacity: refreshing ? 0.5 : 1,
            transition: "all 180ms",
            fontFamily: "'SF Mono', ui-monospace, 'Menlo', monospace",
          }}>
          <RefreshCw size={13} style={{
            animation: refreshing ? "spin 1s linear infinite" : "none",
            color: "var(--t3)", flexShrink: 0,
          }} />
          {lastRefresh ? lastRefresh.toLocaleTimeString("zh-CN", { hour12: false }) : "--:--:--"}
        </button>

      </header>

      {/* ── Header gap ── */}
      <div style={{ height: 12, flexShrink: 0 }} />

      {/* ── All resizable content ──────────────────────────────────── */}
      <div style={{ flex: 1, minHeight: 0 }}>
        <PanelGroup orientation="vertical" style={{ height: "100%", display: "flex", flexDirection: "column" }}>

          {/* ── Status cards row (resizable) ── */}
          <Panel defaultSize="64px" minSize="50px" maxSize="220px">
            <StatusCards status={status} />
          </Panel>

          <PanelResizeHandle className="resize-handle-h" />

          {/* ── Main content ── */}
          <Panel minSize="400px">
            <PanelGroup orientation="horizontal" style={{ height: "100%", display: "flex", gap: 0 }}>
              {/* ── Left column ── */}
              <Panel defaultSize={54} minSize="360px">
                <PanelGroup orientation="vertical" style={{ height: "100%", display: "flex", flexDirection: "column" }}>
                  {/* Video */}
                  <Panel defaultSize={76} minSize="120px">
                    <VideoStream />
                  </Panel>
                  <PanelResizeHandle className="resize-handle-h" />
                  {/* Bottom row: Risk chart + Alarms side by side */}
                  <Panel defaultSize={24} minSize="100px">
                    <PanelGroup orientation="horizontal" style={{ height: "100%", display: "flex" }}>
                      <Panel defaultSize={55} minSize="180px">
                        <RiskTrendChart data={trend} />
                      </Panel>
                      <PanelResizeHandle className="resize-handle-v" />
                      <Panel defaultSize={45} minSize="180px">
                        <AlarmTable alarms={alarms} />
                      </Panel>
                    </PanelGroup>
                  </Panel>
                </PanelGroup>
              </Panel>

              <PanelResizeHandle className="resize-handle-v" />

              {/* ── Right column: Chat only ── */}
              <Panel defaultSize={46} minSize="360px">
                <ChatPanel />
              </Panel>
            </PanelGroup>
          </Panel>

        </PanelGroup>
      </div>

      <style>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
      `}</style>
    </div>
  );
}
