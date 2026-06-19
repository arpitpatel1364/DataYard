// ─────────────────────────────────────────────────────────────────────────────
// STATE
// ─────────────────────────────────────────────────────────────────────────────
let currentOperationId = null;
let pollInterval = null;

/** @type {Array<{label: string, path: string}>} */
let selectedDatasets = [];

// ─────────────────────────────────────────────────────────────────────────────
// CHIP-BASED DATASET SELECTOR
// ─────────────────────────────────────────────────────────────────────────────

function addDataset(path, label) {
  path = path.trim();
  if (!path) return;
  label = label || path.split("/").filter(Boolean).pop() || path;

  // Deduplicate by path
  if (selectedDatasets.some(d => d.path === path)) {
    cisToast("Dataset already added", "warning");
    return;
  }

  selectedDatasets.push({ path, label });
  renderChips();
}

function removeDataset(path) {
  selectedDatasets = selectedDatasets.filter(d => d.path !== path);
  renderChips();
}

function renderChips() {
  const container = document.getElementById("selectedDatasetsChips");
  const placeholder = document.getElementById("chipPlaceholder");

  // Clear existing chips (keep placeholder node)
  Array.from(container.querySelectorAll(".cis-chip")).forEach(el => el.remove());

  if (selectedDatasets.length === 0) {
    placeholder.style.display = "";
    return;
  }

  placeholder.style.display = "none";
  selectedDatasets.forEach(({ path, label }) => {
    const chip = document.createElement("span");
    chip.className = "cis-chip";
    chip.innerHTML = `
      <i class="fa-solid fa-folder" style="font-size:0.7rem;"></i>
      <span title="${path}">${label}</span>
      <button class="cis-chip-remove" data-path="${path}" title="Remove">
        <i class="fa-solid fa-xmark"></i>
      </button>`;
    chip.querySelector(".cis-chip-remove").addEventListener("click", () => removeDataset(path));
    container.appendChild(chip);
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// LOAD REGISTERED DATASETS INTO DROPDOWN
// ─────────────────────────────────────────────────────────────────────────────

async function loadDatasets() {
  try {
    // CISApi.get returns the parsed JSON directly (plain array from /api/datasets)
    const datasets = await CISApi.get("/api/datasets");
    const sel = document.getElementById("registrySelect");
    // Keep the disabled placeholder option at index 0
    while (sel.options.length > 1) sel.remove(1);

    if (!datasets || datasets.length === 0) return;

    datasets.forEach(d => {
      const opt = document.createElement("option");
      // DatasetOut has root_path; no latest_version field in the schema
      opt.value = d.root_path || d.id;
      opt.dataset.label = d.name;
      opt.textContent = `${d.name}  (${d.status})`;
      sel.appendChild(opt);
    });
  } catch (err) {
    cisToast("Failed to load registered datasets", "error");
    console.error("[merger] loadDatasets:", err);
  }
}

document.getElementById("addFromRegistryBtn").addEventListener("click", () => {
  const sel = document.getElementById("registrySelect");
  const opt = sel.options[sel.selectedIndex];
  if (!opt || !opt.value || opt.disabled) {
    cisToast("Please choose a dataset from the dropdown first", "error");
    return;
  }
  addDataset(opt.value, opt.dataset.label || opt.textContent.split("(")[0].trim());
  sel.selectedIndex = 0; // reset
});

document.getElementById("addManualPathBtn").addEventListener("click", () => {
  const input = document.getElementById("manualPathInput");
  addDataset(input.value);
  input.value = "";
});

// Allow Enter key in manual input
document.getElementById("manualPathInput").addEventListener("keydown", e => {
  if (e.key === "Enter") document.getElementById("addManualPathBtn").click();
});

// ─────────────────────────────────────────────────────────────────────────────
// FOLDER BROWSER MODAL
// ─────────────────────────────────────────────────────────────────────────────

let fsBrowsePath = "/"; // current path being displayed in modal

async function openFolderBrowser(startPath) {
  document.getElementById("folderBrowserModal").classList.add("open");
  await fsBrowseTo(startPath || "/");
}

function closeFolderBrowser() {
  document.getElementById("folderBrowserModal").classList.remove("open");
}

async function fsBrowseTo(path) {
  fsBrowsePath = path;
  document.getElementById("fsCurrentPathDisplay").textContent = path;

  const listEl = document.getElementById("fsDirList");
  listEl.innerHTML = '<div class="cis-dir-spinner"><i class="fa-solid fa-spinner fa-spin"></i> Loading…</div>';

  renderFsBreadcrumb(path);

  try {
    const data = await CISApi.get(`/api/fs/browse?path=${encodeURIComponent(path)}`);
    fsBrowsePath = data.current;
    document.getElementById("fsCurrentPathDisplay").textContent = data.current;
    renderFsBreadcrumb(data.current);
    renderFsDirList(data);
  } catch (err) {
    listEl.innerHTML = `<div class="cis-dir-empty"><i class="fa-solid fa-circle-exclamation"></i> ${err.message || "Failed to load directory"}</div>`;
  }
}

function renderFsBreadcrumb(path) {
  const bc = document.getElementById("fsBreadcrumb");
  bc.innerHTML = "";

  const segments = path.split("/").filter(Boolean);
  // Root
  const root = document.createElement("span");
  root.className = "cis-breadcrumb-seg";
  root.dataset.path = "/";
  root.innerHTML = '<i class="fa-solid fa-server" style="margin-right:4px;"></i>Root';
  root.addEventListener("click", () => fsBrowseTo("/"));
  bc.appendChild(root);

  let accumulated = "";
  segments.forEach((seg) => {
    accumulated += "/" + seg;
    const sep = document.createElement("span");
    sep.className = "cis-breadcrumb-sep";
    sep.textContent = " / ";
    bc.appendChild(sep);

    const el = document.createElement("span");
    el.className = "cis-breadcrumb-seg";
    el.textContent = seg;
    const capPath = accumulated;
    el.addEventListener("click", () => fsBrowseTo(capPath));
    bc.appendChild(el);
  });
}

function renderFsDirList(data) {
  const listEl = document.getElementById("fsDirList");
  listEl.innerHTML = "";

  // Up one level
  if (data.parent) {
    const up = document.createElement("div");
    up.className = "cis-dir-item";
    up.innerHTML = `<i class="fa-solid fa-turn-up"></i><span class="cis-dir-item-name">..</span>`;
    up.addEventListener("click", () => fsBrowseTo(data.parent));
    listEl.appendChild(up);
  }

  if (data.dirs.length === 0 && !data.parent) {
    listEl.innerHTML = '<div class="cis-dir-empty">No sub-directories found</div>';
    return;
  }

  data.dirs.forEach(dir => {
    const item = document.createElement("div");
    item.className = "cis-dir-item" + (dir.accessible ? "" : " locked");

    if (dir.accessible) {
      item.innerHTML = `
        <i class="fa-solid fa-folder"></i>
        <span class="cis-dir-item-name">${dir.name}</span>
        <i class="fa-solid fa-chevron-right cis-dir-item-arrow"></i>`;
      item.addEventListener("click", () => fsBrowseTo(dir.path));
    } else {
      item.innerHTML = `
        <i class="fa-solid fa-lock"></i>
        <span class="cis-dir-item-name">${dir.name}</span>
        <small style="color:var(--cis-text-faint)">no access</small>`;
    }
    listEl.appendChild(item);
  });

  if (data.dirs.length === 0) {
    const empty = document.createElement("div");
    empty.className = "cis-dir-empty";
    empty.innerHTML = '<i class="fa-solid fa-folder-open"></i> Empty directory';
    listEl.appendChild(empty);
  }
}

// Wire modal buttons
document.getElementById("openFolderBrowserBtn").addEventListener("click", () => openFolderBrowser(fsBrowsePath));
document.getElementById("closeFolderModal").addEventListener("click", closeFolderBrowser);
document.getElementById("closeFolderModalCancel").addEventListener("click", closeFolderBrowser);

// Close on backdrop click
document.getElementById("folderBrowserModal").addEventListener("click", e => {
  if (e.target === document.getElementById("folderBrowserModal")) closeFolderBrowser();
});

document.getElementById("selectFolderBtn").addEventListener("click", () => {
  addDataset(fsBrowsePath);
  closeFolderBrowser();
});

// ─────────────────────────────────────────────────────────────────────────────
// MERGE OPERATIONS TABLE
// ─────────────────────────────────────────────────────────────────────────────

async function loadOperations() {
  try {
    const ops = await CISApi.get("/api/merger/user/list");
    const tbody = document.getElementById("operationsTableBody");
    tbody.innerHTML = "";
    if (!ops || ops.length === 0) {
      tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:var(--cis-text-faint);padding:20px;">No merge operations yet</td></tr>';
      return;
    }
    ops.forEach(op => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${op.merge_name}</td>
        <td><span class="cis-badge cis-badge-neutral">${op.status}</span></td>
        <td>${op.merged_images_count || '—'}</td>
        <td>${new Date(op.created_at).toLocaleDateString()}</td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error("[merger] loadOperations:", err);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// ANALYZE
// ─────────────────────────────────────────────────────────────────────────────

document.getElementById("startAnalysisBtn").addEventListener("click", async () => {
  const name = document.getElementById("mergeNameInput").value.trim();
  const selectedPaths = selectedDatasets.map(d => d.path);

  if (!name) {
    cisToast("Please enter a merge output name", "error");
    return;
  }
  if (selectedPaths.length < 1) {
    cisToast("Please add at least one source dataset", "error");
    return;
  }

  document.getElementById("startAnalysisBtn").disabled = true;
  document.getElementById("analysisResultCard").style.display = "block";
  document.getElementById("analysisDetails").style.display = "none";
  document.getElementById("analysisStatusIcon").innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';

  try {
    const op = await CISApi.post("/api/merger/analyze", {
      merge_name: name,
      source_datasets: selectedPaths
    });
    currentOperationId = op.id;
    pollAnalysis();
  } catch (err) {
    cisToast(err.message, "error");
    document.getElementById("startAnalysisBtn").disabled = false;
  }
});

function pollAnalysis() {
  if (pollInterval) clearInterval(pollInterval);
  pollInterval = setInterval(async () => {
    try {
      const res = await CISApi.get(`/api/merger/analyze/${currentOperationId}`);

      if (res.status === "pending_merge" && res.analysis) {
        // Analysis complete and results are attached
        clearInterval(pollInterval);
        showAnalysisDetails(res.analysis, res.class_mappings);
      } else if (res.status === "pending_merge" && !res.analysis) {
        // Background task finished status update but hasn't saved analysis yet — keep polling
        return;
      } else if (res.status === "failed") {
        clearInterval(pollInterval);
        cisToast("Analysis failed: " + (res.error || "Unknown error"), "error");
        document.getElementById("analysisStatusIcon").innerHTML = '<i class="fa-solid fa-xmark cis-text-danger"></i>';
        document.getElementById("startAnalysisBtn").disabled = false;
      }
      // statuses: queued_analysis, analyzing — keep polling silently
    } catch (err) {
      console.error("[merger] pollAnalysis:", err);
    }
  }, 2000);
}

function showAnalysisDetails(analysis, savedMappings = {}) {
  if (!analysis) {
    cisToast("Analysis result was empty", "error");
    return;
  }

  document.getElementById("analysisStatusIcon").innerHTML = '<i class="fa-solid fa-check cis-text-success"></i>';
  document.getElementById("analysisDetails").style.display = "block";
  document.getElementById("classMappingCard").style.display = "block";

  // Top-level stats
  document.getElementById("statTotalImages").textContent  = analysis.total_images     ?? 0;
  document.getElementById("statDuplicates").textContent   = analysis.duplicate_count  ?? 0;
  document.getElementById("statBlurry").textContent       = analysis.blurry_images    ?? 0;
  document.getElementById("statCorrupted").textContent    = analysis.corrupted_files  ?? 0;

  // Per-dataset breakdown (from analysis_data)
  const raw = analysis.analysis_data || {};
  const datasets = raw.datasets || {};
  const breakdownEl = document.getElementById("analysisBreakdown");
  if (!breakdownEl) return;

  const entries = Object.entries(datasets);
  if (entries.length === 0) {
    breakdownEl.innerHTML = '';
    return;
  }

  let rows = entries.map(([path, info]) => {
    const name = path.split('/').filter(Boolean).pop() || path;
    if (!info.valid) {
      return `<tr>
        <td title="${path}">${name}</td>
        <td colspan="4" style="color:var(--cis-text-faint)">${(info.errors || []).join(', ') || 'Invalid dataset'}</td>
      </tr>`;
    }
    const imgs   = (info.images   || []).length;
    const anns   = (info.annotations || []).length;
    const dupes  = 0; // duplicates are cross-dataset, shown in total
    const corr   = (info.quality_issues?.corrupted || []).length;
    const blurry = (info.quality_issues?.blurry    || []).length;
    return `<tr>
      <td title="${path}">${name}</td>
      <td>${imgs}</td>
      <td>${anns}</td>
      <td>${corr > 0  ? `<span class="cis-text-danger">${corr}</span>`  : corr}</td>
      <td>${blurry > 0 ? `<span class="cis-text-warning">${blurry}</span>` : blurry}</td>
    </tr>`;
  }).join('');

  breakdownEl.innerHTML = `
    <h4 style="margin: 20px 0 10px; font-size: 13px; color: var(--cis-text-muted); text-transform: uppercase; letter-spacing: 0.04em;">
      Per-Dataset Breakdown
    </h4>
    <table class="cis-table" style="width:100%;">
      <thead><tr>
        <th>Dataset</th><th>Images</th><th>Annotations</th>
        <th><span class="cis-text-danger">Corrupted</span></th>
        <th><span class="cis-text-warning">Blurry</span></th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>`;

  if (analysis.all_classes) {
    initClassMappingUI(analysis.all_classes, savedMappings);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// CLASS MAPPING UI
// ─────────────────────────────────────────────────────────────────────────────
let cmDraggedEl = null;
let currentMappings = {}; // The active UI state

function initClassMappingUI(allClasses, savedMappings) {
  const pool = document.getElementById("cmUnassignedPool");
  const groupsContainer = document.getElementById("cmGroups");
  
  pool.innerHTML = "";
  groupsContainer.innerHTML = "";
  currentMappings = savedMappings || {};

  // Find all classes that are already mapped
  const mappedSources = new Set();
  Object.values(currentMappings).forEach(sources => sources.forEach(s => mappedSources.add(s)));

  // Render unassigned classes
  allClasses.forEach(cls => {
    if (!mappedSources.has(cls)) {
      pool.appendChild(createTag(cls, 'source'));
    }
  });
  if (pool.children.length === 0) {
    pool.innerHTML = '<span style="color:var(--cis-text-faint);font-size:12px;font-style:italic;">All classes mapped</span>';
  }

  // Render existing groups
  Object.entries(currentMappings).forEach(([target, sources]) => {
    const group = createGroup(target);
    const body = group.querySelector('.cm-group-body');
    body.innerHTML = '';
    sources.forEach(s => body.appendChild(createTag(s, 'mapped')));
    groupsContainer.appendChild(group);
  });

  setupDragAndDrop();
  validateMappings();
}

function createTag(text, type) {
  const t = document.createElement("div");
  t.className = `cm-tag ${type}`;
  t.draggable = true;
  t.dataset.val = text;
  t.innerHTML = `<span>${text}</span> <button class="cm-tag-rm" title="Remove">&times;</button>`;
  t.querySelector(".cm-tag-rm").addEventListener("click", () => {
    document.getElementById("cmUnassignedPool").appendChild(createTag(text, 'source'));
    t.remove();
    validateMappings();
  });
  t.addEventListener("dragstart", e => {
    cmDraggedEl = t;
    e.dataTransfer.effectAllowed = "move";
    t.style.opacity = "0.5";
  });
  t.addEventListener("dragend", () => {
    cmDraggedEl = null;
    t.style.opacity = "1";
    document.querySelectorAll(".drag-over").forEach(el => el.classList.remove("drag-over"));
  });
  return t;
}

function createGroup(targetName = "") {
  const g = document.createElement("div");
  g.className = "cm-group";
  g.innerHTML = `
    <div class="cm-group-header">
      <i class="fa-solid fa-object-group" style="color:var(--cis-primary-light);font-size:12px;"></i>
      <input type="text" class="cm-target-input" placeholder="New Unified Class Name..." value="${targetName}">
      <button class="cm-delete-btn" title="Delete Group"><i class="fa-solid fa-trash-can"></i></button>
    </div>
    <div class="cm-group-body" data-zone="group">
      <span class="cm-group-drop-hint">Drop classes here...</span>
    </div>
  `;
  g.querySelector(".cm-delete-btn").addEventListener("click", () => {
    // move all tags back to pool
    const body = g.querySelector(".cm-group-body");
    const pool = document.getElementById("cmUnassignedPool");
    Array.from(body.querySelectorAll(".cm-tag")).forEach(t => {
      pool.appendChild(createTag(t.dataset.val, 'source'));
    });
    g.remove();
    validateMappings();
  });
  g.querySelector(".cm-target-input").addEventListener("input", validateMappings);
  return g;
}

function setupDragAndDrop() {
  document.getElementById("cmAddGroupBtn").addEventListener("click", () => {
    document.getElementById("cmGroups").appendChild(createGroup());
    validateMappings();
  });

  document.getElementById("cmResetBtn").addEventListener("click", () => {
    if (!confirm("Reset all class mappings?")) return;
    const pool = document.getElementById("cmUnassignedPool");
    const tags = document.querySelectorAll("#classMappingCard .cm-tag");
    tags.forEach(t => {
      if (!pool.contains(t)) pool.appendChild(createTag(t.dataset.val, 'source'));
    });
    document.getElementById("cmGroups").innerHTML = "";
    document.querySelectorAll(".cm-tag.mapped").forEach(t => { t.className = "cm-tag source"; });
    validateMappings();
  });

  document.getElementById("cmPreviewBtn").addEventListener("click", () => {
    const p = document.getElementById("cmPreviewPanel");
    p.style.display = p.style.display === "none" ? "block" : "none";
  });

  // Zones
  const makeZone = (zone) => {
    zone.addEventListener("dragover", e => {
      e.preventDefault();
      if (cmDraggedEl) zone.classList.add("drag-over");
    });
    zone.addEventListener("dragleave", () => zone.classList.remove("drag-over"));
    zone.addEventListener("drop", e => {
      e.preventDefault();
      zone.classList.remove("drag-over");
      if (!cmDraggedEl) return;
      
      const isPool = zone.id === "cmUnassignedPool";
      if (isPool) {
        zone.appendChild(createTag(cmDraggedEl.dataset.val, 'source'));
        cmDraggedEl.remove();
      } else {
        const hint = zone.querySelector(".cm-group-drop-hint");
        if (hint) hint.style.display = "none";
        zone.appendChild(createTag(cmDraggedEl.dataset.val, 'mapped'));
        cmDraggedEl.remove();
      }
      validateMappings();
    });
  };

  makeZone(document.getElementById("cmUnassignedPool"));
  // Mutate observer for new groups
  new MutationObserver(mutations => {
    mutations.forEach(m => {
      m.addedNodes.forEach(n => {
        if (n.classList && n.classList.contains("cm-group")) {
          makeZone(n.querySelector(".cm-group-body"));
        }
      });
    });
  }).observe(document.getElementById("cmGroups"), { childList: true });

  // Save functionality
  document.getElementById("cmSaveMappingsBtn").addEventListener("click", async () => {
    const btn = document.getElementById("cmSaveMappingsBtn");
    const map = buildMappingObject(false); // Not quiet
    if (!map) return; // invalid
    
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Saving...';
    try {
      await CISApi.put(`/api/merger/${currentOperationId}/class-mappings`, { class_mappings: map });
      currentMappings = map;
      btn.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> Save Mappings';
      document.getElementById("startMergeBtn").disabled = false;
      const badge = document.getElementById("cmSavedBadge");
      badge.style.display = "inline-flex";
      setTimeout(() => { badge.style.display = "none"; }, 3000);
    } catch (err) {
      cisToast("Failed to save mappings: " + err.message, "error");
      btn.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> Save Mappings';
    }
  });
}

function buildMappingObject(quiet = false) {
  const map = {};
  const groups = document.querySelectorAll(".cm-group");
  for (let g of groups) {
    const target = g.querySelector(".cm-target-input").value.trim();
    const sources = Array.from(g.querySelectorAll(".cm-tag")).map(t => t.dataset.val);
    if (!target) {
      if (!quiet) cisToast("A merge group is missing a target class name.", "error");
      return null;
    }
    if (sources.length === 0) {
      if (!quiet) cisToast(`Group '${target || 'Unnamed'}' is empty.`, "error");
      return null;
    }
    if (map[target]) {
      if (!quiet) cisToast(`Duplicate target name: '${target}'`, "error");
      return null;
    }
    map[target] = sources;
  }
  return map;
}

function validateMappings() {
  const msg = document.getElementById("cmValidationMsg");
  const list = document.getElementById("cmPreviewList");
  const btn = document.getElementById("startMergeBtn");
  
  // Disable merge until re-saved
  btn.disabled = true;
  document.getElementById("cmSavedBadge").style.display = "none";

  // Hide hints if pool is empty
  const pool = document.getElementById("cmUnassignedPool");
  const poolHint = pool.querySelector("span");
  if (poolHint) poolHint.style.display = pool.querySelectorAll(".cm-tag").length > 0 ? "none" : "inline";

  // Build taxonomy preview quietly
  const map = buildMappingObject(true);

  list.innerHTML = "";
  if (!map) {
    msg.innerHTML = '<div class="cm-err"><i class="fa-solid fa-triangle-exclamation"></i> Invalid configuration</div>';
    return;
  }

  const finalClasses = [];
  Object.entries(map).forEach(([target, sources]) => {
    finalClasses.push({ target, sources, type: 'mapped' });
  });

  // Add unmapped items as pass-through
  pool.querySelectorAll(".cm-tag").forEach(t => {
    finalClasses.push({ target: t.dataset.val, sources: [t.dataset.val], type: 'passthrough' });
  });

  // Sort by target name to simulate data.yaml ordering
  finalClasses.sort((a, b) => a.target.localeCompare(b.target));

  finalClasses.forEach((fc, idx) => {
    const row = document.createElement("div");
    row.className = "cm-preview-row";
    row.innerHTML = `
      <div class="cm-preview-idx">${idx}</div>
      <div class="cm-preview-name">${fc.target}</div>
      <div class="cm-preview-sources">${fc.type === 'mapped' ? '(' + fc.sources.join(', ') + ')' : '(Unmapped pass-through)'}</div>
    `;
    list.appendChild(row);
  });

  if (pool.querySelectorAll(".cm-tag").length > 0) {
    msg.innerHTML = '<div class="cm-warn"><i class="fa-solid fa-circle-info"></i> Unassigned classes will be kept as-is in the final dataset.</div>';
  } else {
    msg.innerHTML = '';
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// MERGE
// ─────────────────────────────────────────────────────────────────────────────

document.getElementById("startMergeBtn").addEventListener("click", async () => {
  const map = buildMappingObject(false);
  if (!map) return; // Safety

  document.getElementById("startMergeBtn").disabled = true;
  document.getElementById("mergeStatusCard").style.display = "block";
  document.getElementById("mergeDownloadBtnContainer").style.display = "none";

  // Reset the download button listener to avoid duplicate triggers
  const dlBtn = document.getElementById("downloadZipBtn");
  const newDlBtn = dlBtn.cloneNode(true);
  dlBtn.parentNode.replaceChild(newDlBtn, dlBtn);
  document.getElementById("mergeStatusText").textContent = "Merging datasets in background...";
  document.getElementById("mergeStatusIcon").innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';

  const config = {
    remove_duplicates: document.getElementById("chkRemoveDuplicates").checked,
    remove_blurry: document.getElementById("chkRemoveBlurry").checked,
    remove_corrupted: document.getElementById("chkRemoveCorrupted").checked,
    blurry_threshold: 100,
    excluded_images: [],
    excluded_annotations: [],
    class_mappings: map
  };

  try {
    await CISApi.post(`/api/merger/merge/${currentOperationId}`, config);
    pollMerge();
  } catch (err) {
    cisToast(err.message, "error");
    document.getElementById("startMergeBtn").disabled = false;
  }
});

function pollMerge() {
  if (pollInterval) clearInterval(pollInterval);
  pollInterval = setInterval(async () => {
    try {
      const op = await CISApi.get(`/api/merger/${currentOperationId}`);
      if (op.status === "completed") {
        clearInterval(pollInterval);
        document.getElementById("mergeStatusIcon").innerHTML = '<i class="fa-solid fa-check cis-text-success"></i>';
        document.getElementById("mergeStatusText").textContent =
          `Merge complete! Archive size: ${(op.zip_file_size / 1024 / 1024).toFixed(2)} MB. Included ${op.merged_images_count} images.`;
        document.getElementById("mergeDownloadBtnContainer").style.display = "block";
        
        // Attach fetch download logic
        const dlBtn = document.getElementById("downloadZipBtn");
        dlBtn.onclick = async (e) => {
          e.preventDefault();
          const originalHtml = dlBtn.innerHTML;
          dlBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Downloading...';
          dlBtn.classList.add("cis-disabled");
          try {
            const token = window.CISApi ? window.CISApi.getAccessToken() : localStorage.getItem("cis_access_token");
            const res = await fetch(`/api/merger/download/${currentOperationId}`, {
              headers: { "Authorization": `Bearer ${token}` }
            });
            if (!res.ok) {
              let msg = "Download failed";
              try { const errData = await res.json(); msg = errData.detail || msg; } catch(e){}
              throw new Error(msg);
            }
            const blob = await res.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `${op.merge_name}.zip`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            window.URL.revokeObjectURL(url);
          } catch (err) {
            cisToast(err.message, "error");
          } finally {
            dlBtn.innerHTML = originalHtml;
            dlBtn.classList.remove("cis-disabled");
          }
        };

        loadOperations();
      } else if (op.status === "failed") {
        clearInterval(pollInterval);
        document.getElementById("mergeStatusIcon").innerHTML = '<i class="fa-solid fa-xmark cis-text-danger"></i>';
        document.getElementById("mergeStatusText").textContent = "Merge failed: " + op.error_message;
      }
    } catch (err) {
      console.error("[merger] pollMerge:", err);
    }
  }, 2000);
}

// ─────────────────────────────────────────────────────────────────────────────
// INIT
// ─────────────────────────────────────────────────────────────────────────────
loadDatasets();
loadOperations();
