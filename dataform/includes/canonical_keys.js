const KEY_VERSION = "v1";

function validateStaticComponent(value, name) {
  if (typeof value !== "string" || !/^[a-z][a-z0-9_]*$/.test(value)) {
    throw new Error(
      `${name} must contain only lowercase letters, numbers, and underscores, and must begin with a letter.`
    );
  }
}

function generateCanonicalKey({
  entityType,
  sourceNamespace,
  sourceIdentifiers
}) {
  validateStaticComponent(entityType, "entityType");
  validateStaticComponent(sourceNamespace, "sourceNamespace");

  if (
    !Array.isArray(sourceIdentifiers) ||
    sourceIdentifiers.length === 0 ||
    sourceIdentifiers.some(
      identifier =>
        typeof identifier !== "string" || identifier.trim().length === 0
    )
  ) {
    throw new Error(
      "sourceIdentifiers must be a non-empty array of SQL expressions."
    );
  }

  const missingIdentifierCondition = sourceIdentifiers
    .map(identifier => `(${identifier}) IS NULL`)
    .join("\n      OR ");

  const serializedIdentifiers = sourceIdentifiers
    .map(
      (identifier, index) =>
        `CAST((${identifier}) AS STRING) AS source_identifier_${index + 1}`
    )
    .join(",\n          ");

  return `(
    CASE
      WHEN ${missingIdentifierCondition}
        THEN NULL
      ELSE TO_HEX(
        SHA256(
          TO_JSON_STRING(
            STRUCT(
              "${KEY_VERSION}" AS key_version,
              "${entityType}" AS entity_type,
              "${sourceNamespace}" AS source_namespace,
              ${serializedIdentifiers}
            )
          )
        )
      )
    END
  )`;
}

module.exports = {
  KEY_VERSION,
  generateCanonicalKey
};