const API = "/api/requirements";

// Utility: Fetch JSON with error handling
async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to fetch ${url}: ${res.status}`);
  return res.json();
}

// Renderer: Display list of requirements
function renderList(items) {
  const ul = document.getElementById("item-list");
  if (!ul) return; // Prevent error if element not found
  ul.innerHTML = items.map(i => `<li>${i.name}</li>`).join("");
}

// Wrapper: Fetch and render list
async function renderListWrapper() {
  try {
    const items = await fetchJSON(API);
    renderList(items);
  } catch (err) {
    console.error("Failed to render list:", err);
  }
}

// Populate the multi-select for export
async function renderExportOptions() {
  try {
    const select = document.getElementById("export-select");
    if (!select) return;
    // Fetch from Azure DevOps endpoint
    const items = await fetchJSON("/api/ado/workitems");
    select.innerHTML = items.map(r =>
      `<option value="${r.id}">${r.id} - ${r.title}</option>`
    ).join("");
  } catch (err) {
    console.error("Failed to render export options:", err);
  }
}

// Optional: Render traceability links
async function renderTrace() {
  try {
    const traceEl = document.getElementById("trace-view");
    if (!traceEl) return; // Prevent error if element not found
    const data = await fetchJSON("/api/trace");
    traceEl.innerHTML = data.map(t =>
      `<li>${t.source} ➡️ ${t.target}</li>`
    ).join("");
  } catch (err) {
    console.error("Trace fetch failed:", err);
  }
}

// Handle OSLC Export download
document.getElementById("export-btn").onclick = async () => {
  const sel = document.getElementById("export-select");
  const ids = Array.from(sel.selectedOptions).map(o => o.value).join(",");
  if (!ids) return alert("Select at least one ID");

  try {
    const res = await fetch(`/api/oslc/export?ids=${ids}`, {
      headers: { "Accept": "application/rdf+xml" }
    });
    if (!res.ok) {
      const err = await res.json();
      return alert("Export failed: " + JSON.stringify(err));
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "requirements-export.rdf";
    a.click();
    URL.revokeObjectURL(url);
  } catch (err) {
    alert("Export error: " + err.message);
  }
};

// Handle OSLC Import upload
document.getElementById("import-btn").onclick = async () => {
  const fileInput = document.getElementById("import-file");
  const resultEl = document.getElementById("import-result");

  if (!fileInput.files.length) return alert("Choose a file");
  const file = fileInput.files[0];
  const data = await file.arrayBuffer();

  try {
    const res = await fetch("/api/oslc/import?type=User%20Story", {
      method: "POST",
      headers: { "Content-Type": "application/rdf+xml" },
      body: data
    });

    if (!res.ok) {
      const err = await res.json();
      resultEl.textContent = "Import failed:\n" + JSON.stringify(err, null, 2);
    } else {
      const json = await res.json();
      resultEl.textContent = "Import successful:\n" + JSON.stringify(json, null, 2);
      await renderListWrapper();
      await renderExportOptions();
      // await renderTrace();
    }
  } catch (err) {
    resultEl.textContent = "Import error:\n" + err.message;
  }
};

// On page load, render everything
window.onload = () => {
  renderListWrapper();
  renderExportOptions();
  // renderTrace();
};
