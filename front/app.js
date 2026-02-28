const API_BASE = "/api";

const form = document.getElementById("itemForm");
const itemIdInput = document.getElementById("itemId");
const nameInput = document.getElementById("name");
const skuInput = document.getElementById("sku");
const quantityInput = document.getElementById("quantity");
const locationInput = document.getElementById("location");
const priceInput = document.getElementById("price");
const costUnitInput = document.getElementById("costUnit");
const thresholdInput = document.getElementById("threshold");
const saveBtn = document.getElementById("saveBtn");
const cancelEditBtn = document.getElementById("cancelEdit");

const searchInput = document.getElementById("search");
const lowOnlyInput = document.getElementById("lowOnly");
const sortByInput = document.getElementById("sortBy");

const inventoryBody = document.getElementById("inventoryBody");
const statItems = document.getElementById("statItems");
const statUnits = document.getElementById("statUnits");
const statLow = document.getElementById("statLow");
const statValue = document.getElementById("statValue");
const statCash = document.getElementById("statCash");

const statItemsTrend = document.getElementById("statItemsTrend");
const statUnitsTrend = document.getElementById("statUnitsTrend");
const statLowTrend = document.getElementById("statLowTrend");
const statValueTrend = document.getElementById("statValueTrend");
const statCashTrend = document.getElementById("statCashTrend");

const lowStockPanel = document.getElementById("lowStockPanel");
const lowStockList = document.getElementById("lowStockList");

const salesChartCtx = document.getElementById("salesChart")?.getContext("2d");
const topProductsCtx = document.getElementById("topProductsChart")?.getContext("2d");

let salesChart = null;
let topProductsChart = null;

const reportToggleBtn = document.getElementById("reportToggleBtn");
const reportBackBtn = document.getElementById("reportBackBtn");
const reportPrintBtn = document.getElementById("reportPrintBtn");
const weeklyDash = document.getElementById("weeklyDash");
const weeklyRange = document.getElementById("weeklyRange");
const weeklyTotal = document.getElementById("weeklyTotal");
const weeklyCount = document.getElementById("weeklyCount");
const weeklyUnits = document.getElementById("weeklyUnits");
const weeklyByPayment = document.getElementById("weeklyByPayment");

const exportBtn = document.getElementById("exportCsv");
const backupBtn = document.getElementById("backupBtn");
const importInput = document.getElementById("importCsv");

const saleForm = document.getElementById("saleForm");
const saleItemId = document.getElementById("saleItemId");
const salePriceInput = document.getElementById("salePriceInput");
const saleQuantity = document.getElementById("saleQuantity");
const salePaymentMethod = document.getElementById("salePaymentMethod");
const saleTotalInput = document.getElementById("saleTotalInput");
const saleError = document.getElementById("saleError");
const salesBody = document.getElementById("salesBody");
const salesDash = document.getElementById("salesDash");
const salesToggleBtn = document.getElementById("salesToggleBtn");
const salesBackBtn = document.getElementById("salesBackBtn");
const salesSearch = document.getElementById("salesSearch");
const salesPaymentFilter = document.getElementById("salesPaymentFilter");
const totalEfectivo = document.getElementById("totalEfectivo");
const totalYappy = document.getElementById("totalYappy");
const totalVentas = document.getElementById("totalVentas");
const logoutBtn = document.getElementById("logoutBtn");
const userDisplay = document.getElementById("userDisplay");

let items = [];
let sales = [];
let editingId = null;

const authToken = localStorage.getItem("authToken");
const username = localStorage.getItem("username");

if (!authToken) {
  window.location.href = "/login.html";
}

const currency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
});

// Toast Notifications
const toastContainer = document.getElementById("toastContainer");

