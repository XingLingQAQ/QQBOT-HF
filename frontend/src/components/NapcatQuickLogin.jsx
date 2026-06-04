import { useCallback, useEffect, useState } from "react";
import api from "../api";
import Card from "./Card.jsx";
import { useToast } from "../ui.jsx";

// NapCat quick-login config. When enabled with a QQ uin, NapCat reuses a
// previously scanned session and auto-logs in (no QR). Only affects the NapCat
// backend; takes effect immediately if NapCat is active, otherwise on next start.
export default function NapcatQuickLogin() {
  const [enabled, setEnabled] = useState(false);
  const [qq, setQq] = useState("");
  const [protocol, setProtocol] = useState("");
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  const load = useCallback(async () => {
    try {
      const { data } = await api.get("/napcat/quick-login");
      setEnabled(!!data.enabled);
      setQq(data.qq || "");
      setProtocol(data.protocol || "");
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const save = async () => {
    if (enabled && !/^\d+$/.test(qq.trim())) {
      toast.error("启用快速登录时必须填写纯数字的 QQ 号。");
      return;
    }
    setBusy(true);
    try {
      const { data } = await api.post("/napcat/quick-login", {
        enabled,
        qq: qq.trim(),
      });
      setEnabled(!!data.enabled);
      setQq(data.qq || "");
      if (data.applied) {
        toast.success("已保存并重启 NapCat 使配置生效。");
      } else if (protocol === "napcat") {
        toast.info("已保存（NapCat 重启未成功，请在「进程控制」中手动重启）。");
      } else {
        toast.success("已保存。切换到 NapCat 协议后生效。");
      }
    } catch (e) {
      toast.error(`保存失败：${e?.response?.data?.detail || e.message}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title="NapCat 快速登录">
      <p className="hint-line muted">
        启用后，NapCat 将使用上次扫码登录保存的会话自动登录，无需重复扫码。
        前提是该 QQ 号此前已在本容器成功登录过一次。仅对 NapCatQQ 协议生效。
      </p>
      <label className="field">
        <span>QQ 号</span>
        <input
          type="text"
          inputMode="numeric"
          placeholder="例如 10001"
          value={qq}
          onChange={(e) => setQq(e.target.value.replace(/[^\d]/g, ""))}
          disabled={busy}
        />
      </label>
      <label className="checkbox-row">
        <input
          type="checkbox"
          checked={enabled}
          onChange={(e) => setEnabled(e.target.checked)}
          disabled={busy}
        />
        <span>启用快速登录</span>
      </label>
      <div className="maintenance-actions">
        <button className="btn primary" onClick={save} disabled={busy}>
          {busy ? "保存中…" : "保存"}
        </button>
      </div>
      {protocol && protocol !== "napcat" && (
        <p className="hint-line muted">当前协议为「{protocol}」，配置将在切换到 NapCat 后生效。</p>
      )}
    </Card>
  );
}
