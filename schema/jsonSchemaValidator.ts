import Ajv from "ajv/dist/2020";
import addFormats from "ajv-formats";

export function createValidator(schema: object) {
  const ajv = new Ajv({
    allErrors: true,
    strict: false,
    allowUnionTypes: true
  });

  addFormats(ajv);

  return ajv.compile(schema);
}
