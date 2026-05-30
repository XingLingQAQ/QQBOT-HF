import { useEffect, useState, useCallback } from "react";
import Card from "../components/Card.jsx";
import Modal from "../components/Modal.jsx";
import api from "../api";

export default function Plugins() {
  const [plugins, setPlugins] = useState([]);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState("");
  const [configFor, setConfigFor] = useState(null);
  const [configText, setConfigText] = useState("{}");

  const load = useCallback(async () => {
    try {
      const { data } = await api.get("/plugins");
      setPlugins(data.plugins || []);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const flash = (text) => {
    setToast(text);
    setTimeout(() => setToast(""), 4000);
  };

  const install = async (e) => {
    e.preventDefault();
    const pkg = name.trim();
    if (!pkg) return;
    setBusy(true);
    try {
      await api.post("/plugins/install", { name: pkg });
      flash(`已安装 ${pkg}`);
      setName("");
      await load();
    } catch (err) {
      flash(err?.response?.data?.detail || "安装失败");
    } finally {
      setBusy(false);
    }
  };

  const uninstall = async (pkg) => {
    if (!window.confirm(`确定卸载 ${pkg} 吗？`)) return;
    setBusy(true);
    try {
      await api.post("/plugins/uninstall", { name: pkg });
      flash(`已卸载 ${pkg}`);
      await load();
    } catch (err) {
      flash(err?.response?.data?.detail || "卸载失败");
    } finally {
      setBusy(false);
    }
  };

  const toggle = async (p) => {
    setBusy(true);
    try {
      await api.put("/plugins/toggle", { name: p.name, enabled: !p.enabled });
      await load();
    } catch (err) {
      flash(err?.response?.data?.detail || "操作失败");
    } finally {
      setBusy(false);
    }
  };

  const openConfig = (p) => {
    setConfigFor(p);
    setConfigText(JSON.stringify(p.config || {}, null, 2));
  };

  const saveConfig = async () => {
    let parsed;
    try {
      parsed = JSON.parse(configText || "{}");
    } catch {
      flash("配置必须是合法的 JSON");
      return;
    }
    setBusy(true);
    try {
      await api.put("/plugins/config", { name: configFor.name, config: parsed });
      flash("配置已保存");
      setConfigFor(null);
      await load();
    } catch (err) {
      flash(err?.response?.data?.detail || "保存失败");
    } finally {
      setBusy(false);
    }
  };

  const restart = async () => {
    setBusy(true);
    try {
      await api.post("/plugins/restart");
      flash("已重启 NoneBot");
    } catch (err) {
      flash(err?.response?.data?.detail || "重启失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page">
      <h2 className="page-title">插件管理</h2>

      <Card
        title="安装插件"
        extra={
          <button className="btn" disabled={busy} onClick={restart}>
            重启 NoneBot
          </button>
        }
      >
        <form className="install-bar" onSubmit={install}>
          <input
            placeholder="插件包名，例如 nonebot-plugin-status"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <button className="btn primary" type="submit" disabled={busy}>
            {busy ? "处理中…" : "安装"}
          </button>
        </form>
        <p className="hint-line">
          仅允许形如 <code>nonebot-plugin-xxx</code> / <code>nonebot_plugin_xxx</code> 的包名。
        </p>
      </Card>

      <Card title={`已安装插件 (${plugins.length})`}>
        {plugins.length === 0 ? (
          <p className="empty">暂无已安装插件。</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>名称</th>
                <th>版本</th>
                <th>启用</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {plugins.map((p) => (
                <tr key={p.name}>
                  <td>{p.name}</td>
                  <td>{p.version || "—"}</td>
                  <td>
                    <label className="switch">
                      <input
                        type="checkbox"
                        checked={!!p.enabled}
                        disabled={busy}
                        onChange={() => toggle(p)}
                      />
                      <span className="slider" />
                    </label>
                  </td>
                  <td className="row-actions">
                    <button className="btn-link" onClick={() => openConfig(p)}>
                      配置
                    </button>
                    <button
                      className="btn-link danger"
                      onClick={() => uninstall(p.name)}
                    >
                      卸载
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <Modal
        title={configFor ? `配置 ${configFor.name}` : "配置"}
        open={!!configFor}
        onClose={() => setConfigFor(null)}
        footer={
          <>
            <button className="btn" onClick={() => setConfigFor(null)}>
              取消
            </button>
            <button className="btn primary" disabled={busy} onClick={saveConfig}>
              保存
            </button>
          </>
        }
      >
        <p className="hint-line">以 JSON 形式编辑插件配置，键将写入 NoneBot 的 .env。</p>
        <textarea
          className="code-area"
          rows={12}
          value={configText}
          onChange={(e) => setConfigText(e.target.value)}
        />
      </Modal>

      {toast && <div className="toast">{toast}</div>}
    </div>
  );
}
