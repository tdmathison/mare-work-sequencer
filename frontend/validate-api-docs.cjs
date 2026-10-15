/* Validate local files only: never resolve remote specification references. */
const parser = require('@apidevtools/swagger-parser');
parser.validate(process.argv[2], {resolve: {external: false}}).then(() => {
  process.stdout.write('OpenAPI specification validated.\n');
}).catch(error => { process.stderr.write(error.message + '\n'); process.exitCode = 1; });
