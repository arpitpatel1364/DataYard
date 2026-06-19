(async function () {
  try {
    const datasets = await CISApi.get("/api/datasets");
    document.getElementById("statDatasets").innerText = datasets.length;

    let monitoring = [];
    try { monitoring = await CISApi.get("/api/datasets/monitoring/live"); } catch (e) {}
    document.getElementById("statMonitoring").innerText = monitoring.length;

    let models = [];
    try { models = await CISApi.get("/api/models"); } catch (e) {}
    document.getElementById("statModels").innerText = models.length;

    // Pull latest version per dataset (capped) to compute avg health + distribution
    const sample = datasets.slice(0, 25);
    const scores = [];
    const rows = [];
    for (const ds of sample) {
      let latest = null;
      try {
        const versions = await CISApi.get(`/api/datasets/${ds.id}/versions`);
        latest = versions.length ? versions[versions.length - 1] : null;
      } catch (e) {}
      if (latest) scores.push(latest.health_score);
      rows.push({ ds, latest });
    }

    document.getElementById("statHealth").innerText =
      scores.length ? (scores.reduce((a, b) => a + b, 0) / scores.length).toFixed(1) : "—";

    renderHealthChart(scores);
    renderRecentDatasetsTable(rows);
  } catch (e) {
    cisToast(e.message || "Failed to load dashboard", "error");
  }
})();

function renderHealthChart(scores) {
  const buckets = { "A+/A (90-100)": 0, "B (80-89)": 0, "C (70-79)": 0, "D (60-69)": 0, "F (0-59)": 0 };
  scores.forEach(s => {
    if (s >= 90) buckets["A+/A (90-100)"]++;
    else if (s >= 80) buckets["B (80-89)"]++;
    else if (s >= 70) buckets["C (70-79)"]++;
    else if (s >= 60) buckets["D (60-69)"]++;
    else buckets["F (0-59)"]++;
  });
  const ctx = document.getElementById("healthChart");
  new Chart(ctx, {
    type: "bar",
    data: {
      labels: Object.keys(buckets),
      datasets: [{ label: "Datasets", data: Object.values(buckets), backgroundColor: "#72ab52", borderRadius: 6 }],
    },
    options: {
      plugins: { legend: { display: false } },
      scales: {
        y: { beginAtZero: true, ticks: { color: "#a7b5a3" }, grid: { color: "rgba(255,255,255,0.05)" } },
        x: { ticks: { color: "#a7b5a3" }, grid: { display: false } },
      },
    },
  });
}

function renderRecentDatasetsTable(rows) {
  const container = document.getElementById("recentDatasetsTable");
  if (!rows.length) {
    container.innerHTML = `<div class="cis-empty-state"><i class="fa-solid fa-database"></i><div>No datasets yet</div>
      <a class="cis-btn cis-btn-primary cis-btn-sm" href="/import.html">Import your first dataset</a></div>`;
    return;
  }
  container.innerHTML = `
    <table class="cis-table">
      <thead><tr><th>Name</th><th>Source</th><th>Classes</th><th>Health</th><th>Status</th><th>Last Scanned</th><th></th></tr></thead>
      <tbody>
        ${rows.map(({ ds, latest }) => `
          <tr>
            <td><strong>${cisEscape(ds.name)}</strong></td>
            <td><span class="cis-badge cis-badge-neutral">${ds.source_type}</span></td>
            <td>${ds.num_classes}</td>
            <td>${latest ? `<span class="cis-badge cis-badge-${latest.health_score >= 80 ? "success" : latest.health_score >= 60 ? "warning" : "danger"}">${latest.health_score} · ${latest.health_grade}</span>` : "Not scanned"}</td>
            <td><span class="cis-badge cis-badge-info">${ds.status}</span></td>
            <td>${cisFmtDate(ds.last_scanned_at)}</td>
            <td><a class="cis-btn cis-btn-ghost cis-btn-sm" href="/dataset-detail.html?id=${ds.id}">Open</a></td>
          </tr>
        `).join("")}
      </tbody>
    </table>`;
}
