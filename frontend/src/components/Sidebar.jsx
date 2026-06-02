import { useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../auth.jsx";
import StatusLights from "./StatusLights.jsx";

const NAV = [
  { to: "/", label: "总览", icon: "▣", end: true },
  { to: "/qrlogin", label: "扫码登录", icon: "▦" },
  { to: "/napcat-webui", label: "NapCat WebUI", icon: "◆" },
  { to: "/plugins", label: "插件管理", icon: "◧" },
  { to: "/processes", label: "进程控制", icon: "⚙" },
  { to: "/logs", label: "日志", icon: "≡" },
  { to: "/files", label: "文件管理", icon: "▤" },
  { to: "/terminal", label: "网页终端", icon: "❯" },
];

export default function Sidebar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);

  const handleLogout = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  return (
    <>
      <button className="hamburger" onClick={() => setOpen((v) => !v)} aria-label="menu">
        ☰
      </button>
      <div
        className={`scrim ${open ? "show" : ""}`}
        onClick={() => setOpen(false)}
      />
      <aside className={`sidebar ${open ? "open" : ""}`}>
        <div className="brand">QQ 机器人面板</div>
        <nav className="nav">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
              onClick={() => setOpen(false)}
            >
              <span className="nav-icon">{item.icon}</span>
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <StatusLights />
          <div className="user-row">
            <span className="user-name">{user}</span>
            <button className="btn-link" onClick={handleLogout}>
              退出登录
            </button>
          </div>
        </div>
      </aside>
    </>
  );
}
