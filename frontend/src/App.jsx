import { Routes, Route, Navigate } from "react-router-dom";
import Sidebar from "./components/Sidebar.jsx";
import ProtectedRoute from "./components/ProtectedRoute.jsx";
import Login from "./pages/Login.jsx";
import Overview from "./pages/Overview.jsx";
import QRLogin from "./pages/QRLogin.jsx";
import Plugins from "./pages/Plugins.jsx";
import Files from "./pages/Files.jsx";
import Terminal from "./pages/Terminal.jsx";

function Layout({ children }) {
  return (
    <div className="layout">
      <Sidebar />
      <main className="content">{children}</main>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="/*"
        element={
          <ProtectedRoute>
            <Layout>
              <Routes>
                <Route path="/" element={<Overview />} />
                <Route path="/qrlogin" element={<QRLogin />} />
                <Route path="/plugins" element={<Plugins />} />
                <Route path="/files" element={<Files />} />
                <Route path="/terminal" element={<Terminal />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </Layout>
          </ProtectedRoute>
        }
      />
    </Routes>
  );
}
