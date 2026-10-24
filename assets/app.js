'use strict';
document.querySelectorAll('form[data-confirm]').forEach(form => form.addEventListener('submit', event => { if (!confirm(form.dataset.confirm)) event.preventDefault(); }));
const dialog = document.getElementById('cart-dialog');
if (dialog) {
  const money = cents => 'Bs ' + (cents / 100).toLocaleString('es-BO', {maximumFractionDigits: 2});
  let products = [], whatsapp = '', ready = false, busy = false, toastTimer;
  let cart = {};
  try {
    const saved = JSON.parse(localStorage.getItem('onlyflan-cart') || '{}');
    if (saved && typeof saved === 'object' && !Array.isArray(saved)) Object.entries(saved).forEach(([id, quantity]) => {
      if (/^\d+(?::d)?$/.test(id) && Number.isInteger(quantity) && quantity > 0 && quantity <= 99) cart[id] = quantity;
    });
  } catch (_) { /* A cart also works when local storage is unavailable. */ }
  const toast = message => {
    const node = document.getElementById('toast'); node.textContent = message; node.classList.add('visible');
    clearTimeout(toastTimer); toastTimer = setTimeout(() => node.classList.remove('visible'), 3000);
  };
  function persist() { try { localStorage.setItem('onlyflan-cart', JSON.stringify(cart)); } catch (_) {} }
  async function refresh() {
    const response = await fetch('/api/catalogo', {cache: 'no-store'});
    if (!response.ok) throw new Error('No se pudo actualizar el catálogo. Inténtalo de nuevo.');
    const data = await response.json(); products = data.products.map(p => ({...p, cents: Math.round(Number(p.price) * 100), extra: p.decoration_price === null ? null : Math.round(Number(p.decoration_price) * 100)})); whatsapp = data.whatsapp;
    let changed = false;
    Object.keys(cart).forEach(id => { if (!findProduct(id) || (isDecorated(id) && findProduct(id).extra === null)) { delete cart[id]; changed = true; } });
    ready = true; persist(); render(); return changed;
  }
  const isDecorated = id => String(id).endsWith(':d');
  const findProduct = id => products.find(p => p.id === Number(String(id).split(':')[0]));
  const unitPrice = (p, id) => p.cents + (isDecorated(id) ? p.extra : 0);
  const variantName = (p, id) => p.name + (isDecorated(id) ? ' · Más decorado' : ' · Clásico');
  const priceSnapshot = () => JSON.stringify(products.map(p => [p.id, p.cents, p.extra]));
  function node(tag, text, cls) { const el = document.createElement(tag); if (text !== undefined) el.textContent = text; if (cls) el.className = cls; return el; }
  function render() {
    const root = document.getElementById('cart-items'); root.replaceChildren(); let total = 0, count = 0;
    Object.entries(cart).forEach(([id, quantity]) => {
      const p = findProduct(id); if (!p) return;
      const unit = unitPrice(p, id), title = variantName(p, id);
      count += quantity; total += quantity * unit;
      const row = node('div', undefined, 'cart-item'); const image = node('img'); image.src = p.image; image.alt = p.name;
      const info = node('div'); info.append(node('h3', title), node('p', money(unit)));
      if (isDecorated(id)) info.append(node('p', `Incluye Más decorado: + ${money(p.extra)} por unidad`));
      const controls = node('div', undefined, 'quantity');
      for (const delta of [-1, 1]) {
        const button = node('button', delta < 0 ? '−' : '+'); button.type = 'button'; button.setAttribute('aria-label', (delta < 0 ? 'Reducir ' : 'Aumentar ') + title);
        button.addEventListener('click', () => { const next = cart[id] + delta; if (next > 99) {toast('Máximo 99 unidades por sabor.'); return;} if (next < 1) delete cart[id]; else cart[id] = next; persist(); render(); });
        controls.append(button); if (delta < 0) controls.append(node('span', String(quantity)));
      }
      info.append(controls); const side = node('div'); side.append(node('p', money(unit * quantity)));
      const remove = node('button', 'Quitar', 'remove'); remove.type = 'button'; remove.setAttribute('aria-label', 'Quitar ' + title); remove.onclick = () => {delete cart[id]; persist(); render();}; side.append(remove);
      row.append(image, info, side); root.append(row);
    });
    if (!count) root.append(node('p', ready ? 'Tu carrito está esperando algo dulce. Elige tus sabores favoritos.' : 'Cargando catálogo…', 'empty'));
    document.getElementById('cart-total').textContent = money(total); document.getElementById('cart-count').textContent = String(count);
    document.getElementById('checkout-button').disabled = !count || busy;
  }
  document.querySelectorAll('[data-add]').forEach(button => button.addEventListener('click', async () => {
    button.disabled = true;
    try {
      await refresh(); const productId = button.dataset.add;
      const decorated = document.querySelector(`[data-decoration="${productId}"]`)?.checked;
      const id = productId + (decorated ? ':d' : '');
      const product = findProduct(id);
      if (decorated && product?.extra === null) {toast('La decoración adicional ya no está disponible. Recarga el catálogo.'); return;}
      if (!product) {toast('Este producto ya no está disponible.'); return;}
      if ((cart[id] || 0) >= 99) {toast('Máximo 99 unidades por sabor.'); return;}
      cart[id] = (cart[id] || 0) + 1; persist(); render(); toast('Agregado a tu carrito ♡');
    } catch (error) {toast(error.message);} finally {button.disabled = false;}
  }));
  document.querySelector('[data-open-cart]').addEventListener('click', async () => {
    dialog.showModal(); document.body.style.overflow = 'hidden'; render();
    try {const changed = await refresh(); if (changed) toast('Retiramos del carrito los productos agotados.');} catch (error) {document.getElementById('cart-error').textContent = error.message;}
  });
  document.querySelector('[data-close-cart]').onclick = () => dialog.close();
  dialog.addEventListener('close', () => {document.body.style.overflow = '';});
  document.getElementById('checkout').addEventListener('submit', async event => {
    event.preventDefault(); if (busy) return;
    const name = document.getElementById('customer-name').value.trim(); if (!name) {document.getElementById('customer-name').focus(); return;}
    const errorNode = document.getElementById('cart-error'); errorNode.textContent = ''; const previous = priceSnapshot(); busy = true; render();
    try {
      const changed = await refresh();
      if (changed || previous !== priceSnapshot()) {errorNode.textContent = 'El catálogo cambió. Revisa las cantidades y el total antes de volver a pedir.'; return;}
      const selected = Object.entries(cart).map(([id, quantity]) => ({id, quantity, product: findProduct(id)})).filter(item => item.product); if (!selected.length) return;
      const lines = selected.map(({id, quantity, product: p}) => `• ${quantity} × ${variantName(p, id)} — ${money(quantity * unitPrice(p, id))}${isDecorated(id) ? ` (incluye decoración + ${money(p.extra)} por unidad)` : ''}`);
      const total = selected.reduce((sum, {id, quantity, product: p}) => sum + quantity * unitPrice(p, id), 0);
      const message = `¡Hola, ONLYFLAN! Soy ${name}. Quisiera pedir:\n\n${lines.join('\n')}\n\nTotal de productos: ${money(total)}\n\nQuisiera coordinar el pago y la entrega en La Paz.`;
      window.location.assign(`https://wa.me/${whatsapp}?text=${encodeURIComponent(message)}`);
    } catch (error) {errorNode.textContent = error.message;} finally {busy = false; render();}
  });
  refresh().catch(() => {render(); toast('No se pudo cargar el catálogo. Revisa tu conexión.');});
}
