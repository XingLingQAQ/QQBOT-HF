import { useCallback, useEffect, useState } from "react";
import Card from "../components/Card.jsx";
import api from "../api";
import { protocolLabel } from "../format";

// NapCat ships its own WebUI (login QR, network config, logs, terminal, ...).
// It listens on loopback inside the container and is reverse-proxied by the
// backend at /napcat/* on the single public port, so it works on a HF Space.
export default function NapcatWebUI() {
  const [info, setInfo] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const { data } = await api.get("/napcat/webui-info");
      setInfo(data);
    } catch {
      setInfo(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [load]);

  const available = info?.available;

  return (
    <div className="page">
      <h2 className="page-title">NapCat WebUI</h2>
      <p className="hint-line muted">
        NapCat 自带的管理面板（扫码登录、网络配置、日志、终端等），经本面板反向代理在同一端口下访问，无需额外开放端口。
        {info && (
          <>
            {" "}当前协议：<strong>{protocolLabel(info.protocol)}</strong>。
          </>
        )}
      </p>

      {loading ? (
        <Card title="NapCat WebUI">
          <p className="hint-line muted">加载中…</p>
        </Card>
      ) : available ? (
        <Card
          title="NapCat WebUI"
          extra={
            <a className="btn" href={info.url} target="_blank" rel="noreferrer">
              在新标签打开
            </a>
          }
        >
          <div className="webui-frame-wrap">
            <iframe
              className="webui-frame"
              src={info.url}
              title="NapCat WebUI"
            />
          </div>
        </Card>
      ) : (
        <Card title="NapCat WebUI 未就绪">
          <p className="hint-line warn">
            NapCat WebUI 仅在使用 <strong>NapCatQQ</strong> 协议且其进程运行时可用。
          </p>
          <ul className="muted" style={{ marginTop: 8, lineHeight: 1.8 }}>
            <li>前往「总览」将协议切换为 <strong>NapCatQQ</strong>；</li>
            <li>或前往「进程控制」启动 <strong>napcat</strong> 进程。</li>
          </ul>
          {info && (
            <p className="hint-line muted">
              当前协议：<strong>{protocolLabel(info.protocol)}</strong>，napcat 进程：
              <strong>{info.running ? "运行中" : "未运行"}</strong>。
            </p>
          )}
        </Card>
      )}
    </div>
  );
}
