// Serve the pinned graph runtime locally, with its MIT license; no CDN requests.
const fs=require('node:fs');
fs.mkdirSync('static/vendor/cytoscape',{recursive:true});
fs.copyFileSync('node_modules/cytoscape/dist/cytoscape.min.js','static/vendor/cytoscape/cytoscape.min.js');
fs.copyFileSync('node_modules/cytoscape/LICENSE','static/vendor/cytoscape/LICENSE');
