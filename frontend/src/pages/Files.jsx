import { useEffect, useState, useCallback, useRef } from "react";
import Card from "../components/Card.jsx";
import Modal from "../components/Modal.jsx";
import api from "../api";
import { useConfirm, usePrompt, useToast } from "../ui.jsx";

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
  const [limits, setLimits] = useState({ maxUploadFileSize: 50 * 1024 * 1024, maxUploadFiles: 20 });
  const [editing, setEditing] = useState(null); // {path, content}
  const [editContent, setEditContent] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef(null);
  const toast = useToast();
  const confirm = useConfirm();
  const prompt = usePrompt();

  const load = useCallback(async (p) => {
    setLoading(true);
    try {
      const { data } = await api.get("/files/list", { params: { path: p } });
      setPath(data.path || "");
      setItems(data.items || []);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "无法读取目录");
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    load("");
    api.get("/system/config")
      .then(({ data }) => setLimits(data))
      .catch(() => {});
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
      toast.error(e?.response?.data?.detail || "无法读取文件");
    }
  };

  const saveEditor = async () => {
    setSaving(true);
    try {
      await api.put("/files/write", { path: editing.path, content: editContent });
      toast.success("已保存");
      setEditing(null);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "保存失败");
    } finally {
      setSaving(false);
    }
  };

  const download = (item) => {
    const full = joinPath(path, item.name);
    window.open(`/api/files/download?path=${encodeURIComponent(full)}`, "_blank");
  };

  const remove = async (item) => {
    const full = joinPath(path, item.name);
    const ok = await confirm({
      title: "删除",
      message: `确定删除 ${item.name} 吗？${item.type === "dir" ? "目录及其全部内容将被删除，" : ""}此操作不可撤销。`,
      confirmText: "删除",
      danger: true,
    });
    if (!ok) return;
    try {
      await api.delete("/files/delete", { data: { path: full } });
      toast.success("已删除");
      load(path);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "删除失败");
    }
  };

  const rename = async (item) => {
    const full = joinPath(path, item.name);
    const next = await prompt({
      title: "重命名",
      message: "输入同目录下的新名称：",
      defaultValue: item.name,
      required: true,
      requiredMessage: "名称不能为空",
    });
    if (!next || next === item.name) return;
    try {
      await api.post("/files/rename", { src: full, dst: joinPath(path, next) });
      toast.success("已重命名");
      load(path);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "重命名失败");
    }
  };

  const mkdir = async () => {
    const name = await prompt({
      title: "新建文件夹",
      message: "输入文件夹名称：",
      placeholder: "例如 my-folder",
      required: true,
      requiredMessage: "名称不能为空",
    });
    if (!name) return;
    try {
      await api.post("/files/mkdir", { path: joinPath(path, name) });
      toast.success("已创建");
      load(path);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "创建失败");
    }
  };

  const newFile = async () => {
    const name = await prompt({
      title: "新建文件",
      message: "输入文件名称：",
      placeholder: "例如 config.json",
      required: true,
      requiredMessage: "名称不能为空",
    });
    if (!name) return;
    try {
      await api.put("/files/write", { path: joinPath(path, name), content: "" });
      toast.success("已创建");
      load(path);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "创建失败");
    }
  };

  const uploadFiles = async (files) => {
    if (!files || files.length === 0) return;
    if (files.length > limits.maxUploadFiles) {
      toast.error(`一次最多上传 ${limits.maxUploadFiles} 个文件`);
      return;
    }
    const tooLarge = files.find((f) => f.size > limits.maxUploadFileSize);
    if (tooLarge) {
      toast.error(`${tooLarge.name} 超过 ${fmtSize(limits.maxUploadFileSize)} 限制`);
      return;
    }
    const form = new FormData();
    form.append("path", path);
    files.forEach((f) => form.append("files", f));
    try {
      await api.post("/files/upload", form);
      toast.success(`已上传 ${files.length} 个文件`);
      load(path);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "上传失败");
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
        <p className="hint-line">
          文件管理限制在 /data 内；单文件上传上限 {fmtSize(limits.maxUploadFileSize)}，一次最多 {limits.maxUploadFiles} 个文件。
        </p>
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
            <button className="btn primary" disabled={saving} onClick={saveEditor}>
              {saving ? "保存中…" : "保存"}
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
    </div>
  );
}
