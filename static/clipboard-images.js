(()=>{
 document.addEventListener('paste',event=>{
  const area=event.target.closest?.('.markdown-input');
  if(!area||area.closest('fieldset:disabled'))return;
  const files=Array.from(event.clipboardData?.items||[])
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