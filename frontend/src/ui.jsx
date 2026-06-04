import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import Modal from "./components/Modal.jsx";

// Unified front-end interaction primitives shared by every page:
//   * toast notifications (replacing per-page ad-hoc <div className="toast">)
//   * confirm / prompt dialogs (replacing native window.confirm / window.prompt)
// A single <UIProvider> at the app root renders the toast stack and the active
// dialog; pages call the `useToast` / `useConfirm` / `usePrompt` hooks.

const UIContext = createContext(null);

let _toastId = 0;

const DEFAULT_DURATION = { success: 3000, info: 3500, error: 6000 };

export function UIProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const [dialog, setDialog] = useState(null); // {kind, ...opts}
  const [inputValue, setInputValue] = useState("");
  const [inputError, setInputError] = useState("");
  const resolverRef = useRef(null);
  const timersRef = useRef(new Map());

  const dismiss = useCallback((id) => {
    setToasts((list) => list.filter((t) => t.id !== id));
    const timer = timersRef.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timersRef.current.delete(id);
    }
  }, []);

  const pushToast = useCallback(
    (message, type = "info", duration) => {
      if (!message) return -1;
      const id = ++_toastId;
      setToasts((list) => [...list, { id, message: String(message), type }]);
      const ms = duration ?? DEFAULT_DURATION[type] ?? 3500;
      if (ms > 0) {
        const timer = setTimeout(() => dismiss(id), ms);
        timersRef.current.set(id, timer);
      }
      return id;
    },
    [dismiss]
  );

  useEffect(() => {
    const timers = timersRef.current;
    return () => {
      timers.forEach((t) => clearTimeout(t));
      timers.clear();
    };
  }, []);

  const toast = useMemo(
    () => ({
      show: pushToast,
      info: (m, d) => pushToast(m, "info", d),
      success: (m, d) => pushToast(m, "success", d),
      error: (m, d) => pushToast(m, "error", d),
    }),
    [pushToast]
  );

  const settle = useCallback((result) => {
    const resolve = resolverRef.current;
    resolverRef.current = null;
    setDialog(null);
    setInputError("");
    if (resolve) resolve(result);
  }, []);

  const confirm = useCallback((opts = {}) => {
    return new Promise((resolve) => {
      resolverRef.current = resolve;
      setDialog({ kind: "confirm", ...opts });
    });
  }, []);

  const prompt = useCallback((opts = {}) => {
    return new Promise((resolve) => {
      resolverRef.current = resolve;
      setInputValue(opts.defaultValue || "");
      setInputError("");
      setDialog({ kind: "prompt", ...opts });
    });
  }, []);

  const value = useMemo(() => ({ toast, confirm, prompt }), [toast, confirm, prompt]);

  const isPrompt = dialog?.kind === "prompt";
  const danger = !!dialog?.danger;

  const onConfirm = () => {
    if (isPrompt) {
      const v = inputValue.trim();
      if (dialog.required && !v) {
        setInputError(dialog.requiredMessage || "请输入内容");
        return;
      }
      settle(v);
    } else {
      settle(true);
    }
  };

  const onCancel = () => settle(isPrompt ? null : false);

  return (
    <UIContext.Provider value={value}>
      {children}

      <div className="toast-stack" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.type}`} onClick={() => dismiss(t.id)}>
            <span className="toast-msg">{t.message}</span>
            <button className="toast-close" aria-label="关闭" onClick={() => dismiss(t.id)}>
              ×
            </button>
          </div>
        ))}
      </div>

      <Modal
        open={!!dialog}
        title={dialog?.title || (isPrompt ? "请输入" : "请确认")}
        onClose={onCancel}
        footer={
          <>
            <button className="btn" onClick={onCancel}>
              {dialog?.cancelText || "取消"}
            </button>
            <button className={`btn ${danger ? "danger" : "primary"}`} onClick={onConfirm}>
              {dialog?.confirmText || "确定"}
            </button>
          </>
        }
      >
        {dialog?.message && <p className="dialog-message">{dialog.message}</p>}
        {isPrompt && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              onConfirm();
            }}
          >
            <input
              className="dialog-input"
              autoFocus
              value={inputValue}
              placeholder={dialog.placeholder || ""}
              onChange={(e) => {
                setInputValue(e.target.value);
                if (inputError) setInputError("");
              }}
            />
            {inputError && <p className="dialog-error">{inputError}</p>}
          </form>
        )}
      </Modal>
    </UIContext.Provider>
  );
}

function useUI() {
  const ctx = useContext(UIContext);
  if (!ctx) throw new Error("useUI must be used within <UIProvider>");
  return ctx;
}

export function useToast() {
  return useUI().toast;
}

export function useConfirm() {
  return useUI().confirm;
}

export function usePrompt() {
  return useUI().prompt;
}
