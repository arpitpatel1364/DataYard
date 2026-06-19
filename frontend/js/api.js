/* =========================================================================
   CIS API CLIENT
   Centralizes fetch calls, JWT storage/refresh, and error handling so
   every page just calls CISApi.get('/api/datasets') etc.
   ========================================================================= */
(function (window) {
  const TOKEN_KEY = "cis_access_token";
  const REFRESH_KEY = "cis_refresh_token";

  function getAccessToken() { return localStorage.getItem(TOKEN_KEY); }
  function getRefreshToken() { return localStorage.getItem(REFRESH_KEY); }
  function setTokens(access, refresh) {
    localStorage.setItem(TOKEN_KEY, access);
    if (refresh) localStorage.setItem(REFRESH_KEY, refresh);
  }
  function clearTokens() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_KEY);
  }

  async function refreshAccessToken() {
    const refresh = getRefreshToken();
    if (!refresh) return false;
    try {
      const res = await fetch("/api/auth/refresh", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refresh }),
      });
      if (!res.ok) return false;
      const data = await res.json();
      setTokens(data.access_token, data.refresh_token);
      return true;
    } catch (e) {
      return false;
    }
  }

  async function request(method, path, body, opts) {
    opts = opts || {};
    const headers = Object.assign({}, opts.headers || {});
    const isForm = body instanceof FormData;
    if (!isForm) headers["Content-Type"] = "application/json";
    const token = getAccessToken();
    if (token && !opts.noAuth) headers["Authorization"] = "Bearer " + token;

    const doFetch = () => fetch(path, {
      method,
      headers,
      body: body ? (isForm ? body : JSON.stringify(body)) : undefined,
    });

    let res = await doFetch();

    if (res.status === 401 && !opts.noAuth && !opts._retried) {
      const refreshed = await refreshAccessToken();
      if (refreshed) {
        return request(method, path, body, Object.assign({}, opts, { _retried: true }));
      } else {
        clearTokens();
        if (!path.includes("/auth/")) window.location.href = "/login.html";
      }
    }

    if (res.status === 204) return null;

    let data = null;
    const text = await res.text();
    try { data = text ? JSON.parse(text) : null; } catch (e) { data = text; }

    if (!res.ok) {
      const message = (data && (data.detail || data.message)) ||
        (typeof data === "string" ? data : `Request failed (${res.status})`);
      const err = new Error(typeof message === "string" ? message : JSON.stringify(message));
      err.status = res.status;
      err.data = data;
      throw err;
    }
    return data;
  }

  window.CISApi = {
    get: (path, opts) => request("GET", path, null, opts),
    post: (path, body, opts) => request("POST", path, body, opts),
    put: (path, body, opts) => request("PUT", path, body, opts),
    patch: (path, body, opts) => request("PATCH", path, body, opts),
    delete: (path, opts) => request("DELETE", path, null, opts),
    setTokens, clearTokens, getAccessToken, getRefreshToken,
    isAuthenticated: () => !!getAccessToken(),
  };
})(window);
