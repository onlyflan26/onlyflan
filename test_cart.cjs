const vm = require('node:vm');
const fs = require('node:fs');
const assert = require('node:assert/strict');
class Element {
  constructor() { this.children = []; this.events = {}; this.value = ''; this.dataset = {}; this.classList = {add(){}, remove(){}}; }
  append(...items) { this.children.push(...items); }
  replaceChildren() { this.children = []; }
  setAttribute() {}
  addEventListener(name, callback) { this.events[name] = callback; }
  showModal() {}
  close() {}
}
async function main() {
  const ids = Object.fromEntries(['cart-dialog','cart-items','toast','cart-total','cart-count','checkout-button','customer-name','cart-error','checkout'].map(id => [id, new Element()]));
  const add = new Element(); add.dataset.add = '1';
  const checkbox = new Element(); checkbox.checked = false;
  const open = new Element(), close = new Element();
  let extra = '10.00', destination;
  const context = {
    document: {
      body: {style: {}}, getElementById: id => ids[id], createElement: () => new Element(),
      querySelectorAll: selector => selector === '[data-add]' ? [add] : [],
      querySelector: selector => selector === '[data-open-cart]' ? open : selector === '[data-close-cart]' ? close : checkbox,
    },
    localStorage: {getItem: () => '{"1":1}', setItem(){}},
    fetch: async () => ({ok: true, json: async () => ({whatsapp: '59157002285', products: [{id:1,name:'Vainilla',price:'70.00',decoration_price:extra,image:'/test.png'}]})}),
    window: {location: {assign: value => destination = value}}, setTimeout: () => 1, clearTimeout(){}, console,
  };
  vm.runInNewContext(fs.readFileSync('assets/app.js','utf8'), context);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(ids['cart-total'].textContent, 'Bs 70', 'carrito anterior conservado');
  checkbox.checked = true;
  await add.events.click(); await add.events.click();
  assert.equal(ids['cart-items'].children.length, 2, 'clásico y decorado separados');
  assert.equal(ids['cart-total'].textContent, 'Bs 230', '70 + 2 × 80');
  ids['customer-name'].value = 'Prueba';
  await ids.checkout.events.submit({preventDefault(){}});
  const message = new URL(destination).searchParams.get('text');
  assert.match(message, /2 × Vainilla · Más decorado — Bs 160/);
  assert.match(message, /decoración \+ Bs 10 por unidad/);
  assert.match(message, /Total de productos: Bs 230/);
  destination = undefined; extra = '15.00';
  await ids.checkout.events.submit({preventDefault(){}});
  assert.equal(destination, undefined, 'cambio de recargo requiere revisión');
  assert.equal(ids['cart-total'].textContent, 'Bs 240');
  extra = null;
  await open.events.click();
  assert.equal(ids['cart-total'].textContent, 'Bs 70', 'desactivar decoración retira solo decorados');
  console.log('OK: variantes, cantidades, recargo, WhatsApp, cambio de precio y desactivación.');
}
main().catch(error => {console.error(error); process.exitCode=1;});
