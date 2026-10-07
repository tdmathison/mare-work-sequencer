(()=>{
const interval=Number(document.body.dataset.autosaveMinutes||5)*60000,entries=[];
function display(entry){if(entry.onCountdown)entry.onCountdown(Math.max(0,Math.ceil((entry.next-Date.now())/1000)),entry.running,!entry.canSave());}
window.MareAutosave={register(options){const entry={...options,next:Date.now()+interval,running:false};entries.push(entry);display(entry);return {reset(){entry.next=Date.now()+interval;display(entry);}};}};
async function tick(){const now=Date.now();for(const entry of entries){display(entry);if(entry.running||now<entry.next)continue;if(!entry.canSave()){entry.next=now+interval;display(entry);continue;}entry.running=true;display(entry);try{await entry.save();}catch(error){entry.onError(error);}finally{entry.running=false;entry.next=Date.now()+interval;display(entry);}}}
setInterval(tick,1000);document.addEventListener('visibilitychange',()=>{if(!document.hidden)tick();});
})();
