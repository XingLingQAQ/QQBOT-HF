import { useEffect, useState } from "react";
import api from "../api";

function lightClass(state) {
  if (state === "RUNNING") return "light green";
  if (state === "STARTING" || state === "STOPPING") return "light yellow";
  return "light red";
}

export default function StatusLights() {
  const [status, setStatus] = useState({ lagrange: "?", nonebot: "?" });

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
      <div className="status-row">
        <span className={lightClass(status.lagrange)} />
        <span>Lagrange</span>
        <span className="status-text">{status.lagrange}</span>
      </div>
      <div className="status-row">
        <span className={lightClass(status.nonebot)} />
        <span>NoneBot</span>
        <span className="status-text">{status.nonebot}</span>
      </div>
    </div>
  );
}