function showToast(message, type = "info") {
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.setAttribute("role", "status");
  toast.setAttribute("aria-live", "polite");
  toast.innerHTML = `
    <span class="toast-icon">${type === "success" ? "✓" : type === "error" ? "✕" : "ℹ"}</span>
    <span class="toast-message">${escapeHtml(message)}</span>
  `;
  
  if (toastContainer) {
    toastContainer.appendChild(toast);
  }
  
  setTimeout(() => {
    toast.classList.add("removing");
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}

async function fetchJson(url, options = {}) {
  const token = localStorage.getItem("authToken");
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${token}`,
      ...(options.headers || {}),
    },
    ...options,
  });

  let data = null;
  try {
    data = await response.json();
  } catch (error) {
    data = null;
  }

  if (response.status === 401) {
    localStorage.removeItem("authToken");
    localStorage.removeItem("username");
    window.location.href = "/login.html";
    return;
  }

  if (!response.ok) {
    const message = data?.error || "Request failed.";
    throw new Error(message);
  }
  return data;
}

async function loadItems() {
  items = await fetchJson(`${API_BASE}/items`);
  syncUI();
}

async function saveItem(item) {
  if (editingId) {
    const updated = await fetchJson(`${API_BASE}/items/${item.id}`, {
      method: "PUT",
      body: JSON.stringify(item),
    });
    upsertLocal(updated);
    return;
  }

  const created = await fetchJson(`${API_BASE}/items`, {
    method: "POST",
    body: JSON.stringify(item),
  });
  upsertLocal(created);
}

async function updateItem(itemId, updates) {
  const item = items.find((i) => i.id === itemId);
  if (!item) return;
  const updated = { ...item, ...updates, updatedAt: new Date().toISOString() };
  await fetchJson(`${API_BASE}/items/${itemId}`, {
    method: "PUT",
    body: JSON.stringify(updated),
  });
  upsertLocal(updated);
}

async function deleteItem(id) {
  await fetchJson(`${API_BASE}/items/${id}`, { method: "DELETE" });
  items = items.filter((item) => item.id !== id);
}

async function replaceAllItems(nextItems) {
  items = await fetchJson(`${API_BASE}/items/bulk`, {
    method: "POST",
    body: JSON.stringify({ items: nextItems }),
  });
}

function getFormData() {
  return {
    id: editingId ?? crypto.randomUUID(),
    name: nameInput.value.trim(),
    sku: skuInput.value.trim(),
    quantity: Number(quantityInput.value),
    location: locationInput.value.trim(),
    price: Number(priceInput.value),
    costUnit: Number(costUnitInput.value),
    threshold: Number(thresholdInput.value),
    description: "",
    imageUrl: "",
    status: "Nuevo",
    updatedAt: new Date().toISOString(),
  };
}

function setFormData(item) {
  nameInput.value = item.name;
  skuInput.value = item.sku;
  quantityInput.value = item.quantity;
  locationInput.value = item.location;
  priceInput.value = item.price;
  costUnitInput.value = item.costUnit || 0;
  thresholdInput.value = item.threshold;
  if (statusInput) {
    statusInput.value = item.status || "Nuevo";
  }
}

function resetForm() {
  form.reset();
  editingId = null;
  itemIdInput.value = "";
  saveBtn.textContent = "Save Item";
  cancelEditBtn.hidden = true;
}

function startEdit(item) {
  editingId = item.id;
  itemIdInput.value = item.id;
  setFormData(item);
  saveBtn.textContent = "Save Changes";
  cancelEditBtn.hidden = false;
  form.scrollIntoView({ behavior: "smooth", block: "start" });
}

function upsertLocal(newItem) {
  const exists = items.findIndex((item) => item.id === newItem.id);
  if (exists >= 0) {
    items[exists] = newItem;
  } else {
    items.unshift(newItem);
  }
}

function applyFilters(rawItems) {
  const search = searchInput.value.trim().toLowerCase();
  const lowOnly = lowOnlyInput.checked;

  let next = rawItems.filter((item) => {
    const matches =
      item.name.toLowerCase().includes(search) ||
      item.sku.toLowerCase().includes(search) ||
      item.location.toLowerCase().includes(search);
    const low = item.quantity <= item.threshold;
    return matches && (!lowOnly || low);
  });

  const sortBy = sortByInput.value;
  next = [...next].sort((a, b) => {
    switch (sortBy) {
      case "name":
        return a.name.localeCompare(b.name);
      case "quantity":
        return b.quantity - a.quantity;
      case "value":
        return b.quantity * b.price - a.quantity * a.price;
      default:
        return new Date(b.updatedAt) - new Date(a.updatedAt);
    }
  });

  return next;
}

function renderStats() {
  statItems.textContent = items.length.toString();
  const totalUnits = items.reduce((sum, item) => sum + item.quantity, 0);
  const lowCount = items.filter((item) => item.quantity <= item.threshold).length;
  const totalValue = items.reduce(
    (sum, item) => sum + item.quantity * item.price,
    0
  );
  const totalCash = sales.reduce((sum, sale) => sum + (sale.gain || 0), 0);

  statUnits.textContent = totalUnits.toString();
  statLow.textContent = lowCount.toString();
  statValue.textContent = currency.format(totalValue);
  statCash.textContent = currency.format(totalCash);

  // Calculate trends (7 days ago)
  const sevenDaysAgo = new Date();
  sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);
  
  const oldSales = sales.filter(s => new Date(s.createdAt) < sevenDaysAgo);
  const oldItemCount = items.length; // Simplified - would need history
  const oldTotalUnits = oldSales.reduce((sum, s) => sum + s.quantity, 0);
  const oldTotalValue = oldSales.reduce((sum, s) => sum + s.total, 0);
  const oldTotalCash = oldSales.reduce((sum, sale) => sum + (sale.gain || 0), 0);

  // Show trends
  updateTrendIndicator(statItemsTrend, items.length, oldItemCount);
  updateTrendIndicator(statUnitsTrend, totalUnits, oldTotalUnits);
  updateTrendIndicator(statLowTrend, lowCount, 0);
  updateTrendIndicator(statValueTrend, totalValue, oldTotalValue);
  updateTrendIndicator(statCashTrend, totalCash, oldTotalCash);

  // Show low stock alerts
  renderLowStockAlerts();
}

function updateTrendIndicator(element, current, previous) {
  if (!element) return;
  
  if (previous === 0) {
    element.textContent = current > 0 ? "↑ New" : "=";
    element.className = "stat-trend neutral";
    return;
  }

  const diff = current - previous;
  const percent = Math.round((diff / previous) * 100);
  
  if (diff > 0) {
    element.textContent = `↑ ${percent > 0 ? '+' : ''}${percent}%`;
    element.className = "stat-trend positive";
  } else if (diff < 0) {
    element.textContent = `↓ ${percent}%`;
    element.className = "stat-trend negative";
  } else {
    element.textContent = "=";
    element.className = "stat-trend neutral";
  }
}

function renderLowStockAlerts() {
  const lowItems = items.filter(item => item.quantity <= item.threshold).sort((a, b) => a.quantity - b.quantity);
  
  if (lowItems.length === 0) {
    lowStockPanel.hidden = true;
    return;
  }
  
  lowStockPanel.hidden = false;
  lowStockList.innerHTML = lowItems.map(item => {
    const percent = (item.quantity / item.threshold) * 100;
    const status = item.quantity === 0 ? "Out" : "Low";
    return `
      <div class="alert-item ${item.quantity === 0 ? 'critical' : 'warning'}">
        <div class="alert-info">
          <p class="alert-name">${escapeHtml(item.name)}</p>
          <p class="alert-sku">${escapeHtml(item.sku)}</p>
        </div>
        <div class="alert-numbers">
          <p class="alert-qty">${item.quantity} (Threshold: ${item.threshold})</p>
          <div class="alert-bar">
            <div class="alert-fill" style="width: ${Math.min(percent, 100)}%"></div>
          </div>
        </div>
        <button class="btn btn-small" onclick="quickReorder('${item.id}')">Quick Order</button>
      </div>
    `;
  }).join("");
}

function quickReorder(itemId) {
  const item = items.find(i => i.id === itemId);
  if (!item) return;
  startEdit(item);
}

async function updateCharts() {
  // Prepare data for last 7 days
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const dayLabels = [];
  const daySalesData = [];
  
  for (let i = 6; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(d.getDate() - i);
    dayLabels.push(d.toLocaleDateString("en-US", { month: "short", day: "numeric" }));
    
    const daySales = sales.filter(s => {
      const sDate = new Date(s.createdAt);
      sDate.setHours(0, 0, 0, 0);
      return sDate.getTime() === d.getTime();
    });
    
    const dayTotal = daySales.reduce((sum, s) => sum + s.total, 0);
    daySalesData.push(parseFloat(dayTotal.toFixed(2)));
  }

  // Update Weekly Sales Chart
  if (salesChart) {
    salesChart.data.labels = dayLabels;
    salesChart.data.datasets[0].data = daySalesData;
    salesChart.update();
  } else if (salesChartCtx) {
    salesChart = new Chart(salesChartCtx, {
      type: "line",
      data: {
        labels: dayLabels,
        datasets: [
          {
            label: "Daily Sales",
            data: daySalesData,
            borderColor: "#3b82f6",
            backgroundColor: "rgba(59, 130, 246, 0.1)",
            borderWidth: 2,
            fill: true,
            tension: 0.4,
            pointRadius: 4,
            pointBackgroundColor: "#3b82f6",
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: true,
        plugins: {
          legend: {
            labels: { color: "#e2e8f0" },
          },
        },
        scales: {
          y: {
            ticks: { color: "#94a3b8" },
            grid: { color: "#232a33" },
            beginAtZero: true,
          },
          x: {
            ticks: { color: "#94a3b8" },
            grid: { color: "#232a33" },
          },
        },
      },
    });
  }

  // Top 5 Products by quantity sold
  const productSales = {};
  sales.forEach(sale => {
    const item = items.find(i => i.id === sale.itemId);
    if (item) {
      productSales[item.id] = (productSales[item.id] || 0) + sale.quantity;
    }
  });

  const topProducts = Object.entries(productSales)
    .map(([itemId, qty]) => ({
      name: items.find(i => i.id === itemId)?.name || "Unknown",
      quantity: qty,
    }))
    .sort((a, b) => b.quantity - a.quantity)
    .slice(0, 5);

  const topLabels = topProducts.map(p => p.name);
  const topData = topProducts.map(p => p.quantity);

  if (topProductsChart) {
    topProductsChart.data.labels = topLabels;
    topProductsChart.data.datasets[0].data = topData;
    topProductsChart.update();
  } else if (topProductsCtx) {
    topProductsChart = new Chart(topProductsCtx, {
      type: "bar",
      data: {
        labels: topLabels,
        datasets: [
          {
            label: "Units Sold",
            data: topData,
            backgroundColor: [
              "#3b82f6",
              "#1e40af",
              "#1e3a8a",
              "#172554",
              "#0c1540",
            ],
            borderRadius: 4,
          },
        ],
      },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: true,
        plugins: {
          legend: {
            labels: { color: "#e2e8f0" },
          },
        },
        scales: {
          x: {
            ticks: { color: "#94a3b8" },
            grid: { color: "#232a33" },
            beginAtZero: true,
          },
          y: {
            ticks: { color: "#94a3b8" },
            grid: { color: "#232a33" },
          },
        },
      },
    });
  }
}

function renderTable() {
  const view = applyFilters(items);
  if (view.length === 0) {
    inventoryBody.innerHTML =
      "<tr><td colspan='7'>No items found. Add the first item above.</td></tr>";
    return;
  }

  inventoryBody.innerHTML = view
    .map((item) => {
      const low = item.quantity <= item.threshold;
      return `
      <tr>
        <td>${escapeHtml(item.name)} ${low ? "<span class='badge'>Low</span>" : ""}</td>
        <td>${escapeHtml(item.sku)}</td>
        <td class="qty-cell" data-id="${item.id}" data-qty="${item.quantity}" title="Double-click to edit">${item.quantity}</td>
        <td>${escapeHtml(item.location)}</td>
        <td>${currency.format(item.price)}</td>
        <td>${formatDate(item.updatedAt)}</td>
        <td>
          <button class="action-btn" data-action="edit" data-id="${item.id}">Edit</button>
          <button class="action-btn danger" data-action="delete" data-id="${item.id}">Delete</button>
        </td>
      </tr>`;
    })
    .join("");
}

function formatDate(iso) {
  const date = new Date(iso);
  return date.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function escapeHtml(value) {
  return value.replace(/[&<>"']/g, (match) => {
    const chars = {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    };
    return chars[match];
  });
}

function formatShortDate(date) {
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

function renderWeeklyReport(report) {
  if (!weeklyRange || !weeklyTotal || !weeklyCount || !weeklyUnits || !weeklyByPayment) {
    return;
  }
  const start = new Date(report.start);
  const end = new Date(report.end);
  const endDisplay = new Date(end);
  endDisplay.setDate(endDisplay.getDate() - 1);
  weeklyRange.textContent = `Week of ${formatShortDate(start)} - ${formatShortDate(endDisplay)}`;
  weeklyTotal.textContent = currency.format(report.total || 0);
  weeklyCount.textContent = String(report.count || 0);
  weeklyUnits.textContent = String(report.units || 0);

  if (report.byPayment && report.byPayment.length) {
    weeklyByPayment.innerHTML = report.byPayment
      .map(
        (row) =>
          `<div class="report-item"><span>${escapeHtml(
            String(row.method ?? "")
          )}</span><span>${currency.format(row.total || 0)}</span><span>${
            row.count || 0
          } sales</span></div>`
      )
      .join("");
  } else {
    weeklyByPayment.innerHTML =
      "<div class='report-empty'>No sales this week.</div>";
  }
}

async function loadWeeklyReport() {
  try {
    const report = await fetchJson(`${API_BASE}/reports/weekly`);
    renderWeeklyReport(report);
  } catch (error) {
    console.error(error);
    if (weeklyByPayment) {
      weeklyByPayment.innerHTML =
        "<div class='report-empty'>Cannot load report.</div>";
    }
  }
}

function syncUI() {
  renderStats();
  renderTable();
  updateCharts();
  updateSaleItemOptions();
}

function setSalesDashOpen(isOpen) {
  if (!salesDash || !salesToggleBtn) {
    return;
  }
  salesDash.classList.toggle("is-collapsed", !isOpen);
  salesToggleBtn.setAttribute("aria-expanded", String(isOpen));
  salesToggleBtn.textContent = isOpen ? "Ocultar ventas" : "Agregar venta";
}

function setSalesOnly(isOpen) {
  document.body.classList.toggle("sales-only", isOpen);
  if (isOpen) {
    document.body.classList.remove("report-only");
  }
  setSalesDashOpen(isOpen);
}

function setWeeklyDashOpen(isOpen) {
  if (!weeklyDash || !reportToggleBtn) {
    return;
  }
  weeklyDash.classList.toggle("is-collapsed", !isOpen);
  reportToggleBtn.setAttribute("aria-expanded", String(isOpen));
}

function setReportOnly(isOpen) {
  document.body.classList.toggle("report-only", isOpen);
  if (isOpen) {
    document.body.classList.remove("sales-only");
  }
  setWeeklyDashOpen(isOpen);
}

inventoryBody.addEventListener("click", async (event) => {
  // Edición rápida de cantidad con doble clic
  if (event.target.classList.contains("qty-cell") && event.detail === 2) {
    const cell = event.target;
    const itemId = cell.dataset.id;
    const currentQty = parseInt(cell.dataset.qty);
    const item = items.find((i) => i.id === itemId);
    if (!item) return;

    // Crear input editable
    const input = document.createElement("input");
    input.type = "number";
    input.value = currentQty;
    input.min = "0";
    input.className = "qty-input";
    input.style.width = "60px";
    input.style.padding = "4px";
    input.style.border = "1px solid var(--accent)";
    input.style.borderRadius = "4px";
    input.style.backgroundColor = "#0f141b";
    input.style.color = "var(--ink)";

    const originalContent = cell.innerHTML;
    cell.innerHTML = "";
    cell.appendChild(input);
    input.focus();
    input.select();

    // Guardar cambios
    const saveChanges = async () => {
      const newQty = parseInt(input.value) || 0;
      if (newQty === currentQty) {
        cell.innerHTML = originalContent;
        return;
      }
      try {
        await updateItem(itemId, { quantity: newQty });
        await loadItems();
        syncUI();
        showToast("Cantidad actualizada", "success");
      } catch (error) {
        console.error(error);
        showToast("Error al actualizar cantidad", "error");
        cell.innerHTML = originalContent;
      }
    };

    // Enter para guardar
    input.addEventListener("keydown", async (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        await saveChanges();
      } else if (e.key === "Escape") {
        cell.innerHTML = originalContent;
      }
    });

    // Blur para guardar
    input.addEventListener("blur", saveChanges);
    return;
  }

  // Resto de eventos
  const button = event.target.closest("button");
  if (!button) {
    return;
  }
  const id = button.dataset.id;
  const action = button.dataset.action;
  const item = items.find((entry) => entry.id === id);
  if (!item) {
    return;
  }
  if (action === "edit") {
    startEdit(item);
    return;
  }
  if (action === "delete") {
    try {
      await deleteItem(id);
      syncUI();
      showToast("Producto eliminado exitosamente", "success");
    } catch (error) {
      console.error(error);
      showToast("Error al eliminar. Verifica la conexión con el servidor.", "error");
    }
  }
});

searchInput.addEventListener("input", syncUI);
lowOnlyInput.addEventListener("change", syncUI);
sortByInput.addEventListener("change", syncUI);

if (salesToggleBtn) {
  salesToggleBtn.addEventListener("click", () => {
    setSalesOnly(true);
  });
}

if (salesBackBtn) {
  salesBackBtn.addEventListener("click", () => {
    setSalesOnly(false);
  });
}

if (salesSearch) {
  salesSearch.addEventListener("input", renderSalesTable);
}

if (salesPaymentFilter) {
  salesPaymentFilter.addEventListener("change", renderSalesTable);
}

salesBody.addEventListener("click", async (event) => {
  const button = event.target.closest("button");
  if (!button) {
    return;
  }
  const id = button.dataset.id;
  const action = button.dataset.action;
  if (action === "delete") {
    const confirmed = confirm("Delete this sale? Inventory will be restored.");
    if (!confirmed) {
      return;
    }
    try {
      await deleteSale(id);
      renderSalesTable();
      await loadItems();
      await loadWeeklyReport();
      showToast("Venta eliminada e inventario restaurado", "success");
    } catch (error) {
      console.error(error);
      showToast("Error al eliminar venta. Verifica la conexión con el servidor.", "error");
    }
  }
  if (action === "invoice") {
    try {
      const response = await fetch(`${API_BASE}/sales/${id}/invoice`, {
        headers: {
          "Authorization": `Bearer ${authToken}`,
        },
      });
      if (!response.ok) {
        throw new Error("Failed to download invoice");
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `invoice_${id.substring(0, 8)}.pdf`;
      link.click();
      URL.revokeObjectURL(url);
      showToast("Factura descargada exitosamente", "success");
    } catch (error) {
      console.error(error);
      showToast("Error al descargar factura. Intenta de nuevo.", "error");
    }
  }
});

if (reportToggleBtn) {
  reportToggleBtn.addEventListener("click", () => {
    setReportOnly(true);
  });
}

if (reportBackBtn) {
  reportBackBtn.addEventListener("click", () => {
    setReportOnly(false);
  });
}

if (reportPrintBtn) {
  reportPrintBtn.addEventListener("click", () => {
    window.print();
  });
}

if (backupBtn) {
  backupBtn.addEventListener("click", async () => {
    try {
      const response = await fetch(`${API_BASE}/backup`, {
        headers: {
          "Authorization": `Bearer ${authToken}`,
        },
      });
      if (!response.ok) {
        throw new Error("Backup failed");
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `backup-${new Date().toISOString().split("T")[0]}.db`;
      link.click();
      URL.revokeObjectURL(url);
      showToast("Base de datos descargada exitosamente", "success");
    } catch (error) {
      console.error(error);
      showToast("Error al descargar backup. Intenta de nuevo.", "error");
    }
  });
}

if (exportBtn) {
  exportBtn.addEventListener("click", () => {
  if (items.length === 0) {
    return;
  }
  const header = [
    "id",
    "name",
    "sku",
    "quantity",
    "location",
    "price",
    "threshold",
    "description",
    "imageUrl",
    "status",
    "updatedAt",
  ];
  const rows = items.map((item) =>
    header.map((key) => csvEscape(item[key]))
  );
  const csv = [header.join(","), ...rows.map((row) => row.join(","))].join(
    "\n"
  );
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "inventory.csv";
  link.click();
  URL.revokeObjectURL(url);
  showToast("Inventario exportado exitosamente", "success");
  });
}

if (importInput) {
  importInput.addEventListener("change", async (event) => {
  const file = event.target.files?.[0];
  if (!file) {
    return;
  }
  const text = await file.text();
  const parsed = parseCsv(text);
  if (parsed.length === 0) {
    return;
  }
  try {
    await replaceAllItems(parsed);
    syncUI();
    showToast("Inventario importado exitosamente", "success");
  } catch (error) {
    console.error(error);
    showToast("Error al importar CSV. Verifica el formato del archivo.", "error");
  }
  importInput.value = "";
  });
}

function csvEscape(value) {
  if (value === null || value === undefined) {
    return "";
  }
  const text = String(value);
  if (/[,"\n]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`;
  }
  return text;
}

function parseCsv(text) {
  const lines = text.trim().split(/\r?\n/);
  if (lines.length < 2) {
    return [];
  }
  const header = lines[0].split(",").map((value) => value.trim());
  const rows = lines.slice(1);
  return rows
    .map((line) => parseCsvLine(line, header.length))
    .filter((row) => row.length === header.length)
    .map((row) => {
      const item = {};
      header.forEach((key, index) => {
        item[key] = row[index];
      });
      return normalizeItem(item);
    });
}

function parseCsvLine(line, expectedLength) {
  const result = [];
  let current = "";
  let insideQuotes = false;

  for (let i = 0; i < line.length; i += 1) {
    const char = line[i];
    if (char === '"') {
      if (insideQuotes && line[i + 1] === '"') {
        current += '"';
        i += 1;
      } else {
        insideQuotes = !insideQuotes;
      }
      continue;
    }
    if (char === "," && !insideQuotes) {
      result.push(current);
      current = "";
      continue;
    }
    current += char;
  }
  result.push(current);
  while (result.length < expectedLength) {
    result.push("");
  }
  return result;
}

function normalizeItem(raw) {
  const quantity = Number(raw.quantity ?? 0);
  const price = Number(raw.price ?? 0);
  const threshold = Number(raw.threshold ?? 0);
  return {
    id: raw.id || crypto.randomUUID(),
    name: String(raw.name ?? "").trim(),
    sku: String(raw.sku ?? "").trim(),
    quantity: Number.isNaN(quantity) ? 0 : quantity,
    location: String(raw.location ?? "").trim(),
    price: Number.isNaN(price) ? 0 : price,
    threshold: Number.isNaN(threshold) ? 0 : threshold,
    description: String(raw.description ?? "").trim(),
    imageUrl: String(raw.imageUrl ?? raw.image_url ?? "").trim(),
    status: String(raw.status ?? "Nuevo").trim(),
    updatedAt: raw.updatedAt || new Date().toISOString(),
  };
}

async function loadSales() {
  sales = await fetchJson(`${API_BASE}/sales`);
  renderSalesTable();
  await loadWeeklyReport();
  updateCharts();
}

async function deleteSale(id) {
  await fetchJson(`${API_BASE}/sales/${id}`, { method: "DELETE" });
  sales = sales.filter((sale) => sale.id !== id);
}

function applySalesFilters(rawSales) {
  const search = salesSearch?.value.trim().toLowerCase() || "";
  const paymentFilter = salesPaymentFilter?.value || "";

  return rawSales.filter((sale) => {
    const item = items.find((i) => i.id === sale.itemId);
    const itemName = item ? item.name.toLowerCase() : "";
    const matchesSearch = !search || itemName.includes(search);
    const matchesPayment =
      !paymentFilter || sale.paymentMethod === paymentFilter;
    return matchesSearch && matchesPayment;
  });
}

function renderSalesTable() {
  const filteredSales = applySalesFilters(sales);

  if (filteredSales.length === 0) {
    salesBody.innerHTML =
      "<tr><td colspan='8'>No sales found.</td></tr>";
    updatePaymentSummary(filteredSales);
    return;
  }

  salesBody.innerHTML = filteredSales
    .map((sale) => {
      const item = items.find((i) => i.id === sale.itemId);
      const itemName = item ? item.name : "Unknown";
      const gain = sale.gain || 0;
      const paymentBadge = sale.paymentMethod === "Yappy" 
        ? `<span class="badge badge-yappy">⚡ ${sale.paymentMethod}</span>`
        : `<span class="badge badge-efectivo">💵 ${sale.paymentMethod}</span>`;
      return `
      <tr>
        <td>${escapeHtml(itemName)}</td>
        <td>${sale.quantity}</td>
        <td>${currency.format(sale.price)}</td>
        <td>${currency.format(sale.total)}</td>
        <td>${currency.format(gain)}</td>
        <td>${paymentBadge}</td>
        <td>${formatDate(sale.createdAt)}</td>
        <td>
          <button class="action-btn info" data-action="invoice" data-id="${
            sale.id
          }">Invoice</button>
          <button class="action-btn danger" data-action="delete" data-id="${
            sale.id
          }">Delete</button>
        </td>
      </tr>`;
    })
    .join("");
  
  updatePaymentSummary(filteredSales);
}

function updatePaymentSummary(salesList) {
  const yappyTotal = salesList
    .filter(s => s.paymentMethod === "Yappy")
    .reduce((sum, s) => sum + (s.total || 0), 0);
  
  const efectivoTotal = salesList
    .filter(s => s.paymentMethod === "Efectivo")
    .reduce((sum, s) => sum + (s.total || 0), 0);
  
  const totalSales = yappyTotal + efectivoTotal;

  if (totalYappy) totalYappy.textContent = currency.format(yappyTotal);
  if (totalEfectivo) totalEfectivo.textContent = currency.format(efectivoTotal);
  if (totalVentas) totalVentas.textContent = currency.format(totalSales);
}

function updateSaleItemOptions() {
  saleItemId.innerHTML = '<option value="">-- Select a product --</option>';
  items.forEach((item) => {
    const option = document.createElement("option");
    option.value = item.id;
    option.textContent = `${item.name} (${item.quantity} in stock)`;
    saleItemId.appendChild(option);
  });
}

let updatingSaleFields = false;

function updateSaleFromUnitPrice() {
  if (updatingSaleFields) {
    return;
  }
  const quantity = Number(saleQuantity.value) || 0;
  const unitPrice = Number(salePriceInput.value) || 0;
  updatingSaleFields = true;
  saleTotalInput.value = (quantity * unitPrice).toFixed(2);
  updatingSaleFields = false;
}

function updateSaleFromTotal() {
  if (updatingSaleFields) {
    return;
  }
  const quantity = Number(saleQuantity.value) || 0;
  const total = Number(saleTotalInput.value) || 0;
  updatingSaleFields = true;
  salePriceInput.value = quantity > 0 ? (total / quantity).toFixed(2) : "0.00";
  updatingSaleFields = false;
}

function updateSalePriceAndTotal() {
  const selectedId = saleItemId.value;
  const item = items.find((i) => i.id === selectedId);
  if (item) {
    salePriceInput.value = Number(item.price).toFixed(2);
    updateSaleFromUnitPrice();
  } else {
    salePriceInput.value = "";
    saleTotalInput.value = "";
  }
}

saleForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const itemId = saleItemId.value.trim();
  const quantity = Number(saleQuantity.value);
  const paymentMethod = salePaymentMethod.value.trim();
  const price = Number(salePriceInput.value);

  if (!itemId || quantity <= 0 || !paymentMethod || Number.isNaN(price) || price < 0) {
    saleError.textContent = "Fill in all fields.";
    return;
  }

  const item = items.find((i) => i.id === itemId);
  if (!item) {
    saleError.textContent = "Item not found.";
    return;
  }

  try {
    await fetchJson(`${API_BASE}/sales`, {
      method: "POST",
      body: JSON.stringify({
        itemId,
        quantity,
        price,
        paymentMethod,
      }),
    });
    saleForm.reset();
    saleError.textContent = "";
    await loadSales();
    await loadItems();
    await updateCashDashboard();
    syncUI();
    showToast("Venta registrada exitosamente", "success");
  } catch (error) {
    console.error(error);
    saleError.textContent = error.message;
  }
});

