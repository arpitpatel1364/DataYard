let datasetId = cisQueryParam("id");
let dataset = null;
let versions = [];
let latestVersion = null;
let fullReport = null;

document.querySelectorAll(".cis-tab").forEach(tab => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".cis-tab").forEach(t => t.classList.remove("active"));
    tab.classList.add("active");
    ["overview", "classes", "quality", "recommendations", "monitoring", "reports", "history"].forEach(id => {
      document.getElementById("panel" + capitalize(id)).style.display = (id === tab.dataset.tab) ? "block" : "none";
    });
    history.replaceState(null, null, "#" + tab.dataset.tab);
  });
});

window.addEventListener("hashchange", () => {
  const hash = window.location.hash.substring(1);
  if (hash) {
    const tab = document.querySelector(`.cis-tab[data-tab="${hash}"]`);
    if (tab && !tab.classList.contains("active")) tab.click();
  }
});

function capitalize(s) { return s.charAt(0).toUpperCase() + s.slice(1); }

async function loadAll() {
  if (!datasetId) {
    try {
      const allDs = await CISApi.get("/api/datasets");
      if (!allDs || !allDs.length) {
        document.getElementById("datasetName").innerText = "No datasets available";
        cisToast("Please import a dataset first", "info");
        return;
      }
      allDs.sort((a,b) => b.id - a.id);
      datasetId = allDs[0].id;
    } catch(e) {
      document.getElementById("datasetName").innerText = "Error loading datasets";
      cisToast("Failed to fetch datasets", "error");
      return;
    }
  }

  // Load base dataset
  try {
    dataset = await CISApi.get(`/api/datasets/${datasetId}`);
  } catch (e) {
    document.getElementById("datasetName").innerText = "Dataset not found";
    cisToast(e.message || "Failed to load dataset", "error");
    return;
  }

  // Load versions
  try {
    versions = await CISApi.get(`/api/datasets/${datasetId}/versions`);
    latestVersion = versions.length ? versions[versions.length - 1] : null;
  } catch (e) {
    versions = [];
    latestVersion = null;
    console.error("Failed to load versions:", e);
    // Don't completely fail, maybe the user can still trigger a scan
  }

  // Load full report if we have a version
  if (latestVersion) {
    try {
      const fr = await CISApi.get(`/api/datasets/versions/${latestVersion.id}/full-report`);
      fullReport = fr.full_report;
    } catch (e) {
      fullReport = null;
      console.error("Failed to load full report:", e);
    }
  }

  // Render everything with whatever data we successfully fetched
  try {
    renderHeader();
    renderOverview();
    renderClasses();
    renderQuality();
    renderRecommendations();
    renderMonitoring();
    renderReports();
    renderHistory();

    const hash = window.location.hash.substring(1);
    if (hash) {
      const tab = document.querySelector(`.cis-tab[data-tab="${hash}"]`);
      if (tab) tab.click();
    }
  } catch (e) {
    console.error("Render error:", e);
    cisToast("Error rendering page content", "error");
  }
}

function renderHeader() {
  document.querySelector(".cis-page-title").innerText = dataset.name;
  document.getElementById("datasetName").innerText = dataset.name;
  document.getElementById("datasetMeta").innerText =
    `${dataset.source_type.toUpperCase()} · ${dataset.num_classes} classes · ${dataset.root_path || ""}`;

  const gradeBox = document.getElementById("gradeBox");
  if (latestVersion) {
    gradeBox.innerText = latestVersion.health_grade;
    gradeBox.className = "cis-grade " + cisGradeClass(latestVersion.health_grade);
  } else {
    gradeBox.innerText = "—";
  }
}

