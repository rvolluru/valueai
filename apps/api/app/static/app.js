const form = document.getElementById("analyzeForm");
const previewGrid = document.getElementById("previewGrid");
const imagesInput = document.getElementById("images");
const statusEl = document.getElementById("status");
const analyzeBtn = document.getElementById("analyzeBtn");
const healthBtn = document.getElementById("healthBtn");
const sampleBtn = document.getElementById("sampleBtn");
const latencyBadge = document.getElementById("latencyBadge");
const summaryCards = document.getElementById("summaryCards");
const debugSections = document.getElementById("debugSections");
const brandDebugEl = document.getElementById("brandDebug");
const conditionDebugEl = document.getElementById("conditionDebug");
const valuationDebugEl = document.getElementById("valuationDebug");
const rawJsonEl = document.getElementById("rawJson");
const categoryInput = document.getElementById("category");
const itemSizeInput = document.getElementById("itemSize");
const itemSizeLabel = document.getElementById("itemSizeLabel");

const SIZE_FIELD_META = {
  clothes: { label: "Apparel size", placeholder: "e.g. S, M, L, 8, 10" },
  shoes: { label: "Shoe size (US)", placeholder: "e.g. 7.5, 9, 10.5" },
  handbag: { label: "Bag size", placeholder: "e.g. Mini, Small, Medium, Large" },
};

function setStatus(text, kind = "") {
  statusEl.textContent = text;
  statusEl.className = `status ${kind}`.trim();
}

function prettyJson(obj) {
  return JSON.stringify(obj ?? {}, null, 2);
}

function truncate(text, n = 80) {
  if (!text) return "";
  return text.length > n ? `${text.slice(0, n - 1)}…` : text;
}

function renderPreviews(files) {
  previewGrid.innerHTML = "";
  [...files].slice(0, 4).forEach((file, index) => {
    const fig = document.createElement("figure");
    fig.className = "preview";
    const img = document.createElement("img");
    const caption = document.createElement("figcaption");
    caption.textContent = `${index === 0 ? "full_item" : "close_up"} · ${truncate(file.name, 28)}`;
    fig.append(img, caption);
    previewGrid.appendChild(fig);
    const reader = new FileReader();
    reader.onload = () => {
      img.src = reader.result;
    };
    reader.readAsDataURL(file);
  });
}

function updateSizeInputState() {
  const meta = SIZE_FIELD_META[categoryInput.value];
  if (!meta) {
    itemSizeLabel.textContent = "Item size (select category)";
    itemSizeInput.placeholder = "Select category first";
    itemSizeInput.value = "";
    itemSizeInput.disabled = true;
    return;
  }
  itemSizeLabel.textContent = meta.label;
  itemSizeInput.placeholder = meta.placeholder;
  itemSizeInput.disabled = false;
}

function renderSummaryCard(title, main, meta, pills = []) {
  const card = document.createElement("div");
  card.className = "card";
  const h = document.createElement("h3");
  h.textContent = title;
  const p = document.createElement("p");
  p.className = "big";
  p.textContent = main;
  const m = document.createElement("div");
  m.className = "meta";
  m.textContent = meta || "";
  card.append(h, p, m);
  if (pills.length) {
    const wrap = document.createElement("div");
    wrap.className = "pill-list";
    pills.forEach(({ label, warn }) => {
      const pill = document.createElement("span");
      pill.className = `pill ${warn ? "warn" : ""}`.trim();
      pill.textContent = label;
      wrap.appendChild(pill);
    });
    card.appendChild(wrap);
  }
  return card;
}

