const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
// Exercise the actual pure TypeScript helpers without adding a test dependency.
const source = fs.readFileSync(path.join(__dirname, '../src/config/mapPresentation.ts'), 'utf8');
const helpers = {};
new Function('exports', ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText)(helpers);
const { MAP_LAYERS, defaultMapLayers, classifyMapRecord, mapLayerCounts, visibleMapRecords, tierColor } = helpers;
const record = (fields = {}, tier = null) => ({ project: { latitude: 37, longitude: -78, risk_tier: 'low', coordinate_status: 'verified', coordinate_precision: 'exact_site', coordinate_confidence: 0.8, ...fields }, signal: tier ? { risk_signal_tier: tier } : null });

test('layer model supplies defaults, semantics and unique ids', () => {
  assert.equal(new Set(MAP_LAYERS.map(l => l.id)).size, 5);
  for (const layer of MAP_LAYERS) {
    assert(layer.label && layer.description && layer.color);
    assert.equal(defaultMapLayers()[layer.id], layer.enabledDefault);
  }
  assert.equal(defaultMapLayers().projects, true);
});
test('classification uses explicit evidence, risk and coordinate fields independently', () => {
  assert.deepEqual(classifyMapRecord(record()), { projects: true, risk: false, high_signal: false, verified: true, incomplete: false });
  const flags = classifyMapRecord(record({ risk_tier: 'high', coordinate_precision: 'approximate' }, 'high'));
  assert(flags.risk && flags.high_signal && flags.verified && flags.incomplete);
  assert.equal(classifyMapRecord(record({}, 'moderate')).high_signal, false);
  for (const risk_tier of ['elevated', 'medium', 'moderate']) assert(classifyMapRecord(record({ risk_tier })).risk);
});
test('unknown, invalid and low confidence remain conservative', () => {
  for (const coordinate_confidence of [null, undefined, NaN, -1, 0.49, 1.1]) assert(classifyMapRecord(record({ coordinate_confidence })).incomplete);
  assert.equal(classifyMapRecord(record({ coordinate_confidence: 0.5 })).incomplete, false);
  assert(classifyMapRecord(record({ coordinate_status: null })).incomplete);
  assert(classifyMapRecord(record({ coordinate_precision: null })).incomplete);
});
test('counts exclude unmappable and hidden approximate records; categories can overlap', () => {
  const items = [record({}, 'high'), record({ coordinate_precision: 'approximate', risk_tier: 'high' }, 'high'), record({ latitude: null }), record({ latitude: 91 }), record({ coordinate_status: 'missing' })];
  assert.deepEqual(mapLayerCounts(items, true), { projects: 2, risk: 1, high_signal: 2, verified: 2, incomplete: 1 });
  assert.deepEqual(mapLayerCounts(items, false), { projects: 1, risk: 0, high_signal: 1, verified: 1, incomplete: 0 });
  assert.equal(mapLayerCounts([], true).projects, 0);
});
test('master visibility hides markers; overlay toggles do not filter projects', () => {
  const items = [record(), record({ longitude: null }), record({ coordinate_precision: 'approximate' })];
  const layers = defaultMapLayers();
  assert.equal(visibleMapRecords(items, true, layers).length, 2);
  assert.equal(visibleMapRecords(items, false, layers).length, 1);
  layers.high_signal = false; layers.verified = false;
  assert.equal(visibleMapRecords(items, true, layers).length, 2);
  layers.projects = false;
  assert.deepEqual(visibleMapRecords(items, true, layers), []);
  assert.equal(mapLayerCounts(items, true).projects, 2);
});
test('risk colors never imply approval from a low or unknown risk tier', () => {
  assert.equal(tierColor('high'), 'var(--map-hot)');
  for (const tier of ['medium', 'moderate', 'elevated']) assert.equal(tierColor(tier), 'var(--map-amber)');
  for (const tier of [null, 'low', 'unknown']) assert.equal(tierColor(tier), 'var(--map-slate)');
});
