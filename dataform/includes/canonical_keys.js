const KEY_VERSION = "v1";

function validateStaticComponent(value, name) {
  if (typeof value !== "string" || !/^[a-z][a-z0-9_]*$/.test(value)) {
    throw new Error(
      `${name} must contain only lowercase letters, numbers, and underscores, and must begin with a letter.`
    );
  }
}

function validateIdentifiers(identifiers, name) {
  if (
    !Array.isArray(identifiers) ||
    identifiers.length === 0 ||
    identifiers.some(
      identifier =>
        typeof identifier !== "string" || identifier.trim().length === 0
    )
  ) {
    throw new Error(
      `${name} must be a non-empty array of SQL expressions.`
    );
  }
}

function renderKey({
  entityType,
  sourceNamespace,
  identifiers,
  identifierAlias
}) {
  validateStaticComponent(entityType, "entityType");
  validateIdentifiers(identifiers, "identifiers");

  if (sourceNamespace !== undefined) {
    validateStaticComponent(sourceNamespace, "sourceNamespace");
  }

  const missingIdentifierCondition = identifiers
    .map(identifier => `(${identifier}) IS NULL`)
    .join("\n      OR ");

  const structComponents = [
    `"${KEY_VERSION}" AS key_version`,
    `"${entityType}" AS entity_type`
  ];

  if (sourceNamespace !== undefined) {
    structComponents.push(
      `"${sourceNamespace}" AS source_namespace`
    );
  }

  identifiers.forEach((identifier, index) => {
    structComponents.push(
      `CAST((${identifier}) AS STRING) AS ${identifierAlias}_${index + 1}`
    );
  });

  return `(
    CASE
      WHEN ${missingIdentifierCondition}
        THEN NULL
      ELSE TO_HEX(
        SHA256(
          TO_JSON_STRING(
            STRUCT(
              ${structComponents.join(",\n              ")}
            )
          )
        )
      )
    END
  )`;
}

function generateCanonicalKey({
  entityType,
  sourceNamespace,
  sourceIdentifiers
}) {
  return renderKey({
    entityType,
    sourceNamespace,
    identifiers: sourceIdentifiers,
    identifierAlias: "source_identifier"
  });
}

function generateReferenceKey({
  entityType,
  referenceIdentifiers
}) {
  return renderKey({
    entityType,
    identifiers: referenceIdentifiers,
    identifierAlias: "reference_identifier"
  });
}

module.exports = {
  KEY_VERSION,
  generateCanonicalKey,
  generateReferenceKey
};