import { useEffect, useState } from "react";
import Card from "../components/Card.jsx";
import api from "../api";

const STATUS_LABELS = {
  online: { text: "在线", cls: "badge green" },
  offline: { text: "离线", cls: "badge red" },
  waiting_scan: { text: "等待扫码", cls: "badge yellow" },
  scanned: { text: "已扫码", cls: "badge yellow" },
  expired: { text: "二维码已过期", cls: "badge red" },
};

export default function Overview() {
  const [status, setStatus] = useState({});
  const [login, setLogin] = useState({ status: "offline", qq: "", nickname: "" });

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const [s, l] = await Promise.all([
          api.get("/status"),
          api.get("/login-status"),
        ]);
        if (!alive) return;
        setStatus(s.data);
        setLogin(l.data);
      } catch {
        /* ignore */
      }
    };
    tick();
    const id = setInterval(tick, 3000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  const badge = STATUS_LABELS[login.status] || STATUS_LABELS.offline;

  return (
    <div className="page">
      <h2 className="page-title">总览</h2>
      <div className="grid">
        <Card title="登录状态">
          <div className="kv">
            <span>状态</span>
            <span className={badge.cls}>{badge.text}</span>
          </div>
          <div className="kv">
            <span>QQ 号</span>
            <span>{login.qq || "—"}</span>
          </div>
          <div className="kv">
            <span>昵称</span>
            <span>{login.nickname || "—"}</span>
          </div>
        </Card>

        <Card title="进程状态">
          <div className="kv">
            <span>Lagrange.OneBot</span>
            <span>{status.lagrange || "?"}</span>
          </div>
          <div className="kv">
            <span>NoneBot</span>
            <span>{status.nonebot || "?"}</span>
          </div>
          <div className="kv">
            <span>后端服务</span>
            <span>{status.backend || "?"}</span>
          </div>
        </Card>
      </div>

      <Card title="保活提示" className="hint-card">
        <p>
          本面板部署在 Hugging Face 免费 Docker Space 上，若连续 48 小时无外部请求会自动休眠。
        </p>
        <p>
          建议使用<strong>外部分钟级别的可用性监控服务</strong>（如 UptimeRobot）定时访问本面板地址以保持唤醒。
          请勿在容器内实现违规的自我保活机制。
        </p>
      </Card>
    </div>
  );
}
