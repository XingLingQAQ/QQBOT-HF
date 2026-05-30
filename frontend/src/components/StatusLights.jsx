import { useEffect, useState } from "react";
import api from "../api";
import { procState } from "../format";

const ROWS = [
  { key: "lagrange", label: "Lagrange" },
  { key: "nonebot", label: "NoneBot" },
  { key: "backend", label: "后端" },
];

export default function StatusLights() {
  const [status, setStatus] = useState({});

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const { data } = await api.get("/status");
        if (alive) setStatus(data);
      } catch {
        /* ignore transient errors */
      }
    };
    tick();
    const id = setInterval(tick, 3000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  return (
    <div className="status-lights">
      {ROWS.map(({ key, label }) => {
        const s = procState(status[key]);
        return (
          <div className="status-row" key={key} title={status[key] || "未知"}>
            <span className={`light ${s.tone}`} />
            <span>{label}</span>
            <span className="status-text">{s.text}</span>
          </div>
        );
      })}
    </div>
  );
}
