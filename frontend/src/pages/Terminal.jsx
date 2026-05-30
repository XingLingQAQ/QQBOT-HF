import { useEffect, useRef } from "react";
import { Terminal as XTerm } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";

export default function Terminal() {
  const containerRef = useRef(null);
  const termRef = useRef(null);
  const wsRef = useRef(null);

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
    termRef.current = term;

    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${window.location.host}/ws/terminal`);
    wsRef.current = ws;

    const sendResize = () => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(
          JSON.stringify({ type: "resize", cols: term.cols, rows: term.rows })
        );
      }
    };

    ws.onopen = () => {
      term.writeln("\u001b[32m已连接到容器终端 (appuser @ /data)\u001b[0m");
      sendResize();
    };
    ws.onmessage = (ev) => term.write(ev.data);
    ws.onclose = (ev) => {
      if (ev.code === 4401) {
        term.writeln("\r\n\u001b[31m未授权：请重新登录。\u001b[0m");
      } else {
        term.writeln("\r\n\u001b[33m连接已关闭。\u001b[0m");
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
  }, []);

  return (
    <div className="page terminal-page">
      <h2 className="page-title">网页终端</h2>
      <div className="terminal-wrap">
        <div ref={containerRef} className="terminal-host" />
      </div>
    </div>
  );
}