document.getElementById("rescanBtn").addEventListener("click", async () => {
  const scanMode = document.getElementById("rescanModeSelect").value;
  const btn = document.getElementById("rescanBtn");
  btn.disabled = true; btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Scanning…`;
  try {
    await CISApi.post("/api/datasets/scan", {
      dataset_id: datasetId, selected_classes: dataset.class_names || [], scan_mode: scanMode,
    });
    cisToast("Scan complete");
    location.reload();
  } catch (e) {
    cisToast(e.message || "Scan failed", "error");
  } finally {
    btn.disabled = false; btn.innerHTML = `<i class="fa-solid fa-rotate"></i> Re-scan`;
  }
});

// ---------------------------------------------------------------------------
// OVERVIEW
// ---------------------------------------------------------------------------
function renderOverview() {
  const panel = document.getElementById("panelOverview");
  if (!latestVersion) {
    panel.innerHTML = `<div class="cis-empty-state"><i class="fa-solid fa-heart-pulse"></i>No scan has run yet for this dataset.</div>`;
    return;
  }
  const scoreRows = [
    ["Integrity", latestVersion.integrity_score],
    ["Annotation Quality", latestVersion.annotation_score],
    ["Balance", latestVersion.balance_score],
    ["Image Quality", latestVersion.image_quality_score],
    ["Diversity", latestVersion.diversity_score],
    ["Leakage", latestVersion.leakage_score],
  ];

  panel.innerHTML = `
    <div class="cis-bento" style="grid-template-columns:repeat(3,1fr);gap:16px;">
      <div class="cis-card cis-span-1" style="background:rgba(255,255,255,0.02);">
        <div class="cis-card-title">Train Images</div>
        <div class="cis-stat-value" style="font-size:24px;">${latestVersion.train_images}</div>
      </div>
      <div class="cis-card cis-span-1" style="background:rgba(255,255,255,0.02);">
        <div class="cis-card-title">Val Images</div>
        <div class="cis-stat-value" style="font-size:24px;">${latestVersion.val_images}</div>
      </div>
      <div class="cis-card cis-span-1" style="background:rgba(255,255,255,0.02);">
        <div class="cis-card-title">Test Images</div>
        <div class="cis-stat-value" style="font-size:24px;">${latestVersion.test_images}</div>
      </div>
    </div>

    <div style="margin-top:24px;">
      <div class="cis-card-title" style="margin-bottom:14px;">Health Score Breakdown</div>
      ${scoreRows.map(([label, score]) => `
        <div style="margin-bottom:12px;">
          <div style="display:flex;justify-content:space-between;font-size:13px;margin-bottom:5px;">
            <span>${label}</span><strong>${score}</strong>
          </div>
          <div class="cis-progress"><div style="width:${score}%;"></div></div>
        </div>
      `).join("")}
    </div>

    <div style="margin-top:28px; height: 250px;">
      <div class="cis-card-title" style="margin-bottom:14px;">Health Score Timeline (Versioning)</div>
      <canvas id="timelineChart"></canvas>
    </div>
  `;

  new Chart(document.getElementById("timelineChart"), {
    type: "bar",
    data: {
      labels: versions.map(v => "v" + v.version_number),
      datasets: [{
        label: "Health Score", data: versions.map(v => v.health_score),
        backgroundColor: "rgba(114,171,82,0.8)", borderRadius: 4, maxBarThickness: 50,
      }],
    },
    options: {
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        y: { min: 0, max: 100, ticks: { color: "#a7b5a3" }, grid: { color: "rgba(255,255,255,0.05)" } },
        x: { ticks: { color: "#a7b5a3" }, grid: { display: false } },
      },
    },
  });
}

// ---------------------------------------------------------------------------
// CLASS INTELLIGENCE
// ---------------------------------------------------------------------------
function renderClasses() {
  const panel = document.getElementById("panelClasses");
  const ci = fullReport && fullReport.class_intelligence;
  if (!ci || !Object.keys(ci.distribution || {}).length) {
    panel.innerHTML = `<div class="cis-empty-state"><i class="fa-solid fa-tags"></i>No class intelligence data available yet.</div>`;
    return;
  }
  const classes = Object.keys(ci.distribution);
  panel.innerHTML = `
    <table class="cis-table">
      <thead><tr><th>Class</th><th>Instances</th><th>Images</th><th>Density/Image</th><th>Frequency</th><th>Sufficiency</th><th>Risk</th></tr></thead>
      <tbody>
        ${classes.map(cls => {
          const dist = ci.distribution[cls];
          const ready = (ci.training_readiness || {})[cls] || {};
          const riskColor = ready.risk === "low" ? "success" : ready.risk === "medium" ? "warning" : "danger";
          return `<tr>
            <td><strong>${cisEscape(cls)}</strong></td>
            <td>${dist.total_instances}</td>
            <td>${dist.image_count}</td>
            <td>${dist.density_per_image}</td>
            <td>${dist.frequency_pct}%</td>
            <td><span class="cis-badge cis-badge-neutral">${ready.sufficiency || "—"}</span></td>
            <td><span class="cis-badge cis-badge-${riskColor}">${ready.risk || "—"}</span></td>
          </tr>`;
        }).join("")}
      </tbody>
    </table>
    ${(ci.training_readiness && ci.training_readiness._overall && ci.training_readiness._overall.imbalanced) ? `
      <div class="cis-badge cis-badge-danger" style="margin-top:14px;">
        <i class="fa-solid fa-triangle-exclamation"></i> Class imbalance ratio: ${ci.training_readiness._overall.class_imbalance_ratio}x
      </div>` : ""}
  `;
}

// ---------------------------------------------------------------------------
// QUALITY / DUPLICATES / LEAKAGE
// ---------------------------------------------------------------------------
function renderQuality() {
  const panel = document.getElementById("panelQuality");
  if (!fullReport) { panel.innerHTML = `<div class="cis-empty-state">No data.</div>`; return; }
  const q = fullReport.quality || {};
  const dup = fullReport.duplicates || {};
  const leak = fullReport.leakage || {};

  panel.innerHTML = `
    <div class="cis-bento" style="grid-template-columns:repeat(4,1fr);gap:14px;">
      <div class="cis-card" style="background:rgba(255,255,255,0.02);"><div class="cis-card-title">Corrupted Files</div><div class="cis-stat-value" style="font-size:22px;">${q.corrupted_count ?? "—"}</div></div>
      <div class="cis-card" style="background:rgba(255,255,255,0.02);"><div class="cis-card-title">Blurry Images</div><div class="cis-stat-value" style="font-size:22px;">${q.blurry_pct ?? "—"}%</div></div>
      <div class="cis-card" style="background:rgba(255,255,255,0.02);"><div class="cis-card-title">Dark / Overexposed</div><div class="cis-stat-value" style="font-size:22px;">${(q.dark_pct||0) + (q.overexposed_pct||0)}%</div></div>
      <div class="cis-card" style="background:rgba(255,255,255,0.02);"><div class="cis-card-title">Resolution Variants</div><div class="cis-stat-value" style="font-size:22px;">${q.resolution_diversity_count ?? "—"}</div></div>
    </div>

    <div style="margin-top:24px;" class="cis-card-title">Duplicate Detection</div>
    <p>Exact (SHA256): <strong>${dup.exact ? dup.exact.duplicate_groups + " groups / " + dup.exact.duplicate_files + " files" : "Run a Deep scan to compute"}</strong></p>
    <p>Near-duplicate (pHash): <strong>${dup.near_duplicate && dup.near_duplicate.available ? dup.near_duplicate.near_duplicate_groups + " groups" : (dup.near_duplicate ? dup.near_duplicate.reason : "Run a Deep scan to compute")}</strong></p>
    <p>Semantic similarity (CLIP): <strong>${dup.semantic ? (dup.semantic.available ? "available" : dup.semantic.reason) : "Run a Deep scan to compute"}</strong></p>

    <div style="margin-top:18px;" class="cis-card-title">Train/Val/Test Leakage</div>
    <p>Leaked images detected: <strong>${leak.total_leaked_images ?? "Run a Deep scan to compute"}</strong></p>
    ${leak.total_leaked_images > 0 ? `
      <div class="cis-badge cis-badge-danger"><i class="fa-solid fa-triangle-exclamation"></i>
        Train↔Val: ${leak.train_val_leaks}, Train↔Test: ${leak.train_test_leaks}, Val↔Test: ${leak.val_test_leaks}
      </div>` : ""}
  `;
}

// ---------------------------------------------------------------------------
// RECOMMENDATIONS
// ---------------------------------------------------------------------------
function renderRecommendations() {
  const panel = document.getElementById("panelRecommendations");
  const recs = latestVersion ? (latestVersion.recommendations || []) : [];
  if (!recs.length) { panel.innerHTML = `<div class="cis-empty-state"><i class="fa-solid fa-lightbulb"></i>No recommendations yet.</div>`; return; }
  const sevColor = { critical: "danger", high: "danger", medium: "warning", low: "info", info: "neutral" };
  panel.innerHTML = recs.map(r => `
    <div style="display:flex;gap:12px;padding:12px 0;border-bottom:1px solid rgba(255,255,255,0.05);">
      <span class="cis-badge cis-badge-${sevColor[r.severity] || "neutral"}" style="text-transform:uppercase;flex-shrink:0;">${r.severity}</span>
      <div>${cisEscape(r.message)}</div>
    </div>
  `).join("");
}

// ---------------------------------------------------------------------------
// MONITORING
// ---------------------------------------------------------------------------
function renderMonitoring() {
  const panel = document.getElementById("panelMonitoring");
  panel.innerHTML = `
    <div class="cis-field" style="max-width:420px;">
      <label class="cis-label">
        <input type="checkbox" id="monitoringToggle" ${dataset.monitoring_enabled ? "checked" : ""}> Enable continuous monitoring
      </label>
    </div>
    <div class="cis-field" style="max-width:420px;">
      <label class="cis-label">Re-scan interval (minutes)</label>
      <input class="cis-input" type="number" min="1" id="monitoringInterval" value="${dataset.scan_every_minutes || 30}">
    </div>
    <button class="cis-btn cis-btn-primary" id="saveMonitoringBtn"><i class="fa-solid fa-floppy-disk"></i> Save monitoring settings</button>
    <p style="margin-top:14px;color:var(--cis-text-faint);font-size:12.5px;">
      Last scanned: ${cisFmtDate(dataset.last_scanned_at)}. Monitoring runs entirely in-process (no external queue required)
      and automatically creates a new dataset version on each tick.
    </p>
  `;
  document.getElementById("saveMonitoringBtn").addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    try {
      await CISApi.post("/api/datasets/monitoring/configure", {
        dataset_id: datasetId,
        enabled: document.getElementById("monitoringToggle").checked,
        scan_every_minutes: parseInt(document.getElementById("monitoringInterval").value, 10) || 30,
      });
      cisToast("Monitoring settings saved");
    } catch (err) { 
      cisToast(err.message || "Failed to save", "error"); 
    } finally {
      btn.disabled = false;
    }
  });
}

// ---------------------------------------------------------------------------
// REPORTS
// ---------------------------------------------------------------------------
function renderReports() {
  const panel = document.getElementById("panelReports");
  if (!latestVersion) { panel.innerHTML = `<div class="cis-empty-state">Run a scan first to generate reports.</div>`; return; }
  panel.innerHTML = `
    <p>Generate a downloadable report for the latest scan (v${latestVersion.version_number}).</p>
    <div style="display:flex;gap:10px;flex-wrap:wrap;">
      <button class="cis-btn cis-btn-primary" data-fmt="pdf"><i class="fa-solid fa-file-pdf"></i> PDF</button>
      <button class="cis-btn cis-btn-ghost" data-fmt="xlsx"><i class="fa-solid fa-file-excel"></i> Excel</button>
      <button class="cis-btn cis-btn-ghost" data-fmt="csv"><i class="fa-solid fa-file-csv"></i> CSV</button>
      <button class="cis-btn cis-btn-ghost" data-fmt="json"><i class="fa-solid fa-file-code"></i> JSON</button>
    </div>
    <div id="reportResultArea" style="margin-top:16px;"></div>
  `;
  panel.querySelectorAll("[data-fmt]").forEach(btn => {
    btn.addEventListener("click", async () => {
      try {
        const res = await CISApi.post(`/api/reports/generate/${latestVersion.id}?file_format=${btn.dataset.fmt}`);
        document.getElementById("reportResultArea").innerHTML =
          `<a class="cis-btn cis-btn-primary" href="${res.download_url}" target="_blank"><i class="fa-solid fa-download"></i> Download ${btn.dataset.fmt.toUpperCase()} report</a>`;
      } catch (e) { cisToast(e.message || "Report generation failed", "error"); }
    });
  });
}

// ---------------------------------------------------------------------------
// HISTORY
// ---------------------------------------------------------------------------
async function renderHistory() {
  const panel = document.getElementById("panelHistory");
  try {
    const history = await CISApi.get(`/api/datasets/${datasetId}/history`);
    if (!history.length) { panel.innerHTML = `<div class="cis-empty-state">No history yet.</div>`; return; }
    panel.innerHTML = `
      <table class="cis-table">
        <thead><tr><th>Event</th><th>Message</th><th>When</th></tr></thead>
        <tbody>
          ${history.map(h => `<tr><td><span class="cis-badge cis-badge-neutral">${h.event_type}</span></td><td>${cisEscape(h.message)}</td><td>${cisFmtDate(h.created_at)}</td></tr>`).join("")}
        </tbody>
      </table>`;
  } catch (e) {
    panel.innerHTML = `<div class="cis-empty-state">Failed to load history.</div>`;
  }
}

loadAll();
