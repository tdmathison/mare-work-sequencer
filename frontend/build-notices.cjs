/* Ship dependency license texts with the locally compiled editor. */
const fs = require('node:fs');
const path = require('node:path');
const lock = JSON.parse(fs.readFileSync('package-lock.json', 'utf8'));
const notices = ['MARE CodeMirror 6 frontend dependency notices.\nVersions are pinned by package-lock.json.\n'];
for (const [location, item] of Object.entries(lock.packages).sort()) {
  if (!location.startsWith('node_modules/') || item.dev || !fs.existsSync(location)) continue;
  const manifest = JSON.parse(fs.readFileSync(path.join(location, 'package.json'), 'utf8'));
  const licenses = fs.readdirSync(location).filter(name => /^(license|copying)(\.|$)/i.test(name));
  notices.push(`\n===== ${manifest.name} ${manifest.version} (${manifest.license || 'see license'}) =====\n`);
  for (const name of licenses) notices.push(fs.readFileSync(path.join(location, name), 'utf8'));
}
fs.writeFileSync('static/vendor/codemirror/THIRD_PARTY_LICENSES.txt', notices.join('\n'));