saleItemId.addEventListener("change", updateSalePriceAndTotal);
saleQuantity.addEventListener("input", updateSaleFromUnitPrice);
salePriceInput.addEventListener("input", updateSaleFromUnitPrice);
saleTotalInput.addEventListener("input", updateSaleFromTotal);

setSalesDashOpen(false);
setWeeklyDashOpen(false);

if (userDisplay && username) {
  userDisplay.textContent = `Logged in as ${username}`;
}

if (logoutBtn) {
  logoutBtn.addEventListener("click", async () => {
    try {
      await fetchJson(`${API_BASE}/auth/logout`, { method: "POST" });
    } catch (error) {
      console.error(error);
    }
    localStorage.removeItem("authToken");
    localStorage.removeItem("username");
    window.location.href = "/login.html";
  });
}

// Iniciar aplicación: cargar datos al abrir la página
async function initializeApp() {
  console.log("=== App Initialization Started ===");
  
  if (!authToken) {
    console.error("❌ No auth token found");
    window.location.href = "/login.html";
    return;
  }

  try {
    // Mostrar usuario
    if (userDisplay && username) {
      userDisplay.textContent = `Logged in as ${username}`;
    }

    // Registrar listener del formulario
    if (form) {
      form.addEventListener("submit", handleFormSubmit);
      console.log("✓ Form listener registered");
    } else {
      console.error("❌ Form element not found!");
    }

    // Cargar items
    console.log("Loading items...");
    await loadItems();
    console.log("✓ Items loaded:", items.length);
    
    // Cargar ventas (esto también carga reporte y actualiza gráficos)
    console.log("Loading sales...");
    await loadSales();
    console.log("✓ Sales loaded:", sales.length);
    
    console.log("=== App Ready ===");
  } catch (error) {
    console.error("❌ Initialization error:", error);
    showToast("Error: " + error.message, "error");
  }
}

