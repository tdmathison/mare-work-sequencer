const assert=require('node:assert/strict');
const {model}=require('../../static/backup-import.js');
const input={records:[
 {category:'cases',identifier:'CASE-1',name:'New case',action:'added'},
 {category:'cases',identifier:'CASE-2',name:'New revision',action:'updated'},
 {category:'cases',identifier:'CASE-3',name:'Duplicate',action:'skipped'},
 {category:'tags',identifier:'tag-1',name:'Confirmed tag',action:'unchanged'},
 {category:'tags',identifier:'tag-2',name:'New tag',action:'added'},
 {category:'actors',identifier:'actor-1',name:'Actor added',action:'added'},
 {category:'actors',identifier:'actor-2',name:'Actor conflict',action:'conflict'},
 {category:'families',identifier:'family-1',name:'Family error',action:'error'},
 {category:'families',identifier:'family-2',name:'Unrecorded',action:'unknown'},
]};
const original=JSON.stringify(input),m=model({areas:['cases','tags','actors','families']},input);
assert.deepEqual(m.included,['cases','tags','actors','families']);
assert.deepEqual(m.totals,{processed:8,added:3,unchanged:1,skipped:1,updated:1,replaced:0,conflict:1,error:1,not_processed:1});
assert.equal(m.records.length,m.totals.processed+m.totals.not_processed);
assert.equal(JSON.stringify(input),original,'Presentation must preserve original results');
assert.deepEqual(model({areas:['tags']},{}).included,['tags']);
assert.deepEqual(model({},{}).included,[]);
assert.equal(model({}, {added:100}).totals.added,0,'Old aggregates cannot fabricate per-record success');
assert.equal(model({}, {records:[{category:'cases',action:'replaced'}]}).totals.replaced,1);
const collections=model({areas:['task_collections']},{records:[{category:'task_collections',identifier:'collection-1',name:'Guidance',action:'added'}]});assert.deepEqual(collections.included,['task_collections']);assert.equal(collections.totals.added,1);
console.log('Import presentation adapter: all categories, exact totals, duplicates, updates, errors, empty and legacy results passed.');