function renderResults(payload, elapsedMs) {
  latencyBadge.textContent = `${elapsedMs.toFixed(0)} ms`;
  latencyBadge.className = "badge";

  summaryCards.classList.remove("empty");
  summaryCards.innerHTML = "";

  const brand = payload.brand || {};
  const condition = payload.condition || {};
  const valuation = payload.valuation || null;
  const requested = payload.requested_photos || [];

  summaryCards.appendChild(
    renderSummaryCard(
      "Brand",
      `${brand.name || "unknown"} (${Math.round((brand.confidence || 0) * 100)}%)`,
      `Evidence: ${brand.evidence || "n/a"}`,
      requested.map((r) => ({ label: `Need: ${r}`, warn: true }))
    )
  );

  summaryCards.appendChild(
    renderSummaryCard(
      "Condition",
      `${condition.grade || "n/a"} (${Math.round((condition.confidence || 0) * 100)}%)`,
      `Category: ${payload.category || "n/a"}`,
      (condition.issues || []).slice(0, 5).map((i) => ({ label: `${i.type}:${i.severity}` }))
    )
  );

  summaryCards.appendChild(
    renderSummaryCard(
      "Valuation",
      valuation?.estimated_value != null
        ? `${valuation.currency || "USD"} ${Number(valuation.estimated_value).toFixed(2)}`
        : "Unavailable",
      valuation
        ? `Range: ${valuation.currency || "USD"} ${valuation.range_low} - ${valuation.range_high} · ${(valuation.confidence * 100).toFixed(0)}%`
        : "Brand unknown or no comps available",
      valuation?.comps_summary?.source_breakdown
        ? Object.entries(valuation.comps_summary.source_breakdown).map(([k, v]) => ({ label: `${k}:${v}` }))
        : []
    )
  );

  summaryCards.appendChild(
    renderSummaryCard(
      "Item",
      payload.item_id || "n/a",
      `Requested photos: ${requested.length}`,
      requested.length ? requested.map((r) => ({ label: r, warn: true })) : [{ label: "Sufficient evidence" }]
    )
  );

  const showRaw = document.getElementById("showRawJson").checked;
  debugSections.classList.remove("hidden");
  rawJsonEl.parentElement.open = showRaw;
  brandDebugEl.textContent = prettyJson(payload.debug?.brand || {});
  conditionDebugEl.textContent = prettyJson(payload.debug?.condition || {});
  valuationDebugEl.textContent = prettyJson(payload.debug?.valuation || {});
  rawJsonEl.textContent = prettyJson(payload);
}

async function postAnalyze(formData, apiKey) {
  const resp = await fetch("/v1/analyze", {
    method: "POST",
    headers: { "x-api-key": apiKey },
    body: formData,
  });
  const text = await resp.text();
  let json = null;
  try { json = JSON.parse(text); } catch (_) {}
  if (!resp.ok) {
    const err = json?.detail ? JSON.stringify(json.detail) : text;
    throw new Error(`HTTP ${resp.status}: ${err}`);
  }
  return json;
}

imagesInput.addEventListener("change", () => renderPreviews(imagesInput.files || []));
categoryInput.addEventListener("change", updateSizeInputState);
updateSizeInputState();

healthBtn.addEventListener("click", async () => {
  setStatus("Checking API health...");
  try {
    const t0 = performance.now();
    const resp = await fetch("/v1/health");
    const payload = await resp.json();
    setStatus(`Health: ${payload.status} (${(performance.now() - t0).toFixed(0)} ms)`, "ok");
  } catch (err) {
    setStatus(`Health check failed: ${err.message}`, "error");
  }
});

sampleBtn.addEventListener("click", () => {
  document.getElementById("itemId").value = `item-${Math.floor(Math.random() * 9000 + 1000)}`;
  if (!document.getElementById("itemDescription").value.trim()) {
    document.getElementById("itemDescription").value = "Louis Vuitton Neverfull MM Monogram Tote";
  }
  if (!document.getElementById("purchaseYear").value) {
    document.getElementById("purchaseYear").value = "2019";
  }
  setStatus("Loaded sample IDs/hints. Choose images and run analysis.");
});

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const files = [...(imagesInput.files || [])];
  if (files.length < 1 || files.length > 4) {
    setStatus("Please select 1-4 images.", "error");
    return;
  }

  const apiKey = document.getElementById("apiKey").value.trim();
  const itemId = document.getElementById("itemId").value.trim();
  if (!apiKey) {
    setStatus("API Key is required.", "error");
    return;
  }

  const fd = new FormData();
  if (itemId) fd.append("item_id", itemId);
  const category = document.getElementById("category").value;
  const itemSize = document.getElementById("itemSize").value.trim();
  const itemDescription = document.getElementById("itemDescription").value.trim();
  const purchaseYear = document.getElementById("purchaseYear").value.trim();
  const debug = document.getElementById("debug").checked;
  if (category) fd.append("category", category);
  if (itemSize) fd.append("item_size", itemSize);
  if (itemDescription) fd.append("item_description", itemDescription);
  if (purchaseYear) fd.append("purchase_year", purchaseYear);
  fd.append("debug", String(debug));
  files.slice(0, 4).forEach((f) => fd.append("images", f, f.name));

  analyzeBtn.disabled = true;
  setStatus("Submitting analysis request...");
  const t0 = performance.now();
  try {
    const payload = await postAnalyze(fd, apiKey);
    const elapsed = performance.now() - t0;
    renderResults(payload, elapsed);
    setStatus("Analysis complete.", "ok");
  } catch (err) {
    latencyBadge.textContent = "Request failed";
    latencyBadge.className = "badge muted";
    setStatus(err.message || String(err), "error");
  } finally {
    analyzeBtn.disabled = false;
  }
});
