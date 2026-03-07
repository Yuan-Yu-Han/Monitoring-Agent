"use client";

import type { LatestEvent } from "@/lib/api";

const SEV = {
  critical: { label: "严重", color: "var(--red)", bg: "var(--red-a)" },
  warning: { label: "警告", color: "var(--orange)", bg: "var(--orange-a)" },
  info: { label: "信息", color: "var(--t3)", bg: "var(--panel-2)" },
};

function toTime(ts: string): string {
  if (!ts) return "-";
  try {
    // If backend emits a naive ISO string (no timezone), treat it as UTC.
    const normalized = /Z$|[+-]\d{2}:\d{2}$/.test(ts) ? ts : `${ts}Z`;
    const d = new Date(normalized);
    if (Number.isNaN(d.getTime())) return ts;
    return d.toLocaleTimeString("zh-CN", { hour12: false, timeZone: "Asia/Shanghai" });
  } catch {
    return ts;
  }
}

export default function LatestEventCard({ event }: { event: LatestEvent | null }) {
  const sev = SEV[(event?.severity as keyof typeof SEV) ?? "info"] ?? SEV.info;
  const imageUrl = event?.image_path ? `/api/outputs/${event.image_path}` : "";
  const vlImageUrl = event?.vl_image_path ? `/api/outputs/${event.vl_image_path}` : "";

  return (
    <div className="panel panel-col h-full">
      <div className="panel-hd">
        <span className="panel-title">🧾 最近事件</span>
        {event?.severity && (
          <span className="ml-auto rounded-full px-2 py-0.5 text-[11px] font-semibold"
            style={{ background: sev.bg, color: sev.color }}>
            {sev.label}
          </span>
        )}
      </div>

      {!event ? (
        <div className="flex-1 min-h-0 flex items-center justify-center text-[11px]" style={{ color: "var(--t3)" }}>
          暂无事件
        </div>
      ) : (
        <div className="flex-1 min-h-0 p-3 pt-2 space-y-2">
          <div className="flex items-center gap-2 text-[11px]" style={{ color: "var(--t3)" }}>
            <span className="tabular-nums">{toTime(event.timestamp)}</span>
            <span className="opacity-60">·</span>
            <span className="font-mono">{event.event_id}</span>
            <span className="ml-auto tabular-nums" title="火情置信（来自事件confidence）">
              {(event.confidence * 100).toFixed(1)}%
            </span>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div className="relative rounded-lg overflow-hidden" style={{ border: "0.5px solid var(--border)", background: "#000" }}>
              {imageUrl ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={imageUrl} alt="event" className="h-32 w-full object-contain" />
              ) : (
                <div className="h-32 flex items-center justify-center text-[11px]" style={{ color: "var(--t3)" }}>
                  无原始图
                </div>
              )}
              <div className="absolute left-1.5 top-1.5 rounded px-1.5 py-0.5 text-[10px]"
                style={{ background: "rgba(0,0,0,0.55)", color: "rgba(255,255,255,0.85)" }}>
                原图
              </div>
            </div>

            <div className="relative rounded-lg overflow-hidden" style={{ border: "0.5px solid var(--border)", background: "#000" }}>
              {vlImageUrl ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={vlImageUrl} alt="vl" className="h-32 w-full object-contain" />
              ) : (
                <div className="h-32 flex items-center justify-center text-[11px]" style={{ color: "var(--t3)" }}>
                  暂无标注图
                </div>
              )}
              <div className="absolute left-1.5 top-1.5 rounded px-1.5 py-0.5 text-[10px]"
                style={{ background: "rgba(0,0,0,0.55)", color: "rgba(255,255,255,0.85)" }}>
                VL标注
              </div>
            </div>
          </div>

          {event.summary && (
            <div className="text-[12px] leading-snug line-clamp-3" style={{ color: "var(--t2)" }}>
              {event.summary}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
