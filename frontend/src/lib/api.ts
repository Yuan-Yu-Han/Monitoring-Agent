const BASE = "/api";

export interface DashboardStatus {
  riskLevel: "low" | "medium" | "high";
  fireProbability: number;
  personCount: number;
  targetCount?: number;
  monitorState?: string;
  detectionStreak?: number;
  noDetectionStreak?: number;
  lastFilteredCount?: number;
  lastAlarmTime: string;
  unresolvedAlarms: number;
  stream: {
    is_running: boolean;
    frames_sent: number;
    clients_connected: number;
    uptime_seconds: number | null;
    rtsp_url: string;
    last_error: string | null;
  };
}

export interface Alarm {
  id: string;
  time: string;
  type: string;
  severity: "critical" | "warning" | "info";
  location: string;
  description: string;
  status: "processing" | "resolved";
}

export interface RiskPoint {
  time: string;
  risk: number;
  fire: number;
  person: number;
  target?: number;
}

export interface LatestEvent {
  event_id: string;
  timestamp: string;
  state: string;
  severity: string;
  confidence: number;
  detection_count: number;
  labels: string[];
  summary: string;
  image_path: string;
  vl_image_path: string;
}

export async function fetchStatus(): Promise<DashboardStatus> {
  const res = await fetch(`${BASE}/dashboard/status`, { cache: "no-store" });
  if (!res.ok) throw new Error("status fetch failed");
  return res.json();
}

export async function fetchAlarms(): Promise<{ items: Alarm[] }> {
  const res = await fetch(`${BASE}/dashboard/alarms`, { cache: "no-store" });
  if (!res.ok) throw new Error("alarms fetch failed");
  return res.json();
}

export async function fetchRiskTrend(): Promise<{ items: RiskPoint[] }> {
  const res = await fetch(`${BASE}/dashboard/risk-trend`, { cache: "no-store" });
  if (!res.ok) throw new Error("risk-trend fetch failed");
  return res.json();
}

export async function fetchLatestEvent(): Promise<{ ok: boolean; event: LatestEvent | null }> {
  const res = await fetch(`${BASE}/dashboard/latest-event`, { cache: "no-store" });
  if (!res.ok) throw new Error("latest-event fetch failed");
  return res.json();
}

export async function sendChat(
  query: string,
  _opts?: { enableMemory?: boolean },
): Promise<{ ok: boolean; message: string; severity: string }> {
  const res = await fetch(`${BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query,
    }),
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail ?? body.error ?? detail;
    } catch { /* ignore */ }
    throw new Error(detail);
  }
  return res.json();
}

export async function streamStart(): Promise<void> {
  await fetch(`${BASE}/stream/start`, { method: "POST" });
}

export async function streamStop(): Promise<void> {
  await fetch(`${BASE}/stream/stop`, { method: "POST" });
}
