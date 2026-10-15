/* Build-time only; Flask never downloads documentation assets. */
const fs = require('node:fs');
const path = require('node:path');
const source = path.dirname(require.resolve('swagger-ui-dist/package.json'));
const manifest = require(path.join(source, 'package.json'));
const dest = 'static/vendor/swagger-ui';
fs.mkdirSync(dest, {recursive: true});
for (const file of ['swagger-ui-bundle.js', 'swagger-ui.css', 'LICENSE', 'NOTICE']) {
  fs.copyFileSync(path.join(source, file), path.join(dest, file));
}
fs.writeFileSync(path.join(dest, 'README.txt'), `Swagger UI ${manifest.version}, official swagger-ui-dist npm package.\nSource: https://github.com/swagger-api/swagger-ui/tree/v${manifest.version}\nApache-2.0; see LICENSE and NOTICE.\nRebuild: npm ci && npm run build:api-docs\nDo not edit vendor files; MARE overrides live in static/api-documentation.css.\n`);
