"use client";

import { useEffect, useRef, useState } from "react";
import { io, Socket } from "socket.io-client";

const STREAM_URL = process.env.NEXT_PUBLIC_STREAM_URL ?? "http://127.0.0.1:5002";

type ConnState = "connecting" | "live" | "disconnected" | "error";

export default function VideoStream() {
  const [frame, setFrame] = useState<string | null>(null);
  const [state, setState] = useState<ConnState>("connecting");
  const [fps, setFps] = useState(0);
  const fpsRef = useRef({ count: 0, last: Date.now() });
  const socketRef = useRef<Socket | null>(null);

  useEffect(() => {
    const socket = io(STREAM_URL, {
      // Allow polling fallback. The bundled Flask-SocketIO server may not support pure WebSocket
      // when running with the default Werkzeug/threading stack.
      transports: ["websocket", "polling"],
      reconnection: true,
      reconnectionAttempts: Infinity,
      reconnectionDelay: 2000,
      reconnectionDelayMax: 10000,
    });
    socketRef.current = socket;
    socket.on("connect",       () => setState("live"));
    socket.on("disconnect",    () => { setState("disconnected"); setFrame(null); });
    socket.on("connect_error", () => setState("error"));
    socket.on("frame", (data: { image: string }) => {
      setFrame(data.image);
      fpsRef.current.count++;
      const now = Date.now();
      if (now - fpsRef.current.last >= 1000) {
        setFps(fpsRef.current.count);
        fpsRef.current.count = 0;
        fpsRef.current.last = now;
      }
    });
    return () => { socket.disconnect(); };
  }, []);

  const stateConfig = {
    connecting:   { dot: "var(--orange)", label: "连接中" },
    live:         { dot: "var(--green)",  label: `${fps} fps` },
    disconnected: { dot: "var(--t3)",     label: "已断开" },
    error:        { dot: "var(--red)",    label: "连接失败" },
  }[state];

  return (
    <div className="panel panel-col h-full">
      <div className="panel-hd">
        <span className="panel-title">📹 实时监控</span>
        {/* Status */}
        <div className="ml-auto flex items-center gap-1.5 text-[10px]" style={{ color: "var(--t2)" }}>
          <span className={`h-1.5 w-1.5 rounded-full inline-block ${state === "live" || state === "connecting" ? "live-dot" : ""}`}
            style={{ background: stateConfig.dot }} />
          <span style={{ color: state === "live" ? "var(--green)" : "var(--t3)" }}>
            {stateConfig.label}
          </span>
        </div>
      </div>

      <div className="relative flex-1 min-h-0" style={{ background: "#000" }}>
        {frame ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={frame} alt="stream" className="h-full w-full object-contain" />
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-2">
            <span style={{ fontSize: 28, lineHeight: 1, opacity: 0.4 }}>
              {state === "connecting" ? "📡" : "🔌"}
            </span>
            <span className="text-[11px]" style={{ color: "var(--t3)" }}>
              {state === "connecting" ? "正在连接视频流..." : "视频流未就绪"}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
