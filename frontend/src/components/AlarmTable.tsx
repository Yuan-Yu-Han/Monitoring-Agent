"use client";

import type { Alarm } from "@/lib/api";

const SEV = {
  critical: { label: "严重", color: "var(--red)",    bg: "var(--red-a)"    },
  warning:  { label: "警告", color: "var(--orange)", bg: "var(--orange-a)" },
  info:     { label: "信息", color: "var(--t3)",      bg: "var(--panel-2)"  },
};

export default function AlarmTable({ alarms }: { alarms: Alarm[] }) {
  return (
    <div className="panel panel-col h-full">
      <div className="panel-hd">
        <span className="panel-title">🚨 告警记录</span>
        {alarms.length > 0 && (
          <span className="ml-auto text-[10px] tabular-nums" style={{ color: "var(--t3)" }}>
            {alarms.length} 条
          </span>
        )}
      </div>

      {/* Header */}
      <div className="grid grid-cols-[68px_1fr_60px] gap-2 px-4 py-2"
        style={{ borderBottom: "0.5px solid var(--sep)" }}>
        {["时间", "描述", "等级"].map(h => (
          <div key={h} className="text-[11px] font-semibold tracking-wide uppercase" style={{ color: "var(--t3)" }}>
            {h}
          </div>
        ))}
      </div>

      {/* Rows */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        {alarms.length === 0 ? (
          <div className="flex h-full items-center justify-center text-[11px]" style={{ color: "var(--t3)" }}>
            暂无告警
          </div>
        ) : (
          alarms.map((a, i) => {
            const sev = SEV[a.severity as keyof typeof SEV] ?? SEV.info;
            return (
              <div key={a.id ?? i}
                className="grid grid-cols-[68px_1fr_60px] gap-2 px-4 py-2.5 transition-colors duration-200"
                style={{ borderBottom: "0.5px solid var(--sep)", cursor: "default" }}
                onMouseEnter={e => (e.currentTarget.style.background = "rgba(30,64,175,0.04)")}
                onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
              >
                <div className="text-[12px] tabular-nums" style={{ color: "var(--t3)" }}>{a.time}</div>
                <div className="text-[13px] truncate" style={{ color: "var(--t2)" }}>{a.description || "—"}</div>
                <div className="flex items-center">
                  <span className="rounded-full px-2 py-0.5 text-[11px] font-semibold"
                    style={{ background: sev.bg, color: sev.color }}>
                    {sev.label}
                  </span>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
