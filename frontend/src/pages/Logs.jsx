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

// "2026-06-04_142601.log.gz" -> "2026-06-04 14:26:01"
function archiveLabel(fname) {
  const m = /^(\d{4}-\d{2}-\d{2})_(\d{2})(\d{2})(\d{2})/.exec(fname);
  if (!m) return fname;
  return `${m[1]} ${m[2]}:${m[3]}:${m[4]}`;
}

export default function Logs() {
  const [logs, setLogs] = useState([]);
  const [active, setActive] = useState("");
  const [archives, setArchives] = useState([]);
  const [view, setView] = useState("live"); // "live" | archive filename
  const [meta, setMeta] = useState(null);
  const [content, setContent] = useState("");
  const [live, setLive] = useState(true);
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(false);
  const [nonce, setNonce] = useState(0); // bump to force a live reconnect
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

  const loadArchives = useCallback(async (name) => {
    if (!name) return;
    try {
      const { data } = await api.get(`/logs/${name}/archives`);
      setArchives(data.archives || []);
    } catch {
      setArchives([]);
    }
  }, []);

  useEffect(() => {
    loadList();
  }, [loadList]);

  // Reset to the live view and (re)load the archive list when switching logs.
  useEffect(() => {
    setView("live");
    setContent("");
    setMeta(null);
    loadArchives(active);
  }, [active, loadArchives]);

  // Live SSE stream — only while viewing "live" (and not paused). The server
  // sends a `meta` frame + current tail, then only appended bytes (tail -f); we
  // append incrementally instead of re-pulling the whole tail on a timer.
  useEffect(() => {
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
    if (!active || view !== "live" || !live) {
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
      loadArchives(active); // a rotation likely produced a new archive
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
  }, [active, view, live, nonce, loadArchives]);

  // Static fetch when viewing an archived run.
  useEffect(() => {
    if (!active || view === "live") return;
    let cancelled = false;
    setLoading(true);
    setContent("");
    api
      .get(`/logs/${active}/archive/${encodeURIComponent(view)}`)
      .then(({ data }) => {
        if (cancelled) return;
        setMeta(data);
        setContent(data.content || "");
      })
      .catch((e) => {
        if (cancelled) return;
        setContent(`加载失败：${e?.response?.data?.detail || e.message}`);
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [active, view]);

  // Keep the view pinned to the newest log line as content streams/loads in.
  useEffect(() => {
    if (preRef.current) preRef.current.scrollTop = preRef.current.scrollHeight;
  }, [content]);

  const isLive = view === "live";
  const downloadHref = isLive
    ? `/api/logs/${active}/download`
    : `/api/logs/${active}/archive/${encodeURIComponent(view)}/download`;

  return (
    <div className="page">
      <h2 className="page-title">日志</h2>
      <p className="hint-line muted">
        每次进程启动写入新的 <code>latest.log</code>，上次运行自动归档（保留最近 20 份）。当前日志实时流式跟随，历史归档可在右侧选择查看/下载。
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
            {l.archives > 0 && <span className="badge">{l.archives}</span>}
          </button>
        ))}
      </div>

      <Card
        title={meta?.label || "日志"}
        extra={
          <div className="log-toolbar">
            <select
              className="select"
              value={view}
              onChange={(e) => setView(e.target.value)}
              title="选择当前日志或历史归档"
            >
              <option value="live">当前（实时）</option>
              {archives.map((a) => (
                <option key={a.file} value={a.file}>
                  {archiveLabel(a.file)} · {formatSize(a.size)}
                </option>
              ))}
            </select>
            {isLive ? (
              <>
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
              </>
            ) : (
              <span className="badge yellow">{loading ? "加载中…" : "历史归档"}</span>
            )}
            <a className="btn" href={downloadHref}>
              下载
            </a>
          </div>
        }
      >
        <div className="log-meta">
          {meta?.exists ? (
            <>
              <span>{isLive ? "起始大小" : "大小"}：{formatSize(meta.size)}</span>
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
