import {transform} from './text-operations';
self.onmessage=({data})=>{try{self.postMessage({text:transform(data.operation,data.text,data.pattern)});}catch(error){self.postMessage({error:error.message});}};
