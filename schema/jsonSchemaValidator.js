const Ajv = require("ajv/dist/2020").default;
const addFormats = require("ajv-formats");

function createValidator(schema) {
  const ajv = new Ajv({
    allErrors: true,
    strict: false,
    allowUnionTypes: true
  });

  addFormats(ajv);

  return ajv.compile(schema);
}

module.exports = { createValidator };