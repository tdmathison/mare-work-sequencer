import {Compartment, EditorSelection, EditorState, Transaction} from '@codemirror/state';
import {EditorView, keymap, lineNumbers, drawSelection} from '@codemirror/view';
import {history, historyKeymap, defaultKeymap, undo, redo, undoDepth, redoDepth, isolateHistory} from '@codemirror/commands';
import {syntaxHighlighting} from '@codemirror/language';
import {languages} from '@codemirror/language-data';
const backend=new Set(['ipv4','ipv6','all-ips','cidrs','domains','ips-domains','urls','emails','non-routable','ip-sort','defang','refang','json','xml','python']);
export function mountTextTool({theme,highlighting}){
 const root=document.querySelector('[data-text-tool]');if(root.dataset.initialized)return;root.dataset.initialized='true';
 const wrap=new Compartment(),language=new Compartment(),status=root.querySelector('[role=status]'),counts=root.querySelector('[data-counts]');
 const undoButton=root.querySelector('[data-action=undo]'),redoButton=root.querySelector('[data-action=redo]');
 const refresh=()=>{undoButton.disabled=!undoDepth(view.state);redoButton.disabled=!redoDepth(view.state);counts.textContent=`${view.state.doc.lines} lines · ${view.state.doc.length} characters`;};
 const view=new EditorView({parent:root.querySelector('[data-text-editor]'),state:EditorState.create({extensions:[history({minDepth:200}),keymap.of([...historyKeymap,...defaultKeymap]),lineNumbers(),drawSelection(),theme,syntaxHighlighting(highlighting),wrap.of(EditorView.lineWrapping),language.of([]),EditorView.updateListener.of(refresh)]})});
 root.textView=view;refresh();let busy=false;
 function apply(text){
  const selection=view.state.selection.ranges.map(range=>({anchor:Math.min(range.anchor,text.length),head:Math.min(range.head,text.length)}));
  view.dispatch({changes:{from:0,to:view.state.doc.length,insert:text},selection:EditorSelection.create(selection.map(range=>EditorSelection.range(range.anchor,range.head)),view.state.selection.mainIndex),annotations:[isolateHistory.of('full'),Transaction.userEvent.of('input.transform')],scrollIntoView:false});
 }
 async function run(operation){
  if(busy)return;const before=view.state.doc;const text=before.toString();
  if(new TextEncoder().encode(text).length>2*1024*1024){status.textContent='Text exceeds the 2 MiB processing limit.';return;}
  busy=true;root.querySelectorAll('[data-command]').forEach(button=>button.disabled=true);status.textContent='Processing…';
  try{
   let result;
   if(backend.has(operation)){
    const body=new FormData();body.set('text',text);body.set('operation',operation);body.set('csrf',root.dataset.csrf);
    const response=await fetch(root.dataset.endpoint,{method:'POST',body,redirect:'error'});result=await response.json();if(!response.ok)throw Error(result.error||'Unable to process text.');
   }else result=await new Promise((resolve,reject)=>{
    const worker=new Worker(root.dataset.worker);const timer=setTimeout(()=>{worker.terminate();reject(Error('Operation exceeded 2 seconds. Simplify the expression or use less text.'));},2000);
    const finish=()=>{clearTimeout(timer);worker.terminate();};worker.onmessage=({data})=>{finish();data.error?reject(Error(data.error)):resolve(data);};worker.onerror=()=>{finish();reject(Error('Unable to process text.'));};worker.postMessage({operation,text,pattern:root.querySelector('[data-pattern]').value});
   });
   if(view.state.doc!==before)throw Error('Text changed while processing. Run the command again.');
   apply(result.text);
   if(['json','xml','python'].includes(operation)){
    const mode=languages.find(item=>item.name.toLowerCase()===operation);if(mode){const support=await mode.load();view.dispatch({effects:language.reconfigure(support)});}
   }
   status.textContent=result.warning||'Done.';
  }catch(error){status.textContent=error.message;}
  finally{busy=false;root.querySelectorAll('[data-command]').forEach(button=>button.disabled=false);refresh();}
 }
 root.querySelectorAll('[data-command]').forEach(button=>button.addEventListener('click',()=>run(button.dataset.command)));
 undoButton.addEventListener('click',()=>{undo(view);refresh();});redoButton.addEventListener('click',()=>{redo(view);refresh();});
 root.querySelector('[data-action=clear]').addEventListener('click',()=>apply(''));
 root.querySelector('[data-action=copy]').addEventListener('click',async()=>{try{await navigator.clipboard.writeText(view.state.doc.toString());status.textContent='Copied.';}catch(error){status.textContent='Clipboard unavailable. Select and copy the text manually.';}});
 root.querySelector('[data-wrap]').addEventListener('change',event=>view.dispatch({effects:wrap.reconfigure(event.target.checked?EditorView.lineWrapping:[])}));
 new ResizeObserver(()=>view.requestMeasure()).observe(root);
}
