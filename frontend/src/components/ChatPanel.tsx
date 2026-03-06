"use client";

import { useState, useRef, useEffect } from "react";
import { Send, Bot, User, Loader2, ChevronDown, ChevronRight, Wrench, Terminal } from "lucide-react";
import ReactMarkdown from "react-markdown";

interface StreamStep {
  type: "tool_call" | "tool_output";
  content?: string;
  names?: string[];
}

interface Message {
  role: "user" | "assistant";
  content: string;
  severity?: string;
  streaming?: boolean;
  steps?: StreamStep[];
  stepsOpen?: boolean;
}

type RetrievalTarget = "event" | "chat" | "knowledge";

const SEV_COLOR: Record<string, string> = {
  critical: "var(--red)",
  warning:  "var(--orange)",
};

function TogglePill({
  on,
  label,
  title,
  icon,
  onClick,
}: {
  on: boolean;
  label: string;
  title: string;
  icon: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      className="flex items-center gap-1 rounded-full px-2 py-1 text-[10px] font-semibold transition-colors"
      style={{
        background: on ? "var(--blue-a)" : "rgba(0,0,0,0.05)",
        color: on ? "var(--blue)" : "var(--t3)",
        border: "0.5px solid var(--border)",
      }}
    >
      {icon}
      <span>{label}</span>
    </button>
  );
}

