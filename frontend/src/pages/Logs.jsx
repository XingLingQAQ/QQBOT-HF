import { useCallback, useEffect, useRef, useState } from "react";
import Card from "../components/Card.jsx";
import api from "../api";

// Keep at most this many characters in the live buffer so a long-running
// stream can't grow unbounded; oldest lines are dropped from the front.
const MAX_CHARS = 1_000_000;

function formatSize(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let n = bytes;
  let i = 0;
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024;
    i += 1;
  }
  return `${n.toFixed(n < 10 && i > 0 ? 1 : 0)} ${units[i]}`;
}

export default function Logs() {
  const [logs, setLogs] = useState([]);
  const [active, setActive] = useState("");
  const [meta, setMeta] = useState(null);
  const [content, setContent] = useState("");
  const [live, setLive] = useState(true);
  const [connected, setConnected] = useState(false);
  const [nonce, setNonce] = useState(0); // bump to force a reconnect
  const preRef = useRef(null);
  const esRef = useRef(null);

  const loadList = useCallback(async () => {
    try {
      const { data } = await api.get("/logs");
      setLogs(data.logs || []);
      setActive((cur) => cur || (data.logs && data.logs[0] && data.logs[0].name) || "");
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    loadList();
  }, [loadList]);

  // Open one SSE stream per (active log, live, nonce). The server sends a `meta`
  // frame + current tail, then only appended bytes (tail -f). We append
  // incrementally instead of re-pulling the whole tail on a timer.
  useEffect(() => {
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
    if (!active || !live) {
      setConnected(false);
      return undefined;
    }
    setContent("");
    const es = new EventSource(`/api/logs/${encodeURIComponent(active)}/stream`);
    esRef.current = es;

    const append = (chunk) =>
      setContent((prev) => {
        const next = prev + chunk;
        return next.length > MAX_CHARS ? next.slice(next.length - MAX_CHARS) : next;
      });

    es.addEventListener("meta", (e) => {
      try {
        setMeta(JSON.parse(e.data));
      } catch {
        /* ignore */
      }
      setContent("");
    });
    es.addEventListener("reset", (e) => {
      setContent("");
      try {
        const m = JSON.parse(e.data);
        setMeta((prev) => ({ ...(prev || {}), exists: m.exists }));
      } catch {
        /* ignore */
      }
    });
    es.onmessage = (e) => {
      setConnected(true);
      try {
        append(JSON.parse(e.data));
      } catch {
        /* ignore */
      }
    };
    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false); // EventSource auto-reconnects; meta resets the buffer

    return () => {
      es.close();
      if (esRef.current === es) esRef.current = null;
    };
  }, [active, live, nonce]);

  // Keep the view pinned to the newest log line as content streams in.
  useEffect(() => {
    if (preRef.current) preRef.current.scrollTop = preRef.current.scrollHeight;
  }, [content]);

  return (
    <div className="page">
      <h2 className="page-title">日志</h2>
      <p className="hint-line muted">
        实时流式跟随各后端进程日志（先显示尾部约 256&nbsp;KB，随后只增量推送新内容）。如需完整日志请点击「下载」。
      </p>

      <div className="log-tabs">
        {logs.map((l) => (
          <button
            key={l.name}
            className={`log-tab ${active === l.name ? "active" : ""}`}
            onClick={() => setActive(l.name)}
          >
            {l.label}
            {!l.exists && <span className="badge gray">无</span>}
          </button>
        ))}
      </div>

      <Card
        title={meta?.label || "日志"}
        extra={
          <div className="log-toolbar">
            <span className={`badge ${live && connected ? "green" : "gray"}`}>
              {live ? (connected ? "实时" : "连接中…") : "已暂停"}
            </span>
            <label className="checkbox-row inline">
              <input type="checkbox" checked={live} onChange={(e) => setLive(e.target.checked)} />
              <span>实时跟随</span>
            </label>
            <button className="btn" onClick={() => setNonce((n) => n + 1)} disabled={!live}>
              重连
            </button>
            <a className="btn" href={`/api/logs/${active}/download`}>
              下载
            </a>
          </div>
        }
      >
        <div className="log-meta">
          {meta?.exists ? (
            <>
              <span>起始大小：{formatSize(meta.size)}</span>
              {meta.truncated && <span className="badge yellow">已截断（仅尾部）</span>}
            </>
          ) : (
            <span className="hint-line muted">该日志文件尚不存在（对应进程可能未运行过）。</span>
          )}
        </div>
        <pre className="log-view" ref={preRef}>
          {content || (meta?.exists ? "（日志为空）" : "")}
        </pre>
      </Card>
    </div>
  );
}
