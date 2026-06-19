let currentDetection = null;     // { dataset_root, data_yaml_path, classes, ... }
let currentResolvedPath = null;  // path to pass to /register
let currentRegisteredDatasetId = null; // set when roboflow import already registered the dataset

document.querySelectorAll(".cis-tab").forEach(tab => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".cis-tab").forEach(t => t.classList.remove("active"));
    tab.classList.add("active");
    document.getElementById("tabPanelLocal").style.display = tab.dataset.tab === "local" ? "block" : "none";
    document.getElementById("tabPanelRoboflow").style.display = tab.dataset.tab === "roboflow" ? "block" : "none";
  });
});

document.getElementById("detectLocalBtn").addEventListener("click", async () => {
  const path = document.getElementById("localPathInput").value.trim();
  if (!path) return cisToast("Enter a data.yaml or folder path", "error");
  try {
    const result = await CISApi.post("/api/datasets/detect", { path });
    currentDetection = result;
    currentResolvedPath = path;
    currentRegisteredDatasetId = null;
    renderDetectionSummary(result);
    renderClassChecklist(result.class_names || []);
  } catch (e) {
    cisToast(e.message || "Detection failed", "error");
  }
});

document.getElementById("dropZone").addEventListener("click", () => document.getElementById("yamlFileInput").click());

document.getElementById("yamlFileInput").addEventListener("change", (e) => {
  const file = e.target.files[0];
  if (file) {
    cisToast(`Selected ${file.name}`);
    document.getElementById("dropZone").innerHTML = `<i class="fa-solid fa-file-code" style="font-size:22px;margin-bottom:8px;display:block;color:var(--cis-primary-light);"></i> <strong>Selected:</strong> ${file.name}`;
  }
});

["dragover", "dragleave", "drop"].forEach(evt => {
  document.getElementById("dropZone").addEventListener(evt, (e) => e.preventDefault());
});
document.getElementById("dropZone").addEventListener("drop", (e) => {
  const file = e.dataTransfer.files[0];
  if (file) {
    document.getElementById("yamlFileInput").files = e.dataTransfer.files;
    cisToast(`Selected ${file.name}`);
    document.getElementById("dropZone").innerHTML = `<i class="fa-solid fa-file-code" style="font-size:22px;margin-bottom:8px;display:block;color:var(--cis-primary-light);"></i> <strong>Selected:</strong> ${file.name}`;
  }
});

document.getElementById("uploadYamlBtn").addEventListener("click", async () => {
  const fileInput = document.getElementById("yamlFileInput");
  const root = document.getElementById("dropRootInput").value.trim();
  if (!fileInput.files.length) return cisToast("Choose a data.yaml file first", "error");
  if (!root) return cisToast("Provide the dataset root folder on the server", "error");

  const fd = new FormData();
  fd.append("file", fileInput.files[0]);
  fd.append("dataset_root", root);
  try {
    const result = await CISApi.post("/api/datasets/upload-yaml", fd);
    currentDetection = result;
    currentResolvedPath = result.data_yaml_path;
    currentRegisteredDatasetId = null;
    renderDetectionSummary(result);
    renderClassChecklist(result.class_names || []);
  } catch (e) {
    cisToast(e.message || "Upload failed", "error");
  }
});

