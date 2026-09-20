const test = require('node:test');
const assert = require('node:assert/strict');
const {chartCursor} = require('../chart_interaction.js');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

test('touch interaction cancels native selection and tracks the captured finger', () => {
  const events = {};
  let captured = null;
  const overlay = {setAttribute() {}, querySelector: () => ({setAttribute() {}})};
  const container = {querySelector: selector => selector === '.chart-inspect' ? {textContent: '提示'} : null, addEventListener: (name, fn) => {events[name] = fn;}};
  const svg = {dataset: {candles: '[]'}, closest: () => container, querySelector: () => overlay,
    addEventListener: (name, fn) => {events[name] = fn;}, getScreenCTM: () => null,
    setPointerCapture: id => {captured = id;}};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../chart_interaction.js'), 'utf8'),
    {document: {querySelectorAll: () => [svg]}, window: {matchMedia: () => ({matches: false})}});
  const touch = new Event('pointerdown', {cancelable: true});
  Object.assign(touch, {pointerType: 'touch', pointerId: 7});
  events.pointerdown(touch);
  assert.equal(touch.defaultPrevented, true);
  assert.equal(captured, 7);
  const menu = new Event('contextmenu', {cancelable: true});
  events.contextmenu(menu);
  assert.equal(menu.defaultPrevented, true);
});

test('pointer selects corresponding candle and inverse price coordinate', () => {
  assert.deepEqual(chartCursor(64, 50, 120, 10, 30), {index: 0, price: 30});
  assert.deepEqual(chartCursor(514, 200, 120, 10, 30), {index: 60, price: 20});
  assert.deepEqual(chartCursor(964, 350, 120, 10, 30), {index: 119, price: 10});
});

test('outside plot or empty chart must not show stale candle information', () => {
  assert.equal(chartCursor(63, 200, 120, 10, 30), null);
  assert.equal(chartCursor(100, 351, 120, 10, 30), null);
  assert.equal(chartCursor(100, 200, 0, 10, 30), null);
});
