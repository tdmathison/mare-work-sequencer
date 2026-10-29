import {createExplorer} from './developer-explorer';
import {languageService} from './developer-language';
import { EditorState, Compartment } from "@codemirror/state";
import { EditorView, keymap, lineNumbers, drawSelection, highlightActiveLine, highlightActiveLineGutter, tooltips } from "@codemirror/view";
import { history, defaultKeymap, historyKeymap, indentWithTab } from "@codemirror/commands";
import { languages } from "@codemirror/language-data";
import { LanguageDescription, syntaxHighlighting, bracketMatching, indentOnInput, foldGutter, foldKeymap, indentUnit } from "@codemirror/language";
import { search, searchKeymap, highlightSelectionMatches } from "@codemirror/search";

async function mountDeveloperEditor({theme,highlighting}) {
 const root=document.querySelector('[data-developer-editor]');if(!root)return;
 const layout=window.MareDeveloperWorkspace(root,'editor');
 const tooltipLayer=document.createElement('div');tooltipLayer.className='developer-tooltip-layer';document.body.append(tooltipLayer);
 const q=s=>root.querySelector(s),base=root.dataset.base,csrf=root.dataset.csrf,status=q('.ide-status'),tabs=q('.ide-tabs'),tree=q('[data-files]');
 const managementUrl=q('[data-management-link]').getAttribute('href');
 const buffers=new Map();let selected=null,plugin=null,current=null,permissions=[],view,language,saving,selectionGeneration=0,runId,running=false,activeConsole=['output','debug'].includes(layout.prefs.consoleTab)?layout.prefs.consoleTab:'output',historyIndex=Number.isInteger(window.history.state?.mareEditor?.index)?window.history.state.mareEditor.index:0,restoringHistory=false;
 const wrap=new Compartment(),indent=new Compartment(),access=new Compartment(),prefs={wrap:layout.prefs.wordWrap!==false,indent:'4'};
 const outputs={output:'',debug:''},consolePanel=q('.ide-console');
 function message(text){status.textContent=text;}
 function consoleOpen(open=true){root.classList.toggle('console-collapsed',!open);layout.save({consoleOpen:open});consolePanel.hidden=!open;q('[data-command=console]').setAttribute('aria-expanded',String(open));}
 function consoleTab(name){activeConsole=name;layout.save({consoleTab:name});for(const tab of root.querySelectorAll('[data-console-tab]')){const active=tab.dataset.consoleTab===name;tab.setAttribute('aria-selected',String(active));tab.tabIndex=active?0:-1;q('#console-'+tab.dataset.consoleTab+'-panel').hidden=!active;}for(const action of ['clear','copy'])q('[data-command='+action+'-console]').setAttribute('aria-label',action[0].toUpperCase()+action.slice(1)+' '+(name==='output'?'Output':'Debug'));}
 function append(name,text){if(!text)return;const pre=q(name==='output'?'[data-output]':'[data-debug-output]'),follow=pre.scrollHeight-pre.scrollTop-pre.clientHeight<35;outputs[name]=(outputs[name]+text).slice(-512*1024);pre.textContent=outputs[name];if(follow)pre.scrollTop=pre.scrollHeight;}
 function diagnostic(text){append('debug',new Date().toISOString()+' [diagnostic] '+String(text)+'\n');}
 function log(text){diagnostic(typeof text==='string'?text:JSON.stringify(text,null,2));}
 function fail(error){message(error.message);diagnostic(error.message);}
 async function api(path='',data){const options={credentials:'same-origin',cache:'no-store'};if(data!==undefined){const form=new FormData();form.set('csrf',csrf);form.set('payload',JSON.stringify(data));options.method='POST';options.body=form;}const response=await fetch(base+path,options);if(!response.ok){const raw=await response.text();throw Error(new DOMParser().parseFromString(raw,'text/html').querySelector('p')?.textContent||raw||response.statusText);}return response.json();}
 async function openLine(path,line){await openFile(path);if(!view)return;const position=view.state.doc.line(Math.min(view.state.doc.lines,line+1)).from;view.dispatch({selection:{anchor:position},effects:EditorView.scrollIntoView(position,{y:'center'})});}
 language=languageService({root,base:base.replace(/\/plugins$/,''),csrf,plugin:()=>selected,view:()=>view,current:()=>current,contents:()=>view?.state.doc.toString()||'',log,symbol:log,open:openLine});
  function dirty() {
    return [...buffers.values()].some((b) => b.text !== b.saved);
  }
  function tabLabels() {
    tabs.replaceChildren();
    for (const [path, b] of buffers) {
      const button = document.createElement("button");
      button.type = "button";
      button.role = "tab";
      button.setAttribute("aria-selected", String(path === current));
      button.textContent = path + (b.text !== b.saved ? " \u25CF" : "");
      button.onclick = () => openBuffer(path);
      tabs.append(button);
    }
  }
  function storeState() {
    if (current && view) {
      const b = buffers.get(current);
      b.state = view.state;
      b.text = view.state.doc.toString();
    }
  }
  function saveAll() {
    if(!saving)saving=saveBuffers().finally(()=>{saving=null;});
    return saving;
  }
  async function saveBuffers() {
    message("Saving files…");
    storeState();
    const pid=selected,draft=plugin;
    for(const [path,b] of [...buffers]) {
      if(b.text===b.saved)continue;
      const text=b.text;
      const result=await api('/'+pid+'/files',{revision:draft.revision,path,text});
      draft.revision=result.revision;b.saved=text; if(result.validation&&!result.validation.valid)diagnostic(result.validation.diagnostics.map(d=>d.message).join('\n'));
      if(selected===pid)tabLabels();
    }
    message(dirty()?'Saved snapshot; newer edits remain unsaved.':'All files saved.');
  }
  async function guard() {
    if (!dirty()) return true;
    const dialog = document.querySelector("#plugin-unsaved");
    return new Promise((resolve) => {
      dialog.showModal();
      let done = false;
      const finish = async (choice) => {
        if (done) return;
        done = true;
        dialog.close();
        try {
          if (choice === "save") await saveAll();
          if(choice==='discard'){
            if(saving)await saving;
            for(const b of buffers.values()){b.text=b.saved;b.state=null;}
            view?.destroy();view=null;if(current)await openBuffer(current);
          }
          resolve(choice !== "cancel" && (choice!=="save"||!dirty()));
        } catch (error) {
          message(error.message);
          resolve(false);
        }
        dialog.removeEventListener("click", click);
        dialog.removeEventListener("cancel", cancel);
      };
      const click = (e) => {
        const button = e.target.closest("[data-unsaved]");
        if (button) finish(button.dataset.unsaved);
      };
      const cancel = (e) => {
        e.preventDefault();
        finish("cancel");
      };
      dialog.addEventListener("click", click);
      dialog.addEventListener("cancel", cancel);
    });
  }
  function extensions() {
    return [language.extension, tooltips({parent:tooltipLayer}), theme, syntaxHighlighting(highlighting), lineNumbers(), history(), drawSelection(), highlightActiveLine(), highlightActiveLineGutter(), bracketMatching(), indentOnInput(), foldGutter(), search({ top: true }), highlightSelectionMatches(), keymap.of([{ key: "Mod-s", run: () => {
      saveAll().catch((e) => message(e.message));
      return true;
    } }, indentWithTab, ...defaultKeymap, ...historyKeymap, ...searchKeymap, ...foldKeymap]), wrap.of(prefs.wrap === false ? [] : EditorView.lineWrapping), indent.of(indentUnit.of(prefs.indent === "tab" ? "	" : " ".repeat(Number(prefs.indent) || 4))), access.of(EditorState.readOnly.of(!permissions.includes("edit"))), EditorView.updateListener.of((update) => {
      if (update.docChanged && current) {
        const b = buffers.get(current);
        b.text = update.state.doc.toString();
        b.state = update.state;
        tabLabels();
        language.changed();
      }
    })];
  }
  async function openBuffer(path) {
    storeState();
    const b = buffers.get(path);
    if (!b) return;
    current = path;
    const languageDescription = LanguageDescription.matchFilename(languages, path), syntaxName=languageDescription?.name||null;
    if (!b.state || b.syntaxName!==syntaxName) {
      let support=[];
      if(languageDescription)try{support=await languageDescription.load();}catch{}
      if(!b.state){b.syntax=new Compartment();b.state=EditorState.create({doc:b.text,extensions:[...extensions(),b.syntax.of(support)]});}
      else b.state=b.state.update({effects:b.syntax.reconfigure(support)}).state;
      b.syntaxName=syntaxName;
    }
    if (current !== path || buffers.get(path)!==b) return;
    if (view) view.setState(b.state);
    else view = new EditorView({ state: b.state, parent: q(".ide-code") });
    tabLabels();
    explorer.styles();
    view.focus();
    language.sync().catch((e) => message(e.message));
  }
  async function openFile(path) {
    if (buffers.has(path)) return openBuffer(path);
    const pid=selected,generation=selectionGeneration;
    const response = await fetch(base + "/" + pid + "/file?path=" + encodeURIComponent(path), { credentials: "same-origin" });
    if (!response.ok) throw new Error("Unable to open file.");
    const raw = await response.arrayBuffer();
    if(selected!==pid||generation!==selectionGeneration)return;
    let text;
    try {
      text = new TextDecoder("utf-8", { fatal: true }).decode(raw);
      if (text.includes("\0")) throw new Error();
    } catch {
      log({ path, size: raw.byteLength, message: "Binary resource. Use Download in its Explorer context menu." });
      return;
    }
    buffers.set(path, { text, saved: text, state: null });
    await openBuffer(path);
  }
  const explorer=createExplorer({root,tree,plugin:()=>plugin,id:()=>selected,permissions:()=>permissions,current:()=>current,open:openFile,message,fail,
    refresh:async()=>{if(saving)await saving;await refreshDetail();message('Explorer refreshed. Unsaved buffers were retained.');},
    download:path=>{const link=document.createElement('a');link.href=base+'/'+selected+'/file?path='+encodeURIComponent(path);link.download=path.split('/').at(-1);link.click();},mutate:mutateExplorer});
  function fileTree(){explorer.render();}
  async function mutateExplorer(operation,data){
    if(!selected||!plugin)throw Error('Select a loaded plugin first.');
    if(saving)await saving;
    const pid=selected,draft=plugin,generation=selectionGeneration,paths=data.paths||[data.path];
    const includes=path=>paths.some(parent=>path===parent||path.startsWith(parent+'/'));
    const affected=[...buffers].filter(([path])=>includes(path)),entry=plugin.manifest?.entrypoint?.split(':')[0];
    if(operation==='delete'){
      const names=paths.join(', '),folders=paths.some(path=>plugin.files.some(item=>item.path.startsWith(path+'/'))),unsaved=affected.some(([,buffer])=>buffer.text!==buffer.saved);
      if(!confirm('Delete '+names+'?'+(folders?' Folders and their contents will be removed.':'')+(unsaved?' Unsaved edits in affected tabs will be lost.':'')+' This cannot be undone.'))return false;
    }
    if(['rename','move','delete'].includes(operation)&&entry&&includes(entry)&&!confirm('This affects the manifest entry point '+entry+'. Update plugin.json before running the package again. Python imports will not be changed. Continue?'))return false;
    const result=await api('/'+pid+'/files',{operation,revision:draft.revision,...data});draft.revision=result.revision;
    if(pid!==selected||generation!==selectionGeneration)return false;
    if(operation==='delete'){
      for(const [path] of affected)buffers.delete(path);
      if(current&&includes(current)){current=null;view?.destroy();view=null;}
    }else if(operation==='rename'||operation==='move'){
      storeState();const renamed=new Map();for(const [path,buffer] of buffers){const change=result.changes.roots.find(item=>path===item.source||path.startsWith(item.source+'/'));const next=change?change.target+path.slice(change.source.length):path;renamed.set(next,buffer);if(current===path)current=next;}buffers.clear();for(const [path,buffer] of renamed)buffers.set(path,buffer);
      // The current EditorState retains undo/redo and unsaved text; re-opening it
      // selects the proper syntax mode when its extension changed.
      if(current)await openBuffer(current);
    }
    const updated=await api('/'+pid);if(pid!==selected||generation!==selectionGeneration)return false;plugin=updated;q('[data-plugin-title]').textContent=plugin.name;explorer.changed(result.changes,operation);tabLabels();if(!view&&buffers.size)await openBuffer(buffers.keys().next().value);
    message(operation[0].toUpperCase()+operation.slice(1)+' completed.');if(['rename','move','delete','create','directory','copy'].includes(operation)&&permissions.includes('edit')){await language.close();if(pid!==selected||generation!==selectionGeneration)return result;language.start().catch(error=>{if(pid===selected&&generation===selectionGeneration)diagnostic('Python intelligence unavailable: '+error.message);});}return result;
  }

 async function refreshDetail(){const pid=selected,result=await api('/'+pid);if(selected!==pid)return;plugin=result;q('[data-plugin-title]').textContent=plugin.name;fileTree();}
 async function selectPlugin(id,navigation='push',targetIndex){if(id===selected){if(Number.isInteger(targetIndex))historyIndex=targetIndex;return true;}const generation=++selectionGeneration;if(!await guard()||generation!==selectionGeneration){q('[data-plugin-selector]').value=selected||'';return false;}await language.close();if(generation!==selectionGeneration)return;explorer.close();buffers.clear();current=null;view?.destroy();view=null;if(navigation==='history')historyIndex=targetIndex;selected=id;plugin=null;tree.replaceChildren();q('[data-plugin-title]').textContent='Loading…';q('[data-management-link]').href=managementUrl+'?plugin='+encodeURIComponent(id);q('[data-plugin-selector]').value=id;q('.ide-empty')?.remove();await refreshDetail();if(selected!==id||generation!==selectionGeneration)return;tabLabels();const path=plugin.files.find(f=>f.path===plugin.manifest?.entrypoint?.split(':')[0])?.path||plugin.files.find(f=>!f.directory)?.path;if(path)await openFile(path);layout.save({lastPlugin:id});q('[data-management-link]').href=managementUrl+'?plugin='+encodeURIComponent(id);const url=location.pathname+'?plugin='+encodeURIComponent(id);if(navigation==='push')window.history.pushState({mareEditor:{id,index:++historyIndex}},'',url);else if(navigation==='replace')window.history.replaceState({...window.history.state,mareEditor:{id,index:historyIndex}},'',url);message('Loaded '+plugin.name+'. Starting Python intelligence…');if(permissions.includes('edit')){try{await language.start();if(selected===id)message('Python intelligence ready.');}catch(error){if(selected===id&&generation===selectionGeneration){await language.close();message('Python intelligence unavailable: '+error.message);diagnostic(error.message);}}}return selected===id&&generation===selectionGeneration?true:undefined;}
 async function reload(){const data=await api();permissions=data.permissions;root.querySelectorAll('[data-permission]').forEach(node=>node.hidden=!permissions.includes(node.dataset.permission));const select=q('[data-plugin-selector]');select.replaceChildren(new Option('Select a plugin',''));for(const row of data.plugins)select.add(new Option(row.name,row.id));select.value=selected||'';if(!data.plugins.length)message('No plugin packages found. Install a package through Plugins.');return data;}
 async function fileOperation(operation,path,extra={}){if(!selected||!plugin)throw Error('Select a loaded plugin first.');const result=await api('/'+selected+'/files',{operation,path,revision:plugin.revision,...extra});plugin.revision=result.revision;await refreshDetail();}
 async function run(){if(running)return;if(!selected||!plugin)throw Error('Select a loaded plugin first.');const pid=selected,draft=plugin;await saveAll();if(selected!==pid||plugin!==draft)throw Error('Plugin selection changed; run canceled.');if(dirty())throw Error('Newer edits remain unsaved; save them before Run.');running=true;consoleOpen();consoleTab('output');q('[data-command=run]').disabled=true;append('output',new Date().toISOString()+' Execution started: '+plugin.name+'\n');let previous={stdout:'',stderr:''};
  function render(result){q('[data-execution-status]').textContent=result.status+(result.duration===undefined?'':' · '+result.duration+'s');for(const [stream,name] of [['stdout','output'],['stderr','debug']]){const text=result[stream]||'';append(name,text.startsWith(previous[stream])?text.slice(previous[stream].length):text);previous[stream]=text;}if(!('stdout' in result)&&result.output)diagnostic('Worker returned unclassified legacy output; update the worker to separate stdout and stderr.\n'+result.output);}
  try{let result=await api('/'+pid+'/develop',{});runId=result.id;q('[data-command="cancel-run"]').disabled=false;diagnostic('Isolated execution started: '+runId);render(result);while(['Starting','Running'].includes(result.status)){await new Promise(resolve=>setTimeout(resolve,400));const response=await fetch(base.replace(/\/plugins$/,'')+'/executions/'+runId,{credentials:'same-origin',cache:'no-store'});if(!response.ok)throw Error('Unable to retrieve execution output.');result=await response.json();render(result);}if(result.status==='Succeeded')append('output','Execution completed in '+result.duration+'s.\n');else{diagnostic('Execution '+result.status+' ('+result.duration+'s).');consoleTab('debug');}}
  finally{running=false;runId=null;q('[data-command=run]').disabled=false;q('[data-command=cancel-run]').disabled=true;}}
 root.addEventListener('click',async event=>{const tab=event.target.closest('[data-console-tab]');if(tab){consoleTab(tab.dataset.consoleTab);return;}const button=event.target.closest('[data-command]');if(!button)return;try{const action=button.dataset.command;if(action==='save')await saveAll();else if(action==='run')await run();else if(action==='cancel-run'&&runId){button.disabled=true;const response=await fetch(base.replace(/\/plugins$/,'')+'/executions/'+runId+'/cancel',{method:'POST',credentials:'same-origin',headers:{'X-CSRFToken':csrf},body:new URLSearchParams({csrf:csrf,payload:'{}'})});if(!response.ok)throw Error('Unable to cancel execution.');diagnostic('Execution cancellation requested.');}else if(action==='console')consoleOpen(consolePanel.hidden);else if(action==='clear-console'){outputs[activeConsole]='';q(activeConsole==='output'?'[data-output]':'[data-debug-output]').textContent='';}else if(action==='copy-console')await navigator.clipboard.writeText(outputs[activeConsole]);else if(action==='refresh'){if(saving)await saving;await refreshDetail();message('Explorer refreshed. Unsaved buffers were retained.');}else if(action==='new-file')explorer.newFile();else if(action==='new-directory')explorer.newFolder();else if(action==='rename')explorer.rename();else if(action==='delete-file')await explorer.remove();}

  catch(error){if(button.dataset.command==='run'){consoleOpen();consoleTab('debug');q('[data-execution-status]').textContent='Failed';}fail(error);}});
 root.querySelector('[aria-label="Console tabs"]').addEventListener('keydown',event=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(event.key)){event.preventDefault();consoleTab(event.key==='Home'?'output':event.key==='End'?'debug':activeConsole==='output'?'debug':'output');q('[data-console-tab='+activeConsole+']').focus();}});
 q('[data-plugin-selector]').onchange=event=>{if(event.target.value)selectPlugin(event.target.value).catch(fail);else event.target.value=selected||'';};
 q('[data-word-wrap]').checked=prefs.wrap;q('[data-word-wrap]').onchange=event=>{prefs.wrap=event.target.checked;layout.save({wordWrap:prefs.wrap});const effect=wrap.reconfigure(prefs.wrap?EditorView.lineWrapping:[]);view?.dispatch({effects:effect});for(const buffer of buffers.values())if(buffer.state&&buffer.state!==view?.state)buffer.state=buffer.state.update({effects:effect}).state;};
 consoleOpen(!!layout.prefs.consoleOpen);consoleTab(activeConsole);
 window.addEventListener('popstate',async event=>{if(restoringHistory){restoringHistory=false;return;}const state=event.state?.mareEditor;if(!state)return;const delta=state.index-historyIndex;try{const accepted=await selectPlugin(state.id,'history',state.index);if(accepted===false&&delta){restoringHistory=true;window.history.go(-delta);}}catch(error){fail(error);}});
 window.addEventListener('beforeunload',event=>{if(dirty()){event.preventDefault();event.returnValue='';}});window.addEventListener('pagehide',()=>language.close());
 document.addEventListener('click',async event=>{const link=event.target.closest('a[href]');if(!link||event.defaultPrevented||event.ctrlKey||event.metaKey||link.target==='_blank'||link.hasAttribute('download')||link.href.includes('/file?')||link.href===location.href||!dirty())return;event.preventDefault();if(await guard())location.href=link.href;});
 try{const response=await fetch(base.replace(/\/plugins$/,'/discovery'),{method:'POST',credentials:'same-origin',body:(()=>{const form=new FormData();form.set('csrf',csrf);return form;})()});if(!response.ok)diagnostic('Directory discovery unavailable; existing registered packages remain available.');const data=await reload(),id=root.dataset.selected||data.plugins.find(row=>row.id===layout.prefs.lastPlugin)?.id||data.plugins[0]?.id;if(id)await selectPlugin(id,'replace');}catch(error){fail(error);}
}
export {mountDeveloperEditor};
