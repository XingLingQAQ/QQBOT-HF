import { useEffect, useState, useCallback } from "react";
import Card from "../components/Card.jsx";
import api from "../api";
import { loginState } from "../format";
import { useConfirm, useToast } from "../ui.jsx";

const STATUS_HINT = {
  online: "已登录并连接成功。",
  offline: "Lagrange 未运行或未登录，请刷新二维码后使用手机 QQ 扫码。",
  waiting_scan: "请使用手机 QQ 扫描下方二维码登录。",
  scanned: "已扫码，正在等待 NoneBot 连接…",
  expired: "二维码已过期，请点击「刷新二维码」重新获取。",
};

export default function QRLogin() {
  const [info, setInfo] = useState({ status: "offline", qq: "", nickname: "" });
  const [qrTs, setQrTs] = useState(Date.now());
  const [busy, setBusy] = useState(false);
  const [qrOk, setQrOk] = useState(false);
  const confirm = useConfirm();
  const toast = useToast();

  const poll = useCallback(async () => {
    try {
      const { data } = await api.get("/login-status");
      setInfo(data);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    poll();
    const id = setInterval(poll, 2500);
    return () => clearInterval(id);
  }, [poll]);

  // Refresh the QR image periodically while waiting to scan.
  useEffect(() => {
    if (info.status === "waiting_scan" || info.status === "expired") {
      const id = setInterval(() => setQrTs(Date.now()), 5000);
      return () => clearInterval(id);
    }
  }, [info.status]);

  const refreshQr = async () => {
    setBusy(true);
    try {
      await api.post("/restart-lagrange");
      toast.info("已请求重启 Lagrange，正在生成新的二维码…");
      setTimeout(() => setQrTs(Date.now()), 2000);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "刷新失败");
    } finally {
      setBusy(false);
    }
  };

  const logoutQq = async () => {
    const ok = await confirm({
      title: "退出登录",
      message: "确定要退出当前 QQ 登录吗？将删除登录凭据并重启 Lagrange。",
      confirmText: "退出登录",
      danger: true,
    });
    if (!ok) return;
    setBusy(true);
    try {
      await api.post("/logout-qq");
      toast.success("已退出登录，请重新扫码。");
      setTimeout(() => setQrTs(Date.now()), 2000);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "退出失败");
    } finally {
      setBusy(false);
    }
  };

  const isOnline = info.status === "online";
  const badge = loginState(info.status);

  return (
    <div className="page">
      <h2 className="page-title">扫码登录</h2>
      <Card
        title={isOnline ? "账号信息" : "扫码登录"}
        extra={<span className={`badge ${badge.tone}`}>{badge.text}</span>}
      >
        <p className="hint-line">{STATUS_HINT[info.status] || ""}</p>

        {isOnline ? (
          <div>
            <div className="kv">
              <span>QQ 号</span>
              <span>{info.qq || "—"}</span>
            </div>
            <div className="kv">
              <span>昵称</span>
              <span>{info.nickname || "—"}</span>
            </div>
            <button className="btn danger" disabled={busy} onClick={logoutQq}>
              退出登录
            </button>
          </div>
        ) : (
          <div className="qr-box">
            <div className="qr-frame">
              <img
                className="qr-img"
                src={`/api/qrcode?t=${qrTs}`}
                alt="登录二维码"
                style={{ display: qrOk ? "block" : "none" }}
                onError={() => setQrOk(false)}
                onLoad={() => setQrOk(true)}
              />
              {!qrOk && (
                <div className="qr-placeholder">
                  <span className="spinner" />
                  <span>二维码生成中…</span>
                </div>
              )}
            </div>
            <div className="qr-actions">
              <button className="btn primary" disabled={busy} onClick={refreshQr}>
                {busy ? "处理中…" : "刷新二维码"}
              </button>
              <p className="hint-line muted">页面每 2.5 秒自动检测登录状态，二维码自动刷新。</p>
            </div>
          </div>
        )}
      </Card>

      <Card title="签名服务说明">
        <p className="hint-line">
          扫码登录依赖可用的 Lagrange 签名服务（SignServer）。若长时间无法生成二维码或日志报
          <code>Signer server returned a NotFound</code> / <code>All login failed</code>，
          通常是官方签名服务暂时不可用或与当前 Lagrange 版本不匹配。
        </p>
        <p className="hint-line">
          可在「文件管理」中编辑 <code>/data/lagrange/appsettings.json</code> 的
          <code>SignServerUrl</code> 字段填入可用的签名服务地址后，回到本页点击「刷新二维码」重试。
          排查时请查看 <code>/data/manager/lagrange.log</code>。
        </p>
      </Card>
    </div>
  );
}
