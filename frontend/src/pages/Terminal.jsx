import { useEffect, useRef, useState } from "react";
import { Terminal as XTerm } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";

export default function Terminal() {
  const containerRef = useRef(null);
  const [seed, setSeed] = useState(0);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const term = new XTerm({
      cursorBlink: true,
      fontSize: 14,
      fontFamily: "Menlo, Consolas, 'Courier New', monospace",
      theme: { background: "#1e1e1e", foreground: "#e0e0e0" },
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(containerRef.current);
    fit.fit();

    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${window.location.host}/ws/terminal`);

    const sendResize = () => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "resize", cols: term.cols, rows: term.rows }));
      }
    };

    ws.onopen = () => {
      setConnected(true);
      term.writeln("\u001b[32m已连接到容器终端 (appuser @ /data)\u001b[0m");
      sendResize();
    };
    ws.onmessage = (ev) => term.write(ev.data);
    ws.onclose = (ev) => {
      setConnected(false);
      if (ev.code === 4401) {
        term.writeln("\r\n\u001b[31m未授权：请重新登录。\u001b[0m");
      } else {
        term.writeln("\r\n\u001b[33m连接已关闭，点击「重新连接」恢复会话。\u001b[0m");
      }
    };
    ws.onerror = () => term.writeln("\r\n\u001b[31m连接错误。\u001b[0m");

    const dataSub = term.onData((data) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "input", data }));
      }
    });

    const onResize = () => {
      try {
        fit.fit();
        sendResize();
      } catch {
        /* ignore */
      }
    };
    window.addEventListener("resize", onResize);

    return () => {
      window.removeEventListener("resize", onResize);
      dataSub.dispose();
      try {
        ws.close();
      } catch {
        /* ignore */
      }
      term.dispose();
    };
  }, [seed]);

  return (
    <div className="page terminal-page">
      <div className="terminal-bar">
        <h2 className="page-title" style={{ margin: 0 }}>网页终端</h2>
        <span className={`conn-dot ${connected ? "on" : "off"}`} />
        <span className="conn-text">{connected ? "已连接" : "未连接"}</span>
        <button className="btn" onClick={() => setSeed((s) => s + 1)}>重新连接</button>
      </div>
      <div className="terminal-wrap">
        <div ref={containerRef} className="terminal-host" />
      </div>
    </div>
  );
}
