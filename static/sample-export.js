(()=>{
 const form=document.querySelector('#panel-review form[action$="/archive"]');
 const categorySelect=document.querySelector('.asset-form select[name="category"]');
 const caseId=document.querySelector('.asset-form')?.dataset.caseId;
 const standard=form?.querySelector('button[name="archive_type"][value="standard"]');
 if(!form||!standard||!caseId)return;
 let currentLabel=null;
 async function update(){
  try{
   const response=await fetch('/cases/'+caseId+'/assets?category=samples',{cache:'no-store'});
   if(!response.ok)return;
   const result=await response.json();
   const hasSamples=result.files.some(file=>file.path.startsWith('samples/')&&file.path.toLowerCase().endsWith('.zip'));
   if(hasSamples&&!currentLabel){
    currentLabel=document.createElement('label');
    currentLabel.className='dangerous-sample-export';
    const checkbox=document.createElement('input'),warning=document.createElement('span');
    checkbox.type='checkbox';checkbox.name='include_samples';checkbox.value='1';
    warning.textContent='DANGER: Include password-protected Samples in this MIP archive. The export will contain malware samples and be named -MAL.';
    currentLabel.append(checkbox,warning);standard.before(currentLabel);
   }else if(!hasSamples&&currentLabel){currentLabel.remove();currentLabel=null;}
  }catch(_){}
 }
 categorySelect?.addEventListener('change',()=>{if(categorySelect.value==='samples')update();});
 window.addEventListener('mare:assets-changed',event=>{if(event.detail?.category==='samples')update();});
 update();
})();