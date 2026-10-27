/* Deterministic, local-only geometry. No records are fetched by this worker. */
function explorerLayout({nodes,edges,mode,settings,center}) {
 const primary=nodes.filter(n=>n.kind!=='category').sort((a,b)=>a.id.localeCompare(b.id)),byId=new Map(primary.map(n=>[n.id,n])),neighbors=new Map(primary.map(n=>[n.id,new Set()]));
 for(const e of edges)if(neighbors.has(e.source)&&neighbors.has(e.target)&&e.source!==e.target){neighbors.get(e.source).add(e.target);neighbors.get(e.target).add(e.source);}
 const components=[],seen=new Set();
 for(const n of primary){if(seen.has(n.id))continue;const ids=[n.id];seen.add(n.id);for(let i=0;i<ids.length;i++)for(const id of [...neighbors.get(ids[i])].sort())if(!seen.has(id)){seen.add(id);ids.push(id);}components.push(ids);}
 const factor={compact:.8,balanced:1,spacious:1.35}[settings.spacing]||1,step=230*factor,result={};
 const rank=id=>({case:0,family:1,actor:2}[byId.get(id).kind]??3);
 function automatic(ids){const cases=ids.filter(id=>byId.get(id).kind==='case');return (cases.length?cases:ids).slice().sort((a,b)=>neighbors.get(b).size-neighbors.get(a).size||a.localeCompare(b))[0];}
 // Keep the component containing the radial center first.
 const chosen=mode==='radial'&&settings.center==='selected'&&byId.has(center)?center:automatic(primary.map(n=>n.id));
 if(mode==='radial')components.sort((a,b)=>Number(b.includes(chosen))-Number(a.includes(chosen)));
 let offsetX=0,offsetY=0,rowHeight=0;const packingWidth=Math.max(step*4,Math.sqrt(nodes.length)*step*1.5);
 for(const ids of components){
  const points={};
  if(mode==='tree'){
   const layers=[[],[],[],[]];ids.forEach(id=>layers[rank(id)].push(id));
   // Order each layer by its already placed neighbors, keeping shared nodes single.
   layers.forEach((layer,depth)=>{const score=id=>{const placed=[...neighbors.get(id)].filter(id=>points[id]);return placed.length?placed.reduce((sum,id)=>sum+points[id].x,0)/placed.length:0;};layer.sort((a,b)=>score(a)-score(b)||a.localeCompare(b));layer.forEach((id,i)=>points[id]={x:(i-(layer.length-1)/2)*step,y:depth*step});});
   if(settings.direction==='lr')for(const point of Object.values(points))[point.x,point.y]=[point.y,point.x];
  }else if(mode==='radial'){
   const root=ids.includes(chosen)?chosen:automatic(ids),dist=new Map([[root,0]]),queue=[root];
   for(let i=0;i<queue.length;i++)for(const id of [...neighbors.get(queue[i])].sort())if(!dist.has(id)){dist.set(id,dist.get(queue[i])+1);queue.push(id);}
   const rings=new Map();ids.forEach(id=>{const depth=dist.get(id)||0;if(!rings.has(depth))rings.set(depth,[]);rings.get(depth).push(id);});
   let radius=0;for(const [depth,ring] of [...rings].sort((a,b)=>a[0]-b[0])){ring.sort();radius=depth?Math.max(radius+step,ring.length*step/(2*Math.PI)):0;ring.forEach((id,i)=>{const angle=2*Math.PI*i/ring.length-Math.PI/2;points[id]={x:Math.cos(angle)*radius,y:Math.sin(angle)*radius};});}
  }else{
   const size=Math.max(step,Math.sqrt(ids.length)*step/2);ids.forEach((id,i)=>{const angle=i*2.3999632297;points[id]={x:Math.cos(angle)*size*Math.sqrt((i+1)/ids.length),y:Math.sin(angle)*size*Math.sqrt((i+1)/ids.length)};});
   const links=edges.filter(e=>ids.includes(e.source)&&ids.includes(e.target)&&e.source!==e.target);
   for(let iteration=0;iteration<160;iteration++){
    const forces=Object.fromEntries(ids.map(id=>[id,{x:0,y:0}]));
    for(let i=0;i<ids.length;i++)for(let j=i+1;j<ids.length;j++){const a=ids[i],b=ids[j],dx=points[a].x-points[b].x||.01,dy=points[a].y-points[b].y||.01,d=Math.max(1,Math.hypot(dx,dy)),force=step*step/(d*d)*8;forces[a].x+=dx/d*force;forces[a].y+=dy/d*force;forces[b].x-=dx/d*force;forces[b].y-=dy/d*force;}
    for(const e of links){const a=points[e.source],b=points[e.target],dx=b.x-a.x,dy=b.y-a.y,d=Math.max(1,Math.hypot(dx,dy)),force=(d-step)*.045;forces[e.source].x+=dx/d*force;forces[e.source].y+=dy/d*force;forces[e.target].x-=dx/d*force;forces[e.target].y-=dy/d*force;}
    const cooling=1-iteration/180;for(const id of ids){points[id].x+=Math.max(-20,Math.min(20,forces[id].x))*cooling;points[id].y+=Math.max(-20,Math.min(20,forces[id].y))*cooling;}
   }
   // Resolve close label/node boxes deterministically after forces settle.
   const placed=[];for(const id of ids){let tries=0;while(placed.some(other=>Math.abs(points[id].x-other.x)<step*.8&&Math.abs(points[id].y-other.y)<step*.65)&&tries++<ids.length*3)points[id].y+=step*.7;placed.push(points[id]);}
  }
  // Categories are subordinate satellites; reserve room before packing components.
  for(const parent of ids){const children=nodes.filter(n=>n.kind==='category'&&n.caseNode===parent).sort((a,b)=>a.id.localeCompare(b.id));children.forEach((child,i)=>{let radius=110*factor,point;for(let attempt=0;attempt<100;attempt++){const angle=2*Math.PI*(i/Math.max(1,children.length)+attempt*.381966),r=radius+Math.floor(attempt/12)*80;point={x:points[parent].x+Math.cos(angle)*r,y:points[parent].y+Math.sin(angle)*r};if(!Object.values(points).some(p=>Math.abs(p.x-point.x)<95&&Math.abs(p.y-point.y)<85))break;}points[child.id]=point;});}
  const values=Object.values(points),minX=Math.min(...values.map(p=>p.x)),maxX=Math.max(...values.map(p=>p.x)),minY=Math.min(...values.map(p=>p.y)),maxY=Math.max(...values.map(p=>p.y));
  if(offsetX&&offsetX+maxX-minX>packingWidth){offsetX=0;offsetY+=rowHeight+step*2;rowHeight=0;}
  rowHeight=Math.max(rowHeight,maxY-minY);
  for(const [id,p] of Object.entries(points))result[id]={x:p.x-minX+offsetX,y:p.y-minY+offsetY};offsetX+=maxX-minX+step*2;
 }
 return result;
}
if(typeof self!=='undefined')self.onmessage=event=>{try{self.postMessage({positions:explorerLayout(event.data)});}catch(error){self.postMessage({error:error.message});}};
if(typeof module!=='undefined')module.exports=explorerLayout;
