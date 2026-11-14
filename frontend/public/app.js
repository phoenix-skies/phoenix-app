const session = localStorage.getItem("phoenix-session") || Math.random().toString(36).slice(2);
try { localStorage.setItem("phoenix-session", session); } catch (e) {}
let products = [];
let activeCategory = "All";

const inr = (n) => n.toLocaleString("en-IN");

async function api(path, opts) {
  const res = await fetch(path, opts);
  if (!res.ok) throw new Error(`${res.status} on ${path}`);
  return res.json();
}

function renderFilters() {
  const cats = ["All", ...new Set(products.map((p) => p.category))];
  document.getElementById("filters").innerHTML = cats
    .map((c) => `<button class="${c === activeCategory ? "active" : ""}" data-cat="${c}">${c}</button>`)
    .join("");
  document.querySelectorAll("#filters button").forEach((b) =>
    b.addEventListener("click", () => { activeCategory = b.dataset.cat; renderFilters(); renderGrid(); }));
}

function renderGrid() {
  const list = activeCategory === "All" ? products : products.filter((p) => p.category === activeCategory);
  document.getElementById("grid").innerHTML = list.map((p) => `
    <div class="card">
      <div class="cat">${p.category}</div>
      <h3>${p.name}</h3>
      <div class="price">₹${inr(p.price)}</div>
      <button data-id="${p.id}">Add to cart</button>
    </div>`).join("");
  document.querySelectorAll("#grid button").forEach((b) =>
    b.addEventListener("click", () => addToCart(Number(b.dataset.id))));
}

async function loadCart() {
  const cart = await api(`/api/cart/${session}`);
  document.getElementById("cart").innerHTML = cart.items
    .map((i) => `<li><span>${i.name} × ${i.quantity}</span><span>₹${inr(i.price * i.quantity)}</span></li>`).join("")
    || "<li>Cart is empty</li>";
  document.getElementById("total").textContent = inr(cart.total);
}

async function addToCart(id) {
  await api(`/api/cart/${session}`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ product_id: id, quantity: 1 }),
  });
  loadCart();
}

async function init() {
  try {
    const [fe, be] = await Promise.all([
      fetch("version.json").then((r) => r.json()).catch(() => ({ version: "local" })),
      api("/api/version"),
    ]);
    document.getElementById("versions").textContent = `frontend ${fe.version} · api ${be.version}`;
    const env = (window.location.hostname.match(/(dev|qa|prod)/) || [])[1];
    document.getElementById("env").textContent = (env || "phoenix").toUpperCase();
    products = await api("/api/products");
    renderFilters(); renderGrid(); loadCart();
  } catch (e) {
    document.getElementById("error").textContent = "Could not reach the product API: " + e.message;
  }
}
init();