document.getElementById("importRoboflowBtn").addEventListener("click", async () => {
  const snippet = document.getElementById("rfSnippet").value;
  const apiKeyMatch = snippet.match(/api_key\s*=\s*["']([^"']+)["']/);
  const workspaceMatch = snippet.match(/workspace\s*\(\s*["']([^"']+)["']\s*\)/);
  const projectMatch = snippet.match(/project\s*\(\s*["']([^"']+)["']\s*\)/);
  const versionMatch = snippet.match(/version\s*\(\s*(\d+)\s*\)/);

  if (!apiKeyMatch || !workspaceMatch || !projectMatch || !versionMatch) {
    return cisToast("Could not parse Roboflow snippet. Please ensure it contains api_key, workspace, project, and version.", "error");
  }

  const payload = {
    workspace: workspaceMatch[1],
    project: projectMatch[1],
    version: versionMatch[1],
    api_key: apiKeyMatch[1],
    name: document.getElementById("rfNameInput").value.trim() || null,
  };
  if (!payload.workspace || !payload.project || !payload.version || !payload.api_key) {
    return cisToast("All Roboflow fields are required", "error");
  }
  const btn = document.getElementById("importRoboflowBtn");
  btn.disabled = true; btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Importing…`;
  try {
    const dataset = await CISApi.post("/api/datasets/import-roboflow", payload);
    currentRegisteredDatasetId = dataset.id;
    currentDetection = { dataset_name: dataset.name, classes: dataset.num_classes, class_names: dataset.class_names,
                          train_images: 0, val_images: 0, test_images: 0, warnings: [] };
    renderDetectionSummary(currentDetection);
    renderClassChecklist(dataset.class_names || []);
    cisToast("Roboflow dataset imported — select classes to analyze");
  } catch (e) {
    cisToast(e.message || "Roboflow import failed", "error");
  } finally {
    btn.disabled = false; btn.innerHTML = `<i class="fa-solid fa-cloud-arrow-down"></i> Import from Roboflow`;
  }
});

function renderDetectionSummary(result) {
  const card = document.getElementById("detectionSummaryCard");
  const body = document.getElementById("detectionSummaryBody");
  card.style.display = "block";
  body.innerHTML = `
    <div class="cis-bento" style="grid-template-columns:repeat(4,1fr);gap:14px;">
      <div><div class="cis-card-title">Classes</div><div class="cis-stat-value" style="font-size:24px;">${result.classes}</div></div>
      <div><div class="cis-card-title">Train Images</div><div class="cis-stat-value" style="font-size:24px;">${result.train_images || 0}</div></div>
      <div><div class="cis-card-title">Val Images</div><div class="cis-stat-value" style="font-size:24px;">${result.val_images || 0}</div></div>
      <div><div class="cis-card-title">Test Images</div><div class="cis-stat-value" style="font-size:24px;">${result.test_images || 0}</div></div>
    </div>
    ${(result.warnings || []).length ? `
      <div style="margin-top:14px;">
        ${result.warnings.map(w => `<div class="cis-badge cis-badge-warning" style="margin:3px;display:inline-block;"><i class="fa-solid fa-triangle-exclamation"></i> ${cisEscape(w)}</div>`).join("")}
      </div>` : ""}
  `;
}

function renderClassChecklist(classNames) {
  const card = document.getElementById("classSelectionCard");
  const list = document.getElementById("classChecklist");
  card.style.display = "block";
  if (!classNames.length) {
    list.innerHTML = `<div class="cis-empty-state"><i class="fa-solid fa-tags"></i>No classes detected — you can still run a structural scan.</div>`;
    return;
  }
  list.innerHTML = classNames.map((c, i) => `
    <label class="cis-checkbox-row">
      <input type="checkbox" class="class-checkbox" value="${cisEscape(c)}" checked>
      <span>${cisEscape(c)}</span>
    </label>
  `).join("");
}

document.getElementById("selectAllBtn").addEventListener("click", () => {
  document.querySelectorAll(".class-checkbox").forEach(cb => cb.checked = true);
});
document.getElementById("selectNoneBtn").addEventListener("click", () => {
  document.querySelectorAll(".class-checkbox").forEach(cb => cb.checked = false);
});

document.getElementById("registerAndScanBtn").addEventListener("click", async () => {
  const selectedClasses = Array.from(document.querySelectorAll(".class-checkbox:checked")).map(cb => cb.value);
  const scanMode = document.getElementById("scanModeSelect").value;
  const btn = document.getElementById("registerAndScanBtn");
  btn.disabled = true; btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Running ${scanMode} scan…`;

  try {
    let datasetId = currentRegisteredDatasetId;
    if (!datasetId) {
      const name = document.getElementById("localNameInput").value.trim() || null;
      const dataset = await CISApi.post("/api/datasets/register", { path: currentResolvedPath, name });
      datasetId = dataset.id;
    }
    const version = await CISApi.post("/api/datasets/scan", {
      dataset_id: datasetId, selected_classes: selectedClasses, scan_mode: scanMode,
    });
    cisToast(`Scan complete — Health Score ${version.health_score} (${version.health_grade})`);
    window.location.href = `/dataset-detail.html?id=${datasetId}`;
  } catch (e) {
    cisToast(e.message || "Scan failed", "error");
    btn.disabled = false; btn.innerHTML = `<i class="fa-solid fa-play"></i> Register & Run Analysis`;
  }
});
