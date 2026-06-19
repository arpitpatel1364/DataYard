/* =========================================================================
   CIS APP SHELL
   Renders the sidebar + topbar into every page and provides small shared
   UI helpers (toasts, grade badges, modals) so individual page scripts
   stay focused on their own data.
   ========================================================================= */

const CIS_NAV = [
  { group: "Overview", items: [
    { id: "dashboard", label: "Dashboard", icon: "fa-table-cells-large", href: "/index.html" },
  ]},
  { group: "Datasets", items: [
    { id: "my-datasets", label: "My Datasets", icon: "fa-database", href: "/datasets.html" },
    { id: "import", label: "Import Dataset", icon: "fa-file-import", href: "/import.html" },
    { id: "registry", label: "Dataset Registry", icon: "fa-list-check", href: "/registry.html" },
    { id: "merger", label: "Dataset Merger", icon: "fa-object-group", href: "/merger.html" },
  ]},
  { group: "Analysis", items: [
    { id: "health", label: "Health Reports", icon: "fa-heart-pulse", href: "/dataset-detail.html" },
    { id: "class-intel", label: "Class Intelligence", icon: "fa-tags", href: "/dataset-detail.html#classes" },
  ]},
  { group: "Comparison", items: [
    { id: "compare", label: "Compare Datasets", icon: "fa-code-compare", href: "/compare.html" },
  ]},
  { group: "Models", items: [
    { id: "model-lab", label: "Model Testing Lab", icon: "fa-flask", href: "/model-lab.html" },
    { id: "model-detail", label: "Benchmarking & Analytics", icon: "fa-chart-line", href: "/model-detail.html" },
  ]},
  { group: "Monitoring", items: [
    { id: "monitoring", label: "Live Monitoring", icon: "fa-satellite-dish", href: "/monitoring.html" },
  ]},
  { group: "Administration", items: [
    { id: "admin-users", label: "Users", icon: "fa-users", href: "/admin-users.html" },
    { id: "admin-audit", label: "Audit Logs", icon: "fa-clipboard-list", href: "/admin-audit.html" },
    { id: "admin-settings", label: "Settings", icon: "fa-gear", href: "/admin-settings.html" },
  ]},
  { group: "Account", items: [
    { id: "profile", label: "Profile Settings", icon: "fa-user-gear", href: "/profile.html" },
  ]},
];

