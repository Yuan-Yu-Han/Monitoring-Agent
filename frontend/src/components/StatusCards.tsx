"use client";

import type { DashboardStatus } from "@/lib/api";

interface Card {
  label: string;
  value: string | number;
  sub?: string;
  emoji: string;
  color: string;
  bg: string;
}

export default function StatusCards({ status }: { status: DashboardStatus | null }) {
  const risk = status?.riskLevel ?? "low";
  const riskColor = risk === "high" ? "var(--red)" : risk === "medium" ? "var(--orange)" : "var(--green)";
  const riskBg   = risk === "high" ? "var(--red-a)" : risk === "medium" ? "var(--orange-a)" : "var(--green-a)";
  const riskLabel = risk === "high" ? "高风险" : risk === "medium" ? "中风险" : "低风险";
  const targetCount = status?.targetCount ?? status?.personCount ?? 0;
  const monitorState = (status?.monitorState || "").toLowerCase();
  const stateLabel =
    monitorState === "alarm" ? "报警" :
    monitorState === "suspect" ? "可疑" :
    monitorState === "idle" ? "空闲" :
    "未知";
  const streak = status?.detectionStreak ?? 0;

  const cards: Card[] = [
    {
      label: "综合风险",
      value: riskLabel,
      emoji: "🛡️",
      color: riskColor,
      bg: riskBg,
    },
    {
      label: "火情置信",
      value: `${status?.fireProbability?.toFixed(1) ?? "0.0"}%`,
      emoji: "🔥",
      color: "var(--orange)",
      bg: "var(--orange-a)",
    },
    {
      label: "当前状态",
      value: stateLabel,
      sub: streak > 0 ? `命中×${streak}` : undefined,
      emoji: "🧭",
      color: monitorState === "alarm" ? "var(--red)" : monitorState === "suspect" ? "var(--orange)" : "var(--blue)",
      bg: monitorState === "alarm" ? "var(--red-a)" : monitorState === "suspect" ? "var(--orange-a)" : "var(--blue-a)",
    },
    {
      label: "近期异常",
      value: status?.unresolvedAlarms ?? 0,
      sub: "条",
      emoji: "🔔",
      color: "var(--purple)",
      bg: "var(--purple-a)",
    },
  ];

  return (
    <div className="grid grid-cols-4 h-full gap-4" style={{ overflow: "hidden" }}>
      {cards.map((c) => (
        <div key={c.label} className="panel"
          style={{ display: "flex", flexDirection: "row", alignItems: "center", gap: 16, padding: "0 22px", overflow: "hidden" }}>
          {/* Emoji */}
          <span style={{ fontSize: 26, lineHeight: 1, flexShrink: 0 }}>{c.emoji}</span>
          {/* Text */}
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: "var(--t3)", letterSpacing: "0.05em", textTransform: "uppercase", whiteSpace: "nowrap" }}>
              {c.label}
            </div>
            <div style={{ display: "flex", alignItems: "baseline", gap: 4, marginTop: 4 }}>
              <span style={{ fontSize: 20, fontWeight: 700, lineHeight: 1, letterSpacing: "-0.03em", color: "var(--t1)" }}>
                {c.value}
              </span>
              {c.sub && (
                <span style={{ fontSize: 13, color: "var(--t2)" }}>{c.sub}</span>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
