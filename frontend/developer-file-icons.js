/* Original cohesive SVG glyphs, covered by the repository MIT license. No font/emoji dependency. */
export function fileIconInfo(path, directory=false, expanded=false) {
  const name=path.split('/').at(-1).toLowerCase(),extension=name.split('.').at(-1);
  if(directory)return {kind:expanded?'folder-open':'folder',color:'#d9ae58'};
  if(name==='dockerfile')return {kind:'container',color:'#72b7e5'};
  if(name==='.gitignore')return {kind:'git',color:'#db886c'};
  if(name==='plugin.json')return {kind:'plugin',color:'#d9ae58'};
  if(name==='requirements.txt')return {kind:'package',color:'#82b998'};
  const mapping={py:['python','#78b8df'],json:['json','#d9ae58'],md:['markdown','#72b7e5'],yaml:['config','#bd9bd6'],yml:['config','#bd9bd6'],toml:['config','#dca16e'],txt:['document','#9eabb8'],html:['code','#df9b72'],css:['style','#72b7e5'],js:['javascript','#e0c86e'],ts:['typescript','#72b7e5'],sh:['terminal','#82b998'],xml:['code','#df9b72'],csv:['data','#82b998'],log:['log','#8995a2']};
  const [kind,color]=mapping[extension]||['document','#9eabb8'];return {kind,color};
}
const glyphs={
 folder:'M2 5h7l2 2h11v13H2z', 'folder-open':'M2 8V5h7l2 2h9v3 M2 10h21l-4 10H2z',
 document:'M5 2h9l5 5v15H5z M14 2v6h5 M8 12h8 M8 16h8',
 python:'M5 4h12v8H7v8h12v-8h-6 M8 7h.1 M16 17h.1',
 json:'M9 3H6v6l-3 3 3 3v6h3 M15 3h3v6l3 3-3 3v6h-3',
 markdown:'M2 5h20v14H2z M5 15V9l3 3 3-3v6 M16 9v6m-2-2 2 2 2-2',
 config:'M4 5h16 M4 12h16 M4 19h16 M8 3v4 M16 10v4 M10 17v4',
 code:'m8 6-6 6 6 6 M16 6l6 6-6 6 M14 4l-4 16',
 style:'M4 3h16l-2 17-6 2-6-2z M8 8h8l-1 7-3 1-3-1',
 javascript:'M3 3h18v18H3z M10 8v8H7 M17 8h-4v4h4v4h-4',
 typescript:'M3 3h18v18H3z M6 8h7 M9.5 8v9 M18 8h-4v4h4v5h-4',
 terminal:'M2 4h20v16H2z m4 4 4 4-4 4 M13 16h5',
 data:'M3 3h18v18H3z M3 9h18 M3 15h18 M10 3v18',
 log:'M5 3h14v18H5z M8 7h8 M8 11h8 M8 15h5',
 plugin:'M3 8h5V4h4v4h5v5h4v4h-4v5H3z',
 package:'m3 7 9-5 9 5v10l-9 5-9-5z M3 7l9 5 9-5 M12 12v10 M8 4l9 5',
 container:'M3 10h18v9H3z M5 5h4v5 M10 5h4v5 M15 5h4v5 M3 14h18 M8 10v9 M16 10v9',
 git:'m12 2 10 10-10 10L2 12z M8 7l8 9 M12 11v6'
};
export function fileIcon(path,directory=false,expanded=false){const info=fileIconInfo(path,directory,expanded),svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('aria-hidden','true');svg.setAttribute('focusable','false');svg.classList.add('explorer-file-icon');svg.dataset.icon=info.kind;svg.style.color=info.color;const line=document.createElementNS(svg.namespaceURI,'path');line.setAttribute('d',glyphs[info.kind]);line.setAttribute('fill','none');line.setAttribute('stroke','currentColor');line.setAttribute('stroke-width','1.65');line.setAttribute('stroke-linecap','round');line.setAttribute('stroke-linejoin','round');svg.append(line);if(info.kind==='python'){const accent=document.createElementNS(svg.namespaceURI,'path');accent.setAttribute('d','M7 14v6h12v-8h-6');accent.setAttribute('fill','none');accent.setAttribute('stroke','#e1c66d');accent.setAttribute('stroke-width','1.65');svg.append(accent);}return svg;}
