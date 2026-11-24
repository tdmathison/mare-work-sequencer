const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
let now=0,nextID=0,remote=true,remoteIdentity='alice',fail=false;
const timers=new Map(),listeners={},countdowns=[];
const context={window:{MWS:{path:p=>p},addEventListener:(name,fn)=>listeners[name]=fn},
 document:{body:{dataset:{autosaveMinutes:'1',autosaveEnabled:'1',userLayout:'alice'}},hidden:false,addEventListener:(name,fn)=>listeners[name]=fn},
 Date:{now:()=>now},setInterval:fn=>{timers.set(++nextID,fn);return nextID;},clearInterval:id=>timers.delete(id),
 fetch:async()=>{if(fail)throw Error('offline');return {ok:true,redirected:false,json:async()=>({enabled:remote,user_uuid:remoteIdentity})};}};
vm.runInNewContext(fs.readFileSync('static/autosave.js','utf8'),context);
const auto=context.window.MareAutosave;
let first=0,second=0,canceled=0,finish;
auto.register({canSave:()=>true,save:()=>{first++;return new Promise(r=>finish=r);},onEnabledChange:()=>canceled++,onCountdown:(...args)=>countdowns.push(args)});
auto.register({canSave:()=>true,save:async()=>second++});
(async()=>{
 assert.equal(timers.size,1);now=60000;const submitted=[...timers.values()][0]();assert.equal(first,1);
 remote=false;await auto.synchronize();assert.equal(auto.enabled,false);assert.equal(timers.size,0);
 assert.equal(countdowns.at(-1)[1],true,'in-flight saves remain reported as running');
 finish();await submitted;assert.equal(first,1);assert.equal(second,0,'queued second editor must not save');
 assert.equal(countdowns.at(-1)[3],'Autosave disabled');assert.ok(canceled>0);
 // Explicit save handlers are independent of this automatic scheduler.
 const manual=()=>second++;manual();assert.equal(second,1);
 now=120000;remote=true;await auto.synchronize();assert.equal(first,1,'enabling does not save immediately');assert.equal(timers.size,1);
 await auto.synchronize();await auto.synchronize();assert.equal(timers.size,1,'activation must not duplicate schedules');
 now=179999;await [...timers.values()][0]();assert.equal(first,1);
 now=180000;const resumed=[...timers.values()][0]();assert.equal(first,2);finish();await resumed;assert.equal(second,2);
 remoteIdentity='bob';await auto.synchronize();assert.equal(auto.enabled,false);assert.equal(timers.size,0,'old document must not adopt a different account preference');
 remoteIdentity='alice';fail=true;await auto.synchronize();assert.equal(auto.enabled,false);
 fail=false;await listeners.focus();assert.equal(auto.enabled,true);assert.equal(timers.size,1);
 console.log('PASS: disable, queued/in-flight saves, manual independence, resume, one schedule, identity and offline checks');
})().catch(error=>{console.error(error);process.exitCode=1;});
