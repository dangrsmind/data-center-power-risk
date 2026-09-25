const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'), ts = require('typescript');
const exports_ = {};
new Function('exports', ts.transpileModule(fs.readFileSync('src/config/candidateResolution.ts', 'utf8'),
 {compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText)(exports_);
test('default view excludes placeholders, context, low confidence and unknown classifications', () => {
 for (const value of ['unresolved_placeholder','context_only_or_supporting','low_confidence','exception_review','already_promoted',undefined])
   assert.equal(exports_.matchesResolution(value,'reviewable'),false);
 for (const value of exports_.REVIEWABLE_CLASSES)
   assert.equal(exports_.matchesResolution(value,'reviewable'),true);
});
test('excluded rows remain accessible through all and class filters', () => {
 for (const value of exports_.RESOLUTION_CLASSES) {
   assert.equal(exports_.matchesResolution(value,'all'),true);
   assert.equal(exports_.matchesResolution(value,value),true);
 }
 assert.equal(exports_.matchesResolution('low_confidence','unresolved_placeholder'),false);
});
