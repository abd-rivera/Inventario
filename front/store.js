const API_BASE = "/api";
const storeGrid = document.getElementById("storeGrid");
const storeSearch = document.getElementById("storeSearch");
const storeCount = document.getElementById("storeCount");
const storeStatus = document.getElementById("storeStatus");

const WHATSAPP_NUMBER = ""; // example: 50760000000

const currency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
});

let items = [];

function setStatus(message, type = "") {
  if (!storeStatus) return;
  storeStatus.textContent = message;
  storeStatus.className = `store-status ${type}`.trim();
}

function formatCount(count) {
  return `${count} producto${count === 1 ? "" : "s"}`;
}

function buildWhatsAppLink(item) {
  const message = `Hola, quiero comprar: ${item.name} - ${currency.format(item.price)}`;
  return `https://wa.me/${WHATSAPP_NUMBER}?text=${encodeURIComponent(message)}`;
}

function buildCard(item) {
  const disabled = !WHATSAPP_NUMBER;
  const actionLabel = disabled ? "Configurar WhatsApp" : "Agregar al carrito";
  const actionAttrs = disabled
    ? "disabled aria-disabled='true'"
    : `data-link='${buildWhatsAppLink(item)}'`;
  const lowStock = item.quantity <= 3;
  const stockTag = lowStock ? "Quedan pocos" : "Disponible";
  const description = item.description ? item.description.slice(0, 80) : "";
  const statusTag = item.status || "Nuevo";
  return `
    <article class="store-card">
      <div class="store-card-media">
        ${item.imageUrl ? `<img src="${item.imageUrl}" alt="${item.name}" />` : ""}
      </div>
      <h4>${item.name}</h4>
      ${description ? `<p class="store-card-desc">${description}</p>` : ""}
      <div class="store-card-price">${currency.format(item.price)}</div>
      <div class="store-card-meta">
        <span>${statusTag}</span>
        <span class="store-tag-pill ${lowStock ? "low" : ""}">${stockTag}</span>
      </div>
      <button class="store-action" ${actionAttrs}>
        ${actionLabel}
      </button>
    </article>`;
}

function renderGrid(list) {
  if (!storeGrid) return;
  if (!list.length) {
    storeGrid.innerHTML = "<div class='store-empty'>No hay productos disponibles.</div>";
    return;
  }
  storeGrid.innerHTML = list.map(buildCard).join("");
}

function renderItems() {
  const query = (storeSearch?.value || "").trim().toLowerCase();
  const filtered = items.filter((item) =>
    item.name.toLowerCase().includes(query)
  );

  storeCount.textContent = formatCount(filtered.length);

  renderGrid(filtered.slice(0, 5));
}

async function loadStoreItems() {
  setStatus("Cargando productos...");
  try {
    const response = await fetch(`${API_BASE}/store/items`);
    if (!response.ok) {
      throw new Error("No se pudieron cargar los productos.");
    }
    items = await response.json();
    setStatus(WHATSAPP_NUMBER ? "" : "Configura el numero de WhatsApp en store.js");
    renderItems();
  } catch (error) {
    console.error(error);
    setStatus("Error al cargar el catalogo.", "error");
  }
}

document.addEventListener("click", (event) => {
  const button = event.target.closest(".store-action");
  if (!button) return;
  const link = button.dataset.link;
  if (!link) return;
  window.open(link, "_blank");
});

storeSearch.addEventListener("input", renderItems);

loadStoreItems();
