// Shared formatting helpers for process / login status display.

// Map a supervisor process state to a localized label + indicator color.
const PROC_STATES = {
  RUNNING: { text: "运行中", tone: "green" },
  STARTING: { text: "启动中", tone: "yellow" },
  STOPPING: { text: "停止中", tone: "yellow" },
  STOPPED: { text: "已停止", tone: "red" },
  EXITED: { text: "已退出", tone: "red" },
  FATAL: { text: "异常退出", tone: "red" },
  BACKOFF: { text: "重启中", tone: "yellow" },
  UNKNOWN: { text: "未知", tone: "gray" },
};

export function procState(state) {
  return PROC_STATES[state] || { text: state || "未知", tone: "gray" };
}

// Map a login status to a localized label + badge color.
const LOGIN_STATES = {
  online: { text: "在线", tone: "green" },
  offline: { text: "离线", tone: "red" },
  waiting_scan: { text: "等待扫码", tone: "yellow" },
  scanned: { text: "已扫码", tone: "yellow" },
  expired: { text: "二维码已过期", tone: "red" },
};

export function loginState(status) {
  return LOGIN_STATES[status] || LOGIN_STATES.offline;
}

// QQ protocol backend metadata (selector labels + descriptions).
export const PROTOCOLS = {
  lagrange: {
    label: "Lagrange.OneBot",
    desc: "搭配自建签名服务（VincentZyu233/SignServer）使用",
  },
  napcat: {
    label: "NapCatQQ",
    desc: "基于官方 QQ 注入，无需签名服务；选用后 Lagrange 及签名服务停止",
  },
};

export function protocolLabel(p) {
  return (PROTOCOLS[p] && PROTOCOLS[p].label) || p || "未知";
}

// QQ avatar URL (public endpoint). Returns empty string when no uin.
export function qqAvatar(uin) {
  const u = String(uin || "").trim();
  if (!u || !/^\d+$/.test(u)) return "";
  return `https://q1.qlogo.cn/g?b=qq&nk=${u}&s=100`;
}
