(()=>{
 document.addEventListener('paste',event=>{
  const area=event.target.closest?.('.markdown-input');
  if(!area||area.closest('fieldset:disabled'))return;
    const clipboard=event.clipboardData,items=Array.from(clipboard?.items||[]);
    const types=new Set([...Array.from(clipboard?.types||[]),...items.map(item=>item.type)].map(type=>type.toLowerCase()));
    if([...types].some(type=>type.startsWith('text/')||type==='application/rtf'))return;
    const files=items
   .filter(item=>item.kind==='file'&&item.type.startsWith('image/'))
   .map(item=>item.getAsFile())
   .filter(Boolean);
  if(!files.length)return;
  event.preventDefault();
  const dropEvent=new Event('drop',{bubbles:true,cancelable:true});
  Object.defineProperty(dropEvent,'dataTransfer',{value:{files}});
  area.dispatchEvent(dropEvent);
 });
})();