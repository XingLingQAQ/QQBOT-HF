import { useCallback, useEffect, useState } from "react";
import Card from "../components/Card.jsx";
import api from "../api";
import { loginState, procState, qqAvatar } from "../format";

const PROCS = [
  { key: "lagrange", label: "Lagrange.OneBot" },
  { key: "nonebot", label: "NoneBot" },
  { key: "backend", label: "后端服务" },
];

export default function Overview() {
  const [status, setStatus] = useState({});
  const [login, setLogin] = useState({ status: "offline", qq: "", nickname: "" });
  const [systemConfig, setSystemConfig] = useState(null);
  const [updateBusy, setUpdateBusy] = useState("");
  const [updateMsg, setUpdateMsg] = useState("");

  const tick = useCallback(async () => {
    try {
      const [s, l, c] = await Promise.all([
        api.get("/status"),
        api.get("/login-status"),
        api.get("/system/config"),
      ]);
      setStatus(s.data);
      setLogin(l.data);
      setSystemConfig(c.data);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    tick();
    const id = setInterval(tick, 3000);
    return () => clearInterval(id);
  }, [tick]);

  const badge = loginState(login.status);
  const online = login.status === "online";
  const avatar = online ? qqAvatar(login.qq) : "";

  const runMaintenance = async (kind) => {
    const map = {
      repair: {
        label: "修复 Lagrange 配置",
        url: "/system/repair-lagrange-config",
        confirm: "将修复 Lagrange 反向 WS 与签名服务配置并重启 Lagrange，继续？",
      },
      lagrange: {
        label: "更新 Lagrange",
        url: "/system/update-lagrange",
        confirm: "将从官方 nightly 下载并替换容器内 Lagrange.OneBot，然后重启，继续？",
      },
      deps: {
        label: "更新 NoneBot/依赖",
        url: "/system/update-python-deps",
        confirm: "将升级 /data/venv 内的 FastAPI、NoneBot2 与 OneBot 适配器并重启服务，继续？",
      },
    };
    const item = map[kind];
    if (!item || !window.confirm(item.confirm)) return;
    setUpdateBusy(kind);
    setUpdateMsg("");
    try {
      await api.post(item.url, {});
      setUpdateMsg(`${item.label}已完成。`);
      await tick();
    } catch (e) {
      setUpdateMsg(e?.response?.data?.detail || `${item.label}失败`);
    } finally {
      setUpdateBusy("");
    }
  };

  return (
    <div className="page">
      <h2 className="page-title">总览</h2>

      <div className={`hero ${online ? "online" : ""}`}>
        <div className="hero-avatar">
          {avatar ? (
            <img src={avatar} alt="头像" onError={(e) => (e.currentTarget.style.display = "none")} />
          ) : (
            <span className="hero-avatar-fallback">QQ</span>
          )}
        </div>
        <div className="hero-info">
          <div className="hero-line">
            <span className="hero-name">{login.nickname || (online ? "已登录" : "未登录")}</span>
            <span className={`badge ${badge.tone}`}>{badge.text}</span>
          </div>
          <div className="hero-sub">{login.qq ? `QQ ${login.qq}` : "请前往「扫码登录」绑定账号"}</div>
        </div>
        <button className="btn" onClick={tick}>刷新</button>
      </div>

      <div className="grid">
        <Card title="进程状态">
          {PROCS.map(({ key, label }) => {
            const s = procState(status[key]);
            return (
              <div className="kv" key={key}>
                <span>{label}</span>
                <span className="state-pill">
                  <span className={`light ${s.tone}`} />
                  {s.text}
                </span>
              </div>
            );
          })}
        </Card>

        <Card title="容器内组件更新">
          <div className="kv">
            <span>签名服务</span>
            <code className="inline-code">{systemConfig?.lagrangeSignServerUrl || "—"}</code>
          </div>
          <div className="kv">
            <span>NoneBot 适配器</span>
            <span>{systemConfig?.nonebotAdapter || "—"}</span>
          </div>
          <div className="maintenance-actions">
            <button className="btn" disabled={!!updateBusy} onClick={() => runMaintenance("repair")}>
              {updateBusy === "repair" ? "处理中…" : "修复 Lagrange 配置"}
            </button>
            <button className="btn" disabled={!!updateBusy} onClick={() => runMaintenance("lagrange")}>
              {updateBusy === "lagrange" ? "更新中…" : "更新 Lagrange"}
            </button>
            <button className="btn" disabled={!!updateBusy} onClick={() => runMaintenance("deps")}>
              {updateBusy === "deps" ? "更新中…" : "更新 NoneBot/依赖"}
            </button>
          </div>
          <p className="hint-line">
            更新操作只影响容器内持久化环境：Lagrange 二进制位于 /opt/lagrange，NoneBot 与适配器位于 /data/venv。
          </p>
          {updateMsg && <p className="hint-line info">{updateMsg}</p>}
        </Card>

        <Card title="登录信息">
          <div className="kv">
            <span>状态</span>
            <span className={`badge ${badge.tone}`}>{badge.text}</span>
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
