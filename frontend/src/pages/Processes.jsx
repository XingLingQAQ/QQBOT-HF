import { useCallback, useEffect, useState } from "react";
import Card from "../components/Card.jsx";
import api from "../api";
import { procState, protocolLabel } from "../format";
import { useConfirm, useToast } from "../ui.jsx";

const ACTIONS = [
  { key: "start", label: "启动", cls: "btn" },
  { key: "restart", label: "重启", cls: "btn primary" },
  { key: "stop", label: "停止", cls: "btn danger" },
];

export default function Processes() {
  const [procs, setProcs] = useState([]);
  const [protocol, setProtocol] = useState("");
  const [busy, setBusy] = useState("");
  const confirm = useConfirm();
  const toast = useToast();

  const load = useCallback(async () => {
    try {
      const { data } = await api.get("/processes");
      setProcs(data.processes || []);
      setProtocol(data.protocol || "");
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 3000);
    return () => clearInterval(id);
  }, [load]);

  const act = async (program, action, label) => {
    const verb = { start: "启动", stop: "停止", restart: "重启" }[action];
    const ok = await confirm({
      title: `${verb}进程`,
      message: `确认${verb}「${label}」进程？`,
      confirmText: verb,
      danger: action === "stop",
    });
    if (!ok) return;
    setBusy(`${program}:${action}`);
    try {
      const { data } = await api.post("/processes/action", { program, action });
      if (data.ok) {
        toast.success(`「${label}」${verb}成功，当前状态：${procState(data.status).text}`);
      } else {
        toast.error(`「${label}」${verb}失败：${data.log || "未知错误"}`);
      }
      await load();
    } catch (e) {
      toast.error(`「${label}」${verb}失败：${e?.response?.data?.detail || e.message}`);
    } finally {
      setBusy("");
    }
  };

  return (
    <div className="page">
      <h2 className="page-title">进程控制</h2>
      <p className="hint-line muted">
        当前协议：<strong>{protocolLabel(protocol)}</strong>
        。可手动启动 / 停止 / 重启各后端进程；后端面板服务自身不在此处控制以免锁死面板。
        切换协议请前往「总览」。
      </p>

      <Card title="进程列表" extra={<button className="btn" onClick={load}>刷新</button>}>
        <div className="proc-table">
          {procs.map(({ program, label, status }) => {
            const s = procState(status);
            return (
              <div className="proc-row" key={program}>
                <div className="proc-meta">
                  <span className="proc-name">{label}</span>
                  <span className="state-pill">
                    <span className={`light ${s.tone}`} />
                    {s.text}
                  </span>
                </div>
                <div className="proc-actions">
                  {ACTIONS.map((a) => (
                    <button
                      key={a.key}
                      className={a.cls}
                      disabled={!!busy}
                      onClick={() => act(program, a.key, label)}
                    >
                      {busy === `${program}:${a.key}` ? "处理中…" : a.label}
                    </button>
                  ))}
                </div>
              </div>
            );
          })}
          {procs.length === 0 && <p className="hint-line muted">暂无可控制的进程。</p>}
        </div>
      </Card>
    </div>
  );
}
