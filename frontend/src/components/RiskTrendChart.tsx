"use client";

import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Area, AreaChart,
} from "recharts";
import type { RiskPoint } from "@/lib/api";

const Tip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-xl px-3 py-2 text-[12px]"
      style={{
        background: "rgba(255,255,255,0.97)",
        border: "0.5px solid rgba(0,0,0,0.08)",
        backdropFilter: "blur(20px)",
        boxShadow: "0 4px 24px rgba(0,0,0,0.10)",
      }}>
      <div className="mb-1.5 font-medium" style={{ color: "var(--t3)" }}>{label}</div>
      {payload.map((p: any) => (
        <div key={p.dataKey} className="flex items-center gap-2 mb-0.5">
          <span className="h-1.5 w-1.5 rounded-full flex-shrink-0" style={{ background: p.color }} />
          <span style={{ color: "var(--t2)" }}>{p.name}</span>
          <span className="ml-auto pl-3 font-semibold tabular-nums" style={{ color: p.color }}>
            {p.value}%
          </span>
        </div>
      ))}
    </div>
  );
};

export default function RiskTrendChart({ data }: { data: RiskPoint[] }) {
  return (
    <div className="panel panel-col h-full">
      <div className="panel-hd">
        <span className="panel-title">📈 风险趋势</span>
        <span className="ml-auto text-[12px]" style={{ color: "var(--t3)" }}>近 24h</span>
      </div>
      <div className="flex-1 min-h-0 p-3 pt-4">
        {data.length === 0 ? (
          <div className="flex h-full items-center justify-center text-[14px]" style={{ color: "var(--t3)" }}>
            暂无数据
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 2, right: 4, left: -24, bottom: 0 }}>
              <defs>
                <linearGradient id="gRisk" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#FF3B30" stopOpacity={0.25} />
                  <stop offset="95%" stopColor="#FF3B30" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="gFire" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#FF9500" stopOpacity={0.2} />
                  <stop offset="95%" stopColor="#FF9500" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(30,64,175,0.07)" vertical={false} />
              <XAxis dataKey="time"
                tick={{ fontSize: 11, fill: "rgba(60,60,67,0.50)", fontFamily: "SF Mono, ui-monospace, Menlo, monospace" }}
                axisLine={false} tickLine={false} />
              <YAxis domain={[0, 100]}
                tick={{ fontSize: 11, fill: "rgba(60,60,67,0.50)", fontFamily: "SF Mono, ui-monospace, Menlo, monospace" }}
                axisLine={false} tickLine={false} />
              <Tooltip content={<Tip />} />
              <Area type="monotone" dataKey="risk" name="综合风险" stroke="#FF3B30"
                fill="url(#gRisk)" strokeWidth={1.5} dot={false} activeDot={{ r: 3, strokeWidth: 0 }} />
              <Area type="monotone" dataKey="fire" name="火灾概率" stroke="#FF9500"
                fill="url(#gFire)" strokeWidth={1.5} dot={false} activeDot={{ r: 3, strokeWidth: 0 }} />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
