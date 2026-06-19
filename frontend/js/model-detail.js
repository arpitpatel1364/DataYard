const modelId = cisQueryParam("id");

document.querySelectorAll("[data-run]").forEach(btn => {
  btn.addEventListener("click", () => runBenchmark(btn.dataset.run, btn));
});

async function init() {
  if (!modelId) return cisToast("No model id provided", "error");
  try {
    const models = await CISApi.get("/api/models");
    const model = models.find(m => m.id === modelId);
    document.getElementById("modelTitle").innerText = model ? `${model.name} (${model.framework})` : "Model";
  } catch (e) {}
  await refreshRuns();
}

async function runBenchmark(type, btn) {
  const original = btn.innerHTML;
  btn.disabled = true; btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Running…`;
  try {
    const res = await CISApi.post(`/api/models/${modelId}/benchmark/${type}`);
    renderResult(type, res.results);
    await refreshRuns();
  } catch (e) {
    cisToast(e.message || `${type} benchmark failed`, "error");
  } finally {
    btn.disabled = false; btn.innerHTML = original;
  }
}

function renderResult(type, results) {
  const card = document.getElementById("runResultCard");
  card.style.display = "block";

  if (results.available === false) {
    card.innerHTML = `<div class="cis-empty-state"><i class="fa-solid fa-circle-info"></i>
      <strong>${type} unavailable:</strong> ${cisEscape(results.reason || "not supported in this environment")}</div>`;
    return;
  }

  card.innerHTML = `
    <div class="cis-card-title" style="margin-bottom:14px;">Latest ${capitalize(type)} Result</div>
    <pre style="white-space:pre-wrap;font-family:var(--cis-font-mono);font-size:12.5px;background:rgba(0,0,0,0.25);padding:14px;border-radius:10px;overflow-x:auto;">${cisEscape(JSON.stringify(results, null, 2))}</pre>
  `;
}
function capitalize(s) { return s.charAt(0).toUpperCase() + s.slice(1).replace("-", " "); }

async function refreshRuns() {
  try {
    const runs = await CISApi.get(`/api/models/${modelId}/runs`);
    const container = document.getElementById("runsTable");
    if (!runs.length) {
      container.innerHTML = `<div class="cis-empty-state"><i class="fa-solid fa-chart-line"></i>No benchmark runs yet.</div>`;
      return;
    }
    container.innerHTML = `
      <table class="cis-table">
        <thead><tr><th>Type</th><th>Status</th><th>Started</th><th></th></tr></thead>
        <tbody>
          ${runs.map(r => `
            <tr>
              <td><span class="cis-badge cis-badge-neutral">${r.run_type}</span></td>
              <td><span class="cis-badge cis-badge-${r.status === "completed" ? "success" : "danger"}">${r.status}</span></td>
              <td>${cisFmtDate(r.started_at)}</td>
              <td><button class="cis-btn cis-btn-ghost cis-btn-sm" data-view="${r.id}">View</button></td>
            </tr>
          `).join("")}
        </tbody>
      </table>`;
    container.querySelectorAll("[data-view]").forEach(btn => {
      btn.addEventListener("click", () => {
        const run = runs.find(r => r.id === btn.dataset.view);
        renderResult(run.run_type, run.results);
      });
    });
  } catch (e) { cisToast(e.message || "Failed to load runs", "error"); }
}

init();
