// Straightforward local transformations; regex deliberately uses ECMAScript semantics.
export function transform(operation,text,pattern=''){
 const lines=text.split(/\r\n|\r|\n/);
 switch(operation){
 case 'empty-lines':return lines.filter(line=>line.trim()).join('\n');
 case 'carriage-returns':return text.replace(/\r\n|\r|\n/g,'');
 case 'spaces':return text.replaceAll(' ','');
 case 'cr-spaces':return lines.join(' ');
 case 'cr-commas':return lines.join(',');
 case 'cr-comma-space':return lines.join(', ');
 case 'cr-quotes':return lines.map(line=>JSON.stringify(line)).join(', ');
 case 'semicolon-cr':return text.replaceAll(';','\n');
 case 'space-cr':return text.replaceAll(' ','\n');
 case 'comma-space-cr':return text.replaceAll(', ','\n');
 case 'split':if(!pattern)throw Error('Enter a nonempty literal delimiter.');return text.split(pattern).join('\n');
 case 'egrep':case 'egrep-v':case 'egrep-o':{
  let regex;try{regex=new RegExp(pattern,operation==='egrep-o'?'gu':'u');}catch(error){throw Error('Invalid JavaScript regular expression.');}
  if(operation==='egrep-o')return lines.flatMap(line=>[...line.matchAll(regex)].map(match=>match[0]).filter(value=>value.length)).join('\n');
  return lines.filter(line=>regex.test(line)===(operation==='egrep')).join('\n');
 }
 case 'uniq':return [...new Set(lines)].join('\n');
 case 'uniq-count':{const counts=new Map();lines.forEach(line=>counts.set(line,(counts.get(line)||0)+1));return [...counts].map(([line,count])=>`${line}|${count}`).join('\n');}
 case 'sort':return lines.sort((a,b)=>{const x=a.toLowerCase(),y=b.toLowerCase();return x<y?-1:x>y?1:a<b?-1:a>b?1:0;}).join('\n');
 default:throw Error('Unknown local operation.');
 }
}