function ToolSteps({ steps, open, onToggle, streaming }: {
  steps: StreamStep[];
  open: boolean;
  onToggle: () => void;
  streaming: boolean;
}) {
  if (steps.length === 0 && !streaming) return null;
  return (
    <div className="mb-1.5 overflow-hidden"
      style={{ borderRadius: "var(--radius-sm)", border: "0.5px solid var(--border)" }}>
      <button onClick={onToggle}
        className="flex w-full cursor-pointer items-center gap-1.5 px-3 py-1.5 text-[10px] transition-colors duration-150"
        style={{ background: "var(--panel-2)", color: "var(--t3)" }}
        onMouseEnter={e => (e.currentTarget.style.background = "var(--panel-hover)")}
        onMouseLeave={e => (e.currentTarget.style.background = "var(--panel-2)")}
      >
        {streaming
          ? <Loader2 size={9} className="animate-spin" style={{ color: "var(--orange)" }} />
          : open ? <ChevronDown size={9} /> : <ChevronRight size={9} />
        }
        <span>{streaming ? "工具执行中…" : `工具调用 · ${steps.length} 步`}</span>
      </button>
      {open && steps.length > 0 && (
        <div className="max-h-44 overflow-y-auto p-2 space-y-1"
          style={{ background: "rgba(0,0,0,0.04)" }}>
          {steps.map((s, i) => (
            <div key={i} className="flex gap-1.5 text-[10px] leading-relaxed">
              {s.type === "tool_call"
                ? <Wrench size={9} className="flex-shrink-0 mt-0.5" style={{ color: "var(--orange)" }} />
                : <Terminal size={9} className="flex-shrink-0 mt-0.5" style={{ color: "var(--t3)" }} />
              }
              {s.type === "tool_call" ? (
                <span className="font-mono font-semibold" style={{ color: "var(--orange)" }}>
                  {s.names?.join(", ")}
                </span>
              ) : (
                <span className="whitespace-pre-wrap font-mono break-all" style={{ color: "var(--t3)" }}>
                  {s.content}
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const mdComponents = {
  p:          ({ children }: any) => <p className="mb-1 last:mb-0">{children}</p>,
  h1:         ({ children }: any) => <h1 className="text-[13px] font-semibold mb-1">{children}</h1>,
  h2:         ({ children }: any) => <h2 className="text-[12px] font-semibold mb-1">{children}</h2>,
  h3:         ({ children }: any) => <h3 className="text-[11px] font-medium mb-0.5">{children}</h3>,
  ul:         ({ children }: any) => <ul className="list-disc pl-4 mb-1 space-y-0.5">{children}</ul>,
  ol:         ({ children }: any) => <ol className="list-decimal pl-4 mb-1 space-y-0.5">{children}</ol>,
  li:         ({ children }: any) => <li>{children}</li>,
  strong:     ({ children }: any) => <strong className="font-semibold" style={{ color: "var(--t1)" }}>{children}</strong>,
  blockquote: ({ children }: any) => (
    <blockquote className="border-l-2 pl-2 my-1" style={{ borderColor: "var(--blue)", color: "var(--t2)" }}>
      {children}
    </blockquote>
  ),
  code: ({ inline, children }: any) =>
    inline
      ? <code className="rounded px-1 text-[11px] font-mono"
          style={{ background: "rgba(0,0,0,0.06)", color: "var(--teal)" }}>{children}</code>
      : <pre className="rounded-lg p-2.5 my-1 overflow-x-auto text-[11px] font-mono"
          style={{ background: "rgba(0,0,0,0.04)", color: "var(--teal)", border: "0.5px solid var(--border)" }}>
          <code>{children}</code>
        </pre>,
};

export default function ChatPanel() {
  const [messages, setMessages] = useState<Message[]>([{
    role: "assistant",
    content: "您好，我是 FireGuard AI 助手。可以帮您分析监控事件、查询历史告警、评估火灾风险。",
  }]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [enableMemory, setEnableMemory] = useState(false);
  const [enableCaseRetrieval, setEnableCaseRetrieval] = useState(false);
  const [enableKnowledgeRetrieval, setEnableKnowledgeRetrieval] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const toggleSteps = (idx: number) =>
    setMessages(p => p.map((m, i) => i === idx ? { ...m, stepsOpen: !m.stepsOpen } : m));

  const send = async () => {
    const q = input.trim();
    if (!q || loading) return;
    setInput("");
    setMessages(p => [...p, { role: "user", content: q }]);
    setLoading(true);
    setMessages(p => [...p, { role: "assistant", content: "", streaming: true, steps: [], stepsOpen: true }]);

    try {
      const retrievalTargets: RetrievalTarget[] = [
        ...(enableCaseRetrieval ? (["event", "chat"] as const) : []),
        ...(enableKnowledgeRetrieval ? (["knowledge"] as const) : []),
      ];
      const res = await fetch("/api/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: q,
          enable_memory: enableMemory,
          retrieval_targets: retrievalTargets,
        }),
      });
      if (!res.ok || !res.body) {
        let d = `HTTP ${res.status}`;
        try { const b = await res.json(); d = b.detail ?? b.error ?? d; } catch {}
        throw new Error(d);
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const data = JSON.parse(line.slice(6));
            if (data.type === "token") {
              setMessages(p => p.map((m, i) =>
                i === p.length - 1 ? { ...m, content: (m.content || "") + data.content } : m));
            } else if (data.type === "done") {
              setMessages(p => p.map((m, i) =>
                i === p.length - 1
                  ? { ...m, content: data.message || m.content || "（无回复）", severity: data.severity, streaming: false, stepsOpen: false }
                  : m));
            } else if (data.type === "error") {
              setMessages(p => p.map((m, i) =>
                i === p.length - 1
                  ? { ...m, content: `请求失败：${data.message}`, severity: "critical", streaming: false, stepsOpen: false }
                  : m));
            } else if (data.type === "tool_call" || data.type === "tool_output") {
              setMessages(p => p.map((m, i) =>
                i === p.length - 1 ? { ...m, steps: [...(m.steps ?? []), data as StreamStep] } : m));
            }
          } catch {}
        }
      }
    } catch (err: unknown) {
      const d = err instanceof Error ? err.message : String(err);
      setMessages(p => p.map((m, i) =>
        i === p.length - 1
          ? { ...m, content: `请求失败：${d}`, severity: "critical", streaming: false, stepsOpen: false }
          : m));
    } finally {
      setLoading(false);
    }
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  };

  return (
    <div className="panel panel-col h-full">
      <div className="panel-hd">
        <span className="panel-title">🤖 AI 助手</span>
        <div className="ml-2 flex items-center gap-1.5">
          <TogglePill
            on={enableMemory}
            label="上下文"
            title="拼接本次会话的对话上下文"
            icon="💬"
            onClick={() => setEnableMemory(v => !v)}
          />
          <TogglePill
            on={enableCaseRetrieval}
            label="记忆"
            title="检索历史事件/对话案例（case memory / vector memory）"
            icon="🗃️"
            onClick={() => setEnableCaseRetrieval(v => !v)}
          />
          <TogglePill
            on={enableKnowledgeRetrieval}
            label="知识库"
            title="检索知识库片段（RAG）"
            icon="📚"
            onClick={() => setEnableKnowledgeRetrieval(v => !v)}
          />
        </div>
        <span className="ml-auto rounded-full px-2 py-0.5 text-[9.5px] font-semibold"
          style={{ background: "var(--green-a)", color: "var(--green)" }}>在线</span>
      </div>

      {/* Messages */}
      <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-4">
        {messages.map((m, i) => {
          const isUser = m.role === "user";
          const accentColor = m.severity ? SEV_COLOR[m.severity] : undefined;
          return (
            <div key={i} className={`flex gap-2 ${isUser ? "flex-row-reverse" : ""}`}>
              {/* Avatar */}
              <div className="mt-0.5 h-6 w-6 flex-shrink-0 flex items-center justify-center rounded-full"
                style={{
                  background: isUser ? "var(--blue-a)" : "rgba(242,242,247,0.9)",
                  border: "0.5px solid var(--border)",
                }}>
                {isUser
                  ? <User size={11} style={{ color: "var(--blue)" }} />
                  : <Bot  size={11} style={{ color: "var(--t2)" }} />
                }
              </div>

              <div className="max-w-[88%] min-w-0">
                {/* Tool steps — only show when tools have actually been called */}
                {!isUser && m.steps && m.steps.length > 0 && (
                  <ToolSteps steps={m.steps} open={m.stepsOpen ?? false}
                    onToggle={() => toggleSteps(i)} streaming={m.streaming ?? false} />
                )}

                {/* Bubble */}
                {(m.content || m.streaming) && (
                  <div className="rounded-2xl px-3.5 py-2.5 text-[13px] leading-relaxed"
                    style={isUser
                      ? { background: "var(--blue)", color: "#fff", borderBottomRightRadius: 6 }
                      : {
                          background: "var(--panel-2)",
                          color: "var(--t1)",
                          border: "0.5px solid var(--border)",
                          borderBottomLeftRadius: 6,
                          borderLeft: accentColor ? `2px solid ${accentColor}` : undefined,
                        }
                    }
                  >
                    {m.streaming && !m.content ? (
                      <span className="flex items-center gap-1" style={{ color: "var(--t3)" }}>
                        <span className="inline-block w-1 h-1 rounded-full animate-pulse" style={{ background: "var(--t3)" }} />
                        <span className="inline-block w-1 h-1 rounded-full animate-pulse" style={{ background: "var(--t3)", animationDelay: "0.2s" }} />
                        <span className="inline-block w-1 h-1 rounded-full animate-pulse" style={{ background: "var(--t3)", animationDelay: "0.4s" }} />
                      </span>
                    ) : isUser ? (
                      m.content
                    ) : (
                      <ReactMarkdown components={mdComponents}>{m.content}</ReactMarkdown>
                    )}
                    {/* Streaming cursor */}
                    {m.streaming && m.content && (
                      <span className="inline-block w-0.5 h-3 ml-0.5 animate-pulse rounded-full align-middle"
                        style={{ background: "var(--t2)" }} />
                    )}
                  </div>
                )}
              </div>
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="flex-shrink-0 flex items-end gap-3 p-3"
        style={{ borderTop: "0.5px solid var(--sep)" }}>
        <textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={onKey}
          placeholder="发送消息…"
          rows={2}
          className="flex-1 resize-none rounded-xl px-3 py-2.5 text-[14px] outline-none transition-colors duration-150"
          style={{
            background: "var(--panel-2)",
            border: "0.5px solid var(--border)",
            color: "var(--t1)",
          }}
          onFocus={e => (e.target.style.borderColor = "rgba(10,132,255,0.5)")}
          onBlur={e => (e.target.style.borderColor = "var(--border)")}
        />
        <button onClick={send} disabled={!input.trim() || loading} aria-label="发送"
          className="flex h-8 w-8 flex-shrink-0 cursor-pointer items-center justify-center rounded-full transition-opacity duration-150 disabled:opacity-30"
          style={{ background: "var(--blue)" }}>
          <Send size={13} className="text-white" />
        </button>
      </div>
    </div>
  );
}