function cisRenderShell(activeId, pageTitle, pageSubtitle) {
  if (!document.querySelector("link[rel*='icon']")) {
    document.head.insertAdjacentHTML("beforeend", '<link rel="icon" type="image/png" href="/images/favicon.png">');
  }

  const sidebarGroups = CIS_NAV.map(group => `
    <div class="cis-nav-group">
      <div class="cis-nav-label">${group.group}</div>
      ${group.items.map(item => `
        <a class="cis-nav-item ${item.id === activeId ? "active" : ""}" href="${item.href}">
          <i class="fa-solid ${item.icon}"></i> <span>${item.label}</span>
        </a>`).join("")}
    </div>
  `).join("");

  document.body.insertAdjacentHTML("afterbegin", `
    <div class="cis-app">
      <aside class="cis-sidebar" id="cisSidebar">
        <button class="cis-sidebar-collapse-btn" id="cisSidebarToggle">
          <i class="fa-solid fa-chevron-left"></i>
        </button>
        <div class="cis-brand" style="padding-left: 0; padding-right: 0; padding-top: 10px;">
          <img class="cis-logo-full" src="/images/Cactus%20icon%20Approved-06.png" alt="Cactus Intelligence Suite" style="max-height: 72px; width: auto; max-width: 100%; object-fit: contain;">
          <img class="cis-logo-icon" src="/images/favicon.png" alt="CIS" style="max-height: 36px; width: auto; max-width: 100%; object-fit: contain; display: none;">
        </div>
        <nav style="display:flex;flex-direction:column;gap:18px;overflow-y:auto;margin-top:10px;">
          ${sidebarGroups}
        </nav>
        <div class="cis-sidebar-footer" id="cisUserFooter">Loading…</div>
      </aside>
      <div class="cis-main">
        <header class="cis-topbar">
          <div style="display:flex;align-items:center;gap:14px;">
            <button class="cis-btn cis-btn-ghost cis-btn-sm cis-mobile-toggle" id="cisMobileToggle"><i class="fa-solid fa-bars"></i></button>
            <div>
              <div class="cis-page-title">${pageTitle}</div>
              ${pageSubtitle ? `<div class="cis-page-subtitle">${pageSubtitle}</div>` : ""}
            </div>
          </div>
          <div class="cis-topbar-actions" id="cisTopbarActions">
            <button class="cis-btn cis-btn-ghost cis-btn-sm" id="cisLogoutBtn"><i class="fa-solid fa-right-from-bracket"></i> Log out</button>
          </div>
        </header>
        <main class="cis-content" id="cisContent"></main>
      </div>
    </div>
    <div class="cis-toast-container" id="cisToasts"></div>
  `);

  document.addEventListener("DOMContentLoaded", () => {
    const main = document.getElementById("cisContent");
    const app = document.querySelector(".cis-app");
    const toasts = document.getElementById("cisToasts");
    Array.from(document.body.childNodes).forEach(node => {
      if (node !== app && node !== toasts && node.nodeName !== 'SCRIPT') {
        main.appendChild(node);
      }
    });
  });

  document.getElementById("cisLogoutBtn").addEventListener("click", () => {
    CISApi.clearTokens();
    window.location.href = "/login.html";
  });

  const toggle = document.getElementById("cisMobileToggle");
  if (toggle) {
    toggle.addEventListener("click", () => {
      document.getElementById("cisSidebar").classList.toggle("open");
    });
  }

  const collapseToggle = document.getElementById("cisSidebarToggle");
  if (collapseToggle) {
    collapseToggle.addEventListener("click", () => {
      const app = document.querySelector(".cis-app");
      app.classList.toggle("collapsed");
      const icon = collapseToggle.querySelector("i");
      if (app.classList.contains("collapsed")) {
        icon.className = "fa-solid fa-chevron-right";
        localStorage.setItem("cis-sidebar-collapsed", "true");
      } else {
        icon.className = "fa-solid fa-chevron-left";
        localStorage.setItem("cis-sidebar-collapsed", "false");
      }
    });

    if (localStorage.getItem("cis-sidebar-collapsed") === "true") {
      document.querySelector(".cis-app").classList.add("collapsed");
      collapseToggle.querySelector("i").className = "fa-solid fa-chevron-right";
    }
  }

  cisLoadUserFooter();
}

async function cisLoadUserFooter() {
  try {
    const me = await CISApi.get("/api/auth/me");
    document.getElementById("cisUserFooter").innerHTML =
      `<img src="/images/powered-by-logo.png" alt="Powered By" style="max-height: 48px; display: block; margin: 0 auto; filter: brightness(0) invert(1); opacity: 0.7;">`;
    if (me.role !== "admin") {
      document.querySelectorAll('a[href*="admin-"]').forEach(el => el.style.display = "none");
    }
    return me;
  } catch (e) {
    document.getElementById("cisUserFooter").innerHTML =
      `<img src="/images/powered-by-logo.png" alt="Powered By" style="max-height: 48px; display: block; margin: 0 auto; filter: brightness(0) invert(1); opacity: 0.4;">`;
  }
}

function cisToast(message, type) {
  const container = document.getElementById("cisToasts");
  if (!container) return;
  const el = document.createElement("div");
  el.className = "cis-toast" + (type === "error" ? " error" : "");
  el.innerText = message;
  container.appendChild(el);
  setTimeout(() => el.remove(), 4500);
}

function cisRequireAuth() {
  if (!CISApi.isAuthenticated()) {
    window.location.href = "/login.html";
  }
}

function cisGradeClass(grade) {
  if (!grade) return "grade-f";
  const g = grade[0].toLowerCase();
  if (g === "a") return "grade-a";
  if (g === "b") return "grade-b";
  if (g === "c") return "grade-c";
  return "grade-f";
}

function cisFmtDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString() + " " + d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function cisEscape(str) {
  const div = document.createElement("div");
  div.innerText = str == null ? "" : str;
  return div.innerHTML;
}

function cisQueryParam(name) {
  return new URLSearchParams(window.location.search).get(name);
}
