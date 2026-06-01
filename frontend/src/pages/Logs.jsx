import { useCallback, useEffect, useRef, useState } from "react";
import Card from "../components/Card.jsx";
import api from "../api";

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
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(false);
  const [auto, setAuto] = useState(true);
  const preRef = useRef(null);

  const loadList = useCallback(async () => {
    try {
      const { data } = await api.get("/logs");
      setLogs(data.logs || []);
      setActive((cur) => cur || (data.logs && data.logs[0] && data.logs[0].name) || "");
    } catch {
      /* ignore */
    }
  }, []);

  const loadDetail = useCallback(async (name) => {
    if (!name) return;
    setLoading(true);
    try {
      const { data } = await api.get(`/logs/${name}`);
      setDetail(data);
    } catch (e) {
      setDetail({ name, content: `加载失败：${e?.response?.data?.detail || e.message}`, exists: false });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadList();
  }, [loadList]);

  useEffect(() => {
    loadDetail(active);
  }, [active, loadDetail]);

  useEffect(() => {
    if (!auto) return undefined;
    const id = setInterval(() => loadDetail(active), 3000);
    return () => clearInterval(id);
  }, [auto, active, loadDetail]);

  // Keep the view pinned to the newest log line after each refresh.
  useEffect(() => {
    if (preRef.current) preRef.current.scrollTop = preRef.current.scrollHeight;
  }, [detail]);

  return (
    <div className="page">
      <h2 className="page-title">日志</h2>
      <p className="hint-line muted">
        查看各后端进程的运行日志（仅显示文件尾部，最多约 256&nbsp;KB）。如需完整日志请点击「下载」。
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
        title={detail?.label || "日志"}
        extra={
          <div className="log-toolbar">
            <label className="checkbox-row inline">
              <input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} />
              <span>自动刷新</span>
            </label>
            <button className="btn" onClick={() => loadDetail(active)} disabled={loading}>
              {loading ? "刷新中…" : "刷新"}
            </button>
            <a className="btn" href={`/api/logs/${active}/download`}>
              下载
            </a>
          </div>
        }
      >
        <div className="log-meta">
          {detail?.exists ? (
            <>
              <span>大小：{formatSize(detail.size)}</span>
              {detail.truncated && <span className="badge yellow">已截断（仅尾部）</span>}
            </>
          ) : (
            <span className="hint-line muted">该日志文件尚不存在（对应进程可能未运行过）。</span>
          )}
        </div>
        <pre className="log-view" ref={preRef}>
          {detail?.content || (detail?.exists ? "（日志为空）" : "")}
        </pre>
      </Card>
    </div>
  );
}
