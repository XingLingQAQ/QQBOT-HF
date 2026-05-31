import { useCallback, useEffect, useState } from "react";
import api from "../api";
import Card from "./Card.jsx";
import { PROTOCOLS } from "../format";

// Lets the user pick the active QQ protocol backend. Selecting NapCat stops
// Lagrange + the sign server (and vice-versa); the choice is persisted server
// side. `onChanged` is called after a successful switch so parents can refresh.
export default function ProtocolSelector({ onChanged }) {
  const [protocol, setProtocol] = useState("");
  const [available, setAvailable] = useState(["lagrange", "napcat"]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const load = useCallback(async () => {
    try {
      const { data } = await api.get("/protocol");
      setProtocol(data.protocol);
      if (Array.isArray(data.available) && data.available.length) {
        setAvailable(data.available);
      }
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const select = async (next) => {
    if (busy || next === protocol) return;
    const label = (PROTOCOLS[next] && PROTOCOLS[next].label) || next;
    if (!window.confirm(`切换协议后端到「${label}」？\n将停止未选用的协议及其依赖进程，可能需要重新扫码登录。`)) {
      return;
    }
    setBusy(true);
    setMsg("正在切换并重启相关进程…");
    try {
      const { data } = await api.post("/protocol", { protocol: next });
      setProtocol(data.protocol);
      setMsg(`已切换到「${label}」`);
      if (onChanged) onChanged(data.protocol);
    } catch (e) {
      setMsg(`切换失败：${e?.response?.data?.detail || e.message}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title="协议后端">
      <div className="protocol-options">
        {available.map((key) => {
          const meta = PROTOCOLS[key] || { label: key, desc: "" };
          const active = key === protocol;
          return (
            <button
              key={key}
              type="button"
              className={`protocol-option ${active ? "active" : ""}`}
              onClick={() => select(key)}
              disabled={busy}
            >
              <div className="protocol-option-head">
                <span className="protocol-radio" />
                <span className="protocol-name">{meta.label}</span>
                {active && <span className="badge green">使用中</span>}
                {key === "napcat" && !active && <span className="badge gray">默认不启用</span>}
              </div>
              <div className="protocol-desc">{meta.desc}</div>
            </button>
          );
        })}
      </div>
      {msg && <p className="protocol-msg">{msg}</p>}
    </Card>
  );
}