async function handleFormSubmit(event) {
  event.preventDefault();
  console.log("Form submit intercepted");
  const item = getFormData();
  if (!item.name || !item.sku || !item.location) {
    showToast("Nombre, SKU y ubicación son requeridos", "error");
    return;
  }
  try {
    await saveItem(item);
    resetForm();
    syncUI();
    showToast(item.id ? "Producto actualizado exitosamente" : "Producto agregado exitosamente", "success");
  } catch (error) {
    console.error(error);
    showToast("Error al guardar. Verifica la conexión con el servidor.", "error");
  }
}

// Register Service Worker for PWA
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/service-worker.js")
      .then((registration) => {
        registration.update();

        if (registration.waiting) {
          registration.waiting.postMessage({ type: "SKIP_WAITING" });
        }

        registration.addEventListener("updatefound", () => {
          const newWorker = registration.installing;
          if (!newWorker) return;
          newWorker.addEventListener("statechange", () => {
            if (newWorker.state === "installed" && navigator.serviceWorker.controller) {
              newWorker.postMessage({ type: "SKIP_WAITING" });
            }
          });
        });

        console.log("✓ Service Worker registered:", registration);
      })
      .catch((error) => {
        console.warn("Service Worker registration failed:", error);
      });

    navigator.serviceWorker.getRegistrations().then((registrations) => {
      registrations.forEach((registration) => registration.update());
    });
  });

  navigator.serviceWorker.addEventListener("controllerchange", () => {
    window.location.reload();
  });
}

// Ejecutar cuando el DOM esté listo
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initializeApp);
} else {
  initializeApp();
}
