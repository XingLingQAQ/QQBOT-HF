import axios from "axios";

// Same-origin axios instance; session cookie is sent automatically.
const api = axios.create({
  baseURL: "/api",
  withCredentials: true,
});

// On 401 redirect to the login page (unless we are already there or merely
// probing auth state via /check-auth).
api.interceptors.response.use(
  (resp) => resp,
  (error) => {
    const status = error?.response?.status;
    const url = error?.config?.url || "";
    if (status === 401 && !url.includes("check-auth") && !url.includes("login")) {
      if (window.location.pathname !== "/login") {
        window.location.assign("/login");
      }
    }
    return Promise.reject(error);
  }
);

export default api;
