import { useEffect, useState } from "react";
import api from "../api";
import { procState } from "../format";

function rowsFor(protocol) {
  const common = [
    { key: "nonebot", label: "NoneBot" },
    { key: "backend", label: "后端" },
  ];
  if (protocol === "napcat") {
    return [{ key: "napcat", label: "NapCat" }, ...common];
  }
  return [
    { key: "lagrange", label: "Lagrange" },
    { key: "signserver", label: "签名服务" },
    ...common,
  ];
}

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
      {rowsFor(status.protocol).map(({ key, label }) => {
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
