const {test}=require('node:test');
const assert=require('node:assert/strict'), fs=require('node:fs'), ts=require('typescript');
const React=require('react'), {renderToStaticMarkup}=require('react-dom/server');
const page={};
const compiled=ts.transpileModule(fs.readFileSync('src/pages/ImportedContextPage.tsx','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
new Function('require','exports',compiled)(id=>{
 if(id.endsWith('.css') || id.includes('api/adapter'))return {};
 if(id.includes('candidatePresentation'))return {safeSourceUrl:s=>/^https?:\/\//.test(s)?s:undefined};
 return require(id);
},page);
test('table renders mocked audit rows, badges and safe links without mutation controls',()=>{
 const row={id:'row',display_name:'Cooling plant',dataset_name:'epoch',source_file_basename:'chillers.csv',row_number:3,record_type:'equipment',duplicate_status:'possible_duplicate',warnings_json:['warning'],errors_json:['error'],source_urls_json:['https://example.org','javascript:alert(1)'],created_at:'2026-09-22',linked_project_candidate_id:'candidate'};
 const html=renderToStaticMarkup(React.createElement(page.ContextTable,{rows:[row],onDetail:()=>{}}));
 for(const text of ['Cooling plant','chillers.csv','equipment','possible_duplicate','1 warnings','1 errors','Not a Project','Linked candidate']) assert(html.includes(text));
 assert(!html.includes('javascript:'));
 assert(!/>(Promote|Verify|Admit|Save|Delete|Create|Ingest)</i.test(html));
});
test('summary renders mocked API counts and recent window',()=>{
 const summary={total:100,counts_by_dataset_name:{epoch_ai:80,other:20},recent_window_days:7,recent_row_count:10,rows_with_warnings:2,rows_with_errors:1,linked_candidate_count:3};
 const html=renderToStaticMarkup(React.createElement(page.ContextSummaryCards,{summary}));
 for(const text of ['100','80','Imported in last 7 days','Rows with warnings','Linked to candidates']) assert(html.includes(text));
});
test('page renders read-only filters and loading state, with registered route',()=>{
 const html=renderToStaticMarkup(React.createElement(page.ImportedContextPage));
 for(const text of ['Imported Context','Dataset','Source file','Search','Loading context rows']) assert(html.includes(text));
 assert(!/>(Promote|Verify|Admit|Save|Delete|Create|Ingest)</i.test(html));
 assert(fs.readFileSync('src/App.tsx','utf8').includes('path="/imported-context" element={<ImportedContextPage />}'));
});
