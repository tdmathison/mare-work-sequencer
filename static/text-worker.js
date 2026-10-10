(()=>{function l(c,s,o=""){let n=s.split(/\r\n|\r|\n/);switch(c){case"empty-lines":return n.filter(r=>r.trim()).join(`
`);case"carriage-returns":return s.replace(/\r\n|\r|\n/g,"");case"spaces":return s.replaceAll(" ","");case"cr-spaces":return n.join(" ");case"cr-commas":return n.join(",");case"cr-comma-space":return n.join(", ");case"cr-quotes":return n.map(r=>JSON.stringify(r)).join(", ");case"semicolon-cr":return s.replaceAll(";",`
`);case"space-cr":return s.replaceAll(" ",`
`);case"comma-space-cr":return s.replaceAll(", ",`
`);case"split":if(!o)throw Error("Enter a nonempty literal delimiter.");return s.split(o).join(`
`);case"egrep":case"egrep-v":case"egrep-o":{let r;try{r=new RegExp(o,c==="egrep-o"?"gu":"u")}catch{throw Error("Invalid JavaScript regular expression.")}return c==="egrep-o"?n.flatMap(e=>[...e.matchAll(r)].map(t=>t[0]).filter(t=>t.length)).join(`
`):n.filter(e=>r.test(e)===(c==="egrep")).join(`
`)}case"uniq":return[...new Set(n)].join(`
`);case"uniq-count":{let r=new Map;return n.forEach(e=>r.set(e,(r.get(e)||0)+1)),[...r].map(([e,t])=>`${e}|${t}`).join(`
`)}case"sort":return n.sort((r,e)=>{let t=r.toLowerCase(),a=e.toLowerCase();return t<a?-1:t>a?1:r<e?-1:r>e?1:0}).join(`
`);default:throw Error("Unknown local operation.")}}self.onmessage=({data:c})=>{try{self.postMessage({text:l(c.operation,c.text,c.pattern)})}catch(s){self.postMessage({error:s.message})}};})();
