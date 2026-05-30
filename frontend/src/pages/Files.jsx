import { useEffect, useState, useCallback, useRef } from "react";
import Card from "../components/Card.jsx";
import Modal from "../components/Modal.jsx";
import api from "../api";

function joinPath(base, name) {
  if (!base) return name;
  return `${base}/${name}`;
}

function parentPath(path) {
  if (!path) return "";
  const idx = path.lastIndexOf("/");
  return idx === -1 ? "" : path.slice(0, idx);
}

function fmtSize(n) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export default function Files() {
  const [path, setPath] = useState("");
  const [items, setItems] = useState([]);
  const [toast, setToast] = useState("");
  const [editing, setEditing] = useState(null); // {path, content}
  const [editContent, setEditContent] = useState("");
  const [loading, setLoading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef(null);

  const flash = (t) => {
    setToast(t);
    setTimeout(() => setToast(""), 3500);
  };

  const load = useCallback(async (p) => {
    setLoading(true);
    try {
      const { data } = await api.get("/files/list", { params: { path: p } });
      setPath(data.path || "");
      setItems(data.items || []);
    } catch (e) {
      flash(e?.response?.data?.detail || "无法读取目录");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load("");
  }, [load]);

  const enter = (item) => {
    if (item.type === "dir") load(joinPath(path, item.name));
  };

  const openEditor = async (item) => {
    const full = joinPath(path, item.name);
    try {
      const { data } = await api.get("/files/read", { params: { path: full } });
      setEditing({ path: full });
      setEditContent(data.content);
    } catch (e) {
      flash(e?.response?.data?.detail || "无法读取文件");
    }
  };

  const saveEditor = async () => {
    try {
      await api.put("/files/write", { path: editing.path, content: editContent });
      flash("已保存");
      setEditing(null);
    } catch (e) {
      flash(e?.response?.data?.detail || "保存失败");
    }
  };

  const download = (item) => {
    const full = joinPath(path, item.name);
    window.open(`/api/files/download?path=${encodeURIComponent(full)}`, "_blank");
  };

  const remove = async (item) => {
    const full = joinPath(path, item.name);
    if (!window.confirm(`确定删除 ${item.name} 吗？`)) return;
    try {
      await api.delete("/files/delete", { data: { path: full } });
      flash("已删除");
      load(path);
    } catch (e) {
      flash(e?.response?.data?.detail || "删除失败");
    }
  };

  const rename = async (item) => {
    const full = joinPath(path, item.name);
    const next = window.prompt("重命名为（同目录下新名称）：", item.name);
    if (!next || next === item.name) return;
    try {
      await api.post("/files/rename", { src: full, dst: joinPath(path, next) });
      flash("已重命名");
      load(path);
    } catch (e) {
      flash(e?.response?.data?.detail || "重命名失败");
    }
  };

  const mkdir = async () => {
    const name = window.prompt("新文件夹名称：");
    if (!name) return;
    try {
      await api.post("/files/mkdir", { path: joinPath(path, name) });
      flash("已创建");
      load(path);
    } catch (e) {
      flash(e?.response?.data?.detail || "创建失败");
    }
  };

  const newFile = async () => {
    const name = window.prompt("新文件名称：");
    if (!name) return;
    try {
      await api.put("/files/write", { path: joinPath(path, name), content: "" });
      flash("已创建");
      load(path);
    } catch (e) {
      flash(e?.response?.data?.detail || "创建失败");
    }
  };

  const uploadFiles = async (files) => {
    if (!files || files.length === 0) return;
    const form = new FormData();
    form.append("path", path);
    files.forEach((f) => form.append("files", f));
    try {
      await api.post("/files/upload", form);
      flash(`已上传 ${files.length} 个文件`);
      load(path);
    } catch (err) {
      flash(err?.response?.data?.detail || "上传失败");
    } finally {
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const upload = (e) => uploadFiles(Array.from(e.target.files || []));

  const onDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    uploadFiles(Array.from(e.dataTransfer?.files || []));
  };

  const crumbs = path ? path.split("/") : [];

  return (
    <div className="page">
      <h2 className="page-title">文件管理</h2>
      <Card
        title={
          <span className="breadcrumb">
            <button className="crumb" onClick={() => load("")}>
              /data
            </button>
            {crumbs.map((c, i) => {
              const target = crumbs.slice(0, i + 1).join("/");
              return (
                <span key={target}>
                  <span className="crumb-sep">/</span>
                  <button className="crumb" onClick={() => load(target)}>
                    {c}
                  </button>
                </span>
              );
            })}
          </span>
        }
        extra={
          <div className="toolbar">
            <button className="btn" onClick={() => load(path)}>
              刷新
            </button>
            <button className="btn" onClick={newFile}>
              新建文件
            </button>
            <button className="btn" onClick={mkdir}>
              新建文件夹
            </button>
            <button className="btn primary" onClick={() => fileInputRef.current?.click()}>
              上传
            </button>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              hidden
              onChange={upload}
            />
          </div>
        }
      >
        <div
          className={`dropzone ${dragOver ? "drag" : ""}`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
        >
        {loading && <div className="empty">加载中…</div>}
        <table className="table">
          <thead>
            <tr>
              <th>名称</th>
              <th>类型</th>
              <th>大小</th>
              <th>修改时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {path && (
              <tr>
                <td colSpan={5}>
                  <button className="btn-link" onClick={() => load(parentPath(path))}>
                    .. 返回上级
                  </button>
                </td>
              </tr>
            )}
            {items.map((item) => (
              <tr key={item.name}>
                <td>
                  {item.type === "dir" ? (
                    <button className="btn-link" onClick={() => enter(item)}>
                      📁 {item.name}
                    </button>
                  ) : (
                    <button className="btn-link" onClick={() => openEditor(item)}>
                      📄 {item.name}
                    </button>
                  )}
                </td>
                <td>{item.type === "dir" ? "目录" : "文件"}</td>
                <td>{item.type === "dir" ? "—" : fmtSize(item.size)}</td>
                <td>{new Date(item.mtime * 1000).toLocaleString()}</td>
                <td className="row-actions">
                  {item.type === "file" && (
                    <button className="btn-link" onClick={() => download(item)}>
                      下载
                    </button>
                  )}
                  <button className="btn-link" onClick={() => rename(item)}>
                    重命名
                  </button>
                  <button className="btn-link danger" onClick={() => remove(item)}>
                    删除
                  </button>
                </td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr>
                <td colSpan={5} className="empty">
                  空目录
                </td>
              </tr>
            )}
          </tbody>
        </table>
        {dragOver && <div className="drop-hint">松开以上传到当前目录</div>}
        </div>
      </Card>

      <Modal
        title={editing ? `编辑 ${editing.path}` : "编辑"}
        open={!!editing}
        onClose={() => setEditing(null)}
        footer={
          <>
            <button className="btn" onClick={() => setEditing(null)}>
              取消
            </button>
            <button className="btn primary" onClick={saveEditor}>
              保存
            </button>
          </>
        }
      >
        <textarea
          className="code-area"
          rows={18}
          value={editContent}
          onChange={(e) => setEditContent(e.target.value)}
        />
      </Modal>

      {toast && <div className="toast">{toast}</div>}
    </div>
  );
}
