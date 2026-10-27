const assert=require('node:assert/strict'),arrange=require('../../static/explorer-layout-worker.js');
const nodes=[{id:'c1',kind:'case'},{id:'c2',kind:'case'},{id:'f',kind:'family'},{id:'a',kind:'actor'},{id:'orphan',kind:'actor'},{id:'cat',kind:'category',caseNode:'c1'}];
const edges=[{source:'c1',target:'f'},{source:'c2',target:'f'},{source:'f',target:'a'},{source:'a',target:'c1'},{source:'c1',target:'cat'}];
for(const mode of ['tree','radial','clusters'])for(const spacing of ['compact','balanced','spacious']){
 const input={nodes,edges,mode,center:'c1',settings:{spacing,direction:'tb',center:'selected'}};
 const result=arrange(input);assert.deepEqual(Object.keys(result).sort(),nodes.map(n=>n.id).sort());assert.deepEqual(result,arrange(input));assert.ok(Object.values(result).every(p=>Number.isFinite(p.x)&&Number.isFinite(p.y)));
 assert.ok(Math.hypot(result.orphan.x-result.a.x,result.orphan.y-result.a.y)>100);
 if(mode==='tree')assert.ok(result.c1.y<result.f.y&&result.f.y<result.a.y);
 if(mode==='radial')assert.ok(Math.abs(Math.hypot(result.f.x-result.c1.x,result.f.y-result.c1.y)-Math.hypot(result.a.x-result.c1.x,result.a.y-result.c1.y))<.001);
}
for(const mode of ['tree','radial','clusters']){
 assert.deepEqual(arrange({nodes:[],edges:[],mode,settings:{}}),{});
 assert.equal(Object.keys(arrange({nodes:[{id:'one',kind:'actor'}],edges:[],mode,settings:{}})).length,1);
 const large=Array.from({length:400},(_,i)=>({id:'node'+i,kind:['case','family','actor'][i%3]}));const links=large.slice(1).map((n,i)=>({source:large[i].id,target:n.id}));
 const start=Date.now();assert.equal(Object.keys(arrange({nodes:large,edges:links,mode,settings:{}})).length,400);assert.ok(Date.now()-start<5000);
}
console.log('PASS deterministic layouts: shared nodes, cycles, disconnected components, category leaves, spacing, empty/single and 400-node graphs.');
