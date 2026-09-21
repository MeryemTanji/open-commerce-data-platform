# Olist Canonical Dimension Contracts

## Status

Draft

## Date

2026-09-19

## Purpose

This document defines the source-specific canonical dimension contracts for the Olist implementation.

It applies the platform-wide [Mercury Canonical Model Design](../../../../architecture/designs/canonical_model_design.md) and the inventory established in the [Olist Canonical Model Overview](olist_canonical_model_overview.md).

The contracts are informed by the validated [Olist Relationship Profile](../../relationships/olist_relationship_profile.md) and implement the dispositions recorded in the [Olist Anomaly Disposition Register](../../staging/olist_anomaly_disposition.md).

## Scope

This document defines the initial Olist contracts for:

- `dim_customer`;
- `dim_location`;
- `dim_product`;
- `dim_seller`;
- `dim_date`;
- dimension-related foreign-key resolution on canonical facts.

Profiling evidence and anomaly baselines remain in their dedicated source documents.

## 1. Customer Identity and Order Context

### 1.1 Identity semantics

The canonical customer entity uses:

```text
customer_unique_id
```

as the source identifier for persistent customer identity.

The Olist `customer_id` does not represent the persistent customer. It identifies the customer record associated with a particular order and may contain the address context observed for that purchase.

The canonical model therefore assigns these responsibilities:

| Source field | Canonical responsibility |
| --- | --- |
| `customer_unique_id` | Identifies the persistent customer represented by `dim_customer` |
| `customer_id` | Identifies the order-context customer record retained on `fct_orders` |
| Customer ZIP, city, and state | Preserve the address context associated with the order |

Multiple orders associated with one `customer_unique_id` represent repeat activity by the same persistent customer and are not anomalies. 

The canonical model must not create a separate persistent customer merely because a new `customer_id` appears.

### 1.2 Customer dimension

`dim_customer` has the grain:

```text
one row per source namespace and customer_unique_id
```

Its required identity columns are:

| Column | Responsibility |
| --- | --- |
| `customer_key` | Canonical primary key for the persistent customer |
| `source_namespace` | Stable namespace identifying the originating source instance |
| `source_customer_id` | Preserved `customer_unique_id` from the Olist source |

The initial `dim_customer` is intentionally thin because the source does not provide stable customer attributes independently of order-context address records.

Order-specific city, state, and postal-code attributes must not be selected arbitrarily and stored as permanent current-customer attributes.

A future source containing governed customer master data may extend the dimension through an explicit identity-resolution and survivorship contract.

### 1.3 Order-to-customer mapping

`fct_orders` resolves customer identity through:

```text
stg_orders.customer_id
        ↓
stg_customers.customer_id
        ↓
stg_customers.customer_unique_id
        ↓
dim_customer.customer_key
```

The join from orders to staged customer records must preserve order grain.

The customer-related columns on `fct_orders` include:

| Column | Responsibility |
| --- | --- |
| `customer_key` | Foreign key to the persistent customer |
| `source_customer_record_id` | Preserved order-specific `customer_id` |
| `customer_location_key` | Foreign key to the order-context location |
| `customer_source_postal_code_prefix` | Preserved postal-code prefix from the customer record |
| `customer_source_city` | Preserved normalized city from the customer record |
| `customer_source_state` | Preserved normalized state from the customer record |
| `customer_reference_status` | Describes the result of customer identity resolution |

The initial `customer_reference_status` domain is:

| Value | Meaning |
| --- | --- |
| `matched` | The order resolved to one staged customer record and persistent customer |
| `missing_customer` | The order references no staged customer record |
| `reused_customer_record` | One order-specific `customer_id` is associated with multiple orders |

The status values describe source relationship conditions. They do not authorize deletion or fabrication of customer data.

### 1.4 Order-context location

`dim_customer` must not contain one arbitrarily selected current location.

Instead, each order carries the location associated with its order-specific customer record:

```text
fct_orders.customer_location_key
        ↓
dim_location.location_key
```

The key is generated from:

```text
country_code = "BR"
customer_zip_code_prefix
```

The country code is supplied by the governed Olist source context. It is not inferred from the state abbreviation.

The order fact retains the customer source city, state, and postal-code prefix even when geographic reference coverage is unavailable.

`dim_location` must include every postal-code prefix referenced by canonical customers or sellers, including prefixes without a matching staged geolocation observation. For uncovered prefixes:

- the location key remains available;
- source postal-code lineage is preserved;
- resolved city, state, latitude, and longitude remain unavailable;
- geographic coverage status is exposed explicitly;
- otherwise valid customers, sellers, and orders remain publishable.

This prevents missing geolocation reference data from creating broken canonical foreign keys.

### 1.5 Customer anomaly dispositions

The customer-order controls are applied as follows:

| Condition | Canonical treatment |
| --- | --- |
| `orders_without_customer` | Retain the order, preserve its referenced `customer_id`, set `customer_key` to `NULL`, and mark `customer_reference_status` as `missing_customer` |
| `customers_without_order` | Retain the customer in `dim_customer`; exclude it only from analyses requiring an associated order |
| `customer_ids_with_multiple_orders` | Retain all orders and mark them as `reused_customer_record` pending investigation |

Mercury must not:

- invent a persistent customer for an unmatched order;
- replace a missing customer reference with an unrelated customer;
- delete unmatched orders or customers;
- treat repeated `customer_unique_id` values as duplicates;
- assign one arbitrary order-context address to the persistent customer.

Customer-dependent downstream products must explicitly exclude or separately classify orders where `customer_key` is unavailable.

### 1.6 Customer publication controls

`dim_customer` must enforce:

- one row per `customer_key`;
- one row per unique combination of source_namespace and `source_customer_id`;
- non-null canonical and source identity columns;
- deterministic consistency between `customer_key` and its key inputs.

`fct_orders` must enforce:

- one row per `order_key`;
- preservation of the staged order count;
- no row amplification during customer resolution;
- valid `customer_reference_status` values;
- a valid `dim_customer` reference whenever `customer_reference_status = "matched"`;
- a `NULL` `customer_key` whenever `customer_reference_status = "missing_customer"`;
- preservation of the source customer-record identifier;
- deterministic location-key generation when a postal-code prefix is available.

The existing relationship-quality view remains responsible for monitoring changes to customer-order coverage and source-instance cardinality.

A blocking canonical control must fail if customer resolution unexpectedly changes the number of order rows.

## 2. Location Resolution and Geographic Context

### 2.1 Location semantics

Olist geographic observations describe Brazilian ZIP-code prefixes rather than unique customer, seller, or address entities.

The canonical location grain is:

```text
one row per country code and postal-code prefix
```

The initial implementation uses:

```text
country_code = "BR"
```

A location represents a reusable geographic reference. It does not represent a complete street address, customer residence, seller identity, or individual coordinate observation.

Repeated geolocation observations for the same postal-code prefix are valid source evidence and must be resolved before canonical use.

Canonical models must not join customers, sellers, orders, or order items directly to `stg_geolocations`.

### 2.2 Location population

`dim_location` must contain the distinct union of postal-code prefixes found in:

- `stg_geolocations.geolocation_zip_code_prefix`;
- `stg_customers.customer_zip_code_prefix`;
- `stg_sellers.seller_zip_code_prefix`.

This includes:

- prefixes with staged geolocation observations;
- prefixes referenced only by customers;
- prefixes referenced only by sellers;
- geolocation prefixes not currently referenced by either entity.

Including all referenced prefixes ensures that missing geolocation coverage does not create broken canonical foreign keys.

A postal-code prefix without geolocation observations remains a valid location identity. Its resolved geographic attributes remain unavailable until a governed reference source provides supporting evidence.

### 2.3 Resolution boundary

Geographic resolution is implemented through:

```text
stg_geolocations
        ↓
int_geolocation_resolution
        ↓
dim_location
```

`int_geolocation_resolution` has the grain:

```text
one row per geolocation postal-code prefix
```

It resolves repeated observations into one deterministic geographic record.

`dim_location` combines the resolved reference with all postal-code prefixes used by customers and sellers. It therefore includes placeholder locations for prefixes without staged geolocation coverage.

Neither relation may expose more than one row for a given combination of `country_code` and postal-code prefix.

### 2.4 State resolution

For each postal-code prefix, the resolved state is selected using:

- 1. the state with the highest source-observation count;
- 2. the alphabetically first state as a deterministic tie-breaker.

Conceptually:

```text
resolved_state =
    highest observation count
    then state ascending
```

The resolution must also expose whether:

- more than one distinct state was observed;
- multiple states shared the highest observation count.

A modal-state tie does make the transformation technically nondeterministic because the lexical tie-breaker remains stable. It does, however, represent semantic ambiguity and must be flagged for investigation.

The source observations remain unchanged in staging.

### 2.5 City resolution

For each postal-code prefix, the resolved city is selected from observations belonging to the resolved state.

The rule selects:

- 1. the city with the highest observation count within the resolved state;
- 2. the alphabetically first city as a deterministic tie-breaker.

Conceptually:

```text
resolved_city =
    city within resolved_state
    with highest observation count
    then city ascending
```

The resolution must expose whether:

- more than one distinct city was observed within the resolved state;
- multiple cities shared the highest observation count.

The resolved city is a representative label for the postal-code prefix. It must not be interpreted as evidence that every source observation belongs to only one city.

### 2.6 Coordinate resolution

Representative coordinates are calculated from observations belonging to the resolved state.

The initial method uses:

```text
representative_latitude  = median latitude
representative_longitude = median longitude
```

Latitude and longitude are calculated independently across the eligible observations.

The median is used because it is less sensitive than the mean to isolated coordinate outliers. The resulting coordinate represents the postal-code prefix and is not required to reproduce one exact source observation.

The resolution must expose:

- the number of eligible coordinate observations;
- the number of distinct coordinate pairs;
- whether multiple coordinate pairs were observed;
- the coordinate-resolution method.

For prefixes without staged geolocation coverage, representative latitude and longitude remain `NULL`.

### 2.7 Canonical location columns

`dim_location` includes the following core columns:

| Column | Responsibility |
| --- | --- |
| `location_key` | Canonical primary key for the location |
| `country_code` | Governed country context for the postal-code prefix |
| `postal_code_prefix` | Normalized source postal-code prefix |
| `resolved_city` | Deterministically selected representative city |
| `resolved_state` | Deterministically selected representative state |
| `representative_latitude` | Median latitude for eligible observations |
| `representative_longitude` | Median longitude for eligible observations |
| `geolocation_coverage_status` | Indicates whether geographic reference evidence exists |
| `source_observation_count` | Number of staged observations for the prefix |
| `distinct_observation_count` | Number of distinct normalized observations |
| `distinct_city_count` | Number of cities observed within the resolved state |
| `distinct_state_count` | Number of states observed for the prefix |
| `distinct_coordinate_count` | Number of distinct eligible coordinate pairs |
| `has_multiple_cities` | Indicates city-level ambiguity |
| `has_multiple_states` | Indicates state-level ambiguity |
| `has_multiple_coordinates` | Indicates coordinate variation |
| `has_modal_city_tie` | Indicates a tie between leading city values |
| `has_modal_state_tie` | Indicates a tie between leading state values |
| `resolution_method` | Identifies the governed resolution rule applied |

The initial `geolocation_coverage_status` domain is:

| Value | Meaning |
| --- | --- |
| `resolved` | One or more staged geolocation observations support the location |
| `missing_reference` | The prefix is referenced by an entity but has no staged geolocation observation |

For locations with `missing_reference` status:

- `source_observation_count` and all distinct-value counts are `0`;
- ambiguity indicators are `FALSE`;
- resolved city, state, latitude, and longitude are `NULL`;
- `resolution_method` is `unresolved_missing_reference`.

The initial `resolution_method` values are:

| Value | Meaning |
| --- | --- |
| `modal_state_modal_city_median_coordinates_v1` | Geographic attributes were resolved from staged observations using the approved version-one rules |
| `unresolved_missing_reference` | No staged geolocation observations were available |

Unused geolocation prefixes remain `resolved`; lack of current customer or seller usage does not make the reference incomplete.

### 2.8 Source and resolved geography

Customer and seller source attributes must remain distinguishable from resolved geographic attributes.

Canonical entity relations must preserve, where applicable:

- source postal-code prefix;
- source city;
- source state;
- canonical location key;
- resolved city;
- resolved state;
- geographic coverage status;
- source-versus-resolved state mismatch status.

A resolved value must not overwrite the source-derived value.

For known seller-state disagreements, Mercury may use the resolved state for governed geographic analysis while retaining the seller's source state for lineage and investigation.

A mismatch indicates conflicting source evidence. It does not invalidate the seller or authorize modification of the staging record.

### 2.9 Geographic anomaly dispositions

The geographic controls are applied as follows:

| Condition | Canonical treatment |
| --- | --- |
| `customers_without_geolocation_prefix` | Retain the customer and order context, publish the location key, and leave resolved geographic attributes unavailable |
| `customer_prefixes_without_geolocation` | Publish placeholder locations and monitor changes in missing reference coverage |
| `sellers_without_geolocation_prefix` | Retain the seller, publish the location key, and leave resolved geographic attributes unavailable |
| `seller_prefixes_without_geolocation` | Publish placeholder locations and monitor changes in missing reference coverage |
| `customers_disagreeing_with_modal_geolocation_state` | Preserve both states, flag the mismatch, and prevent silent correction |
| `sellers_disagreeing_with_modal_geolocation_state` | Preserve the source state, expose the resolved state, and flag the mismatch |
| `geolocation_prefixes_with_multiple_states` | Preserve all staging observations and apply the deterministic modal-state rule |
| `geolocation_prefixes_with_modal_state_ties` | Apply the lexical tie-breaker, flag the ambiguity, and require investigation before unreviewed geographic use |
| `geolocation_prefixes_without_customer_or_seller` | Retain the resolved reference without treating lack of entity usage as invalid |

Mercury must not:

- discard an entity because geolocation coverage is unavailable;
- fabricate coordinates for an uncovered postal-code prefix;
- overwrite source city or state values in staging;
- select an arbitrary geolocation observation;
- treat repeated geolocation observations as duplicate entity records;
- join entity-grain models directly to staged geolocation observations;
- conceal ambiguity created by multiple cities, states, or coordinates.

### 2.10 Foreign-key propagation

Customer and seller locations use the same governed location-key logic as `dim_location`.

The initial relationships are:

| Child relation | Foreign key | Context |
| --- | --- | --- |
| `fct_orders` | `customer_location_key` | Location observed on the order-specific customer record |
| `dim_seller` | `location_key` | Location supplied by the staged seller record |

The key is derived from:

```text
key_version
    +
location entity type
    +
country_code
    +
postal_code_prefix
```

The same valid country and postal-code components must always generate the same `location_key`.

A matching geolocation observation is not required to generate the key.

### 2.11 Location publication controls

`int_geolocation_resolution` must enforce:

- one row per geolocation postal-code prefix;
- deterministic state and city ranking;
- deterministic representative-coordinate calculation;
- valid ambiguity indicators;
- non-null resolved state for covered prefixes;
- non-null representative coordinates when eligible coordinates exist;
- preservation of source and distinct-observation counts;
- no row amplification during resolution.

`dim_location` must enforce:

- one row per `location_key`;
- one row per unique combination of `country_code` and `postal_code_prefix`;
- non-null key components;
- deterministic consistency between `location_key` and its key inputs;
- inclusion of every postal-code prefix referenced by canonical customers or sellers;
- valid `geolocation_coverage_status` values;
- `resolved` status only when supporting geolocation observations exist;
- `missing_reference` status only when supporting observations do not exist;
- `NULL` resolved attributes for locations without reference coverage;
- valid foreign-key compatibility with customer and seller relations.

A blocking control must fail if geographic resolution creates more than one per country and postal-code prefix or amplifies an entity-grain relation.

The existing geographic relationship-quality view remains responsible for monitoring source coverage, state inconsistencies, multi-state prefixes, modal-state ties, and unused reference coverage.

## 3. Product Identity and Catalogue Semantics

### 3.1 Product identity

The canonical product entity uses:

```text
product_id
```

as the source identifier for product identity.

`dim_product` has the grain:

```text
one row per source namespace and product_id
```

The canonical key is generated from:

```text
key_version
    +
product entity type
    +
source_namespace
    +
product_id
```

The initial source namespace is:

```text
olist
```

The same source namespace and `product_id` must always generate the same `product_key`.

The source does not provide a separate cross-system product master identifier. Mercury must not infer that products from different source namespaces represent the same product merely because their names, categories, or physical measurements are similar.

### 3.2 Product dimension

The initial `dim_product` includes:

| Column | Responsibility |
| --- | --- |
| `product_key` | Canonical primary key for the product |
| `source_namespace` | Stable namespace identifying the originating source instance |
| `source_product_id` | Preserved source `product_id` |
| `product_category_name` | Normalized source category name |
| `product_name_length` | Source-provided product-name length |
| `product_description_length` | Source-provided product-description length |
| `product_photos_count` | Source-provided product-photo count |
| `product_weight_g` | Source-provided product weight in grams |
| `product_length_cm` | Source-provided product length in centimetres |
| `product_height_cm` | Source-provided product height in centimetres |
| `product_width_cm` | Source-provided product width in centimetres |
| `catalog_metadata_status` | Indicates whether catalogue-description metadata is complete |
| `physical_measurement_status` | Indicates whether all physical measurements are available |
| `product_weight_status` | Distinguishes positive, zero, and missing weight values |

The initial dimension represents the product information available in the current source snapshot.

The source does not provide sufficient temporal metadata to reconstruct product-attribute history. `dim_product` must not claim to implement historical versioning or slowly changing dimension behavior unless a future source and contract explicitly support it.

### 3.3 Catalogue metadata

The following attributes are legitimately nullable:

- `product_category_name`;
- `product_name_length`;
- `product_description_length`;
- `product_photos_count`.

The initial `catalog_metadata_status` domain is:

| Value | Meaning |
| --- | --- |
| `complete` | All governed catalogue-description attributes are available |
| `missing` | One or more governed catalogue-description attributes are unavailable |

Missing catalogue metadata does not invalidate product identity.

A product with missing metadata remains valid for:

- order-item counting;
- revenue and price analysis;
- seller-product relationship analysis;
- product-identifier-level analysis.

It may be unsuitable for analyses requiring:

- product-category segmentation;
- product-name or description completeness;
- product-photo availability;
- complete catalogue enrichment.

Mercury must not replace a missing source category with an invented category.

An explicit value such as `unknown` may be introduced only by a downstream consumption contract that requires complete grouping labels. Such a presentation value must not overwrite the canonical `NULL`.

### 3.4 Physical measurements

The physical measurement attributes are:

- `product_weight_g`;
- `product_length_cm`;
- `product_height_cm`;
- `product_width_cm`.

The initial `physical_measurement_status` domain is:

| Value      | Meaning                                             |
| ---------- | --------------------------------------------------- |
| `complete` | Weight, length, height, and width are all available |
| `missing`  | One or more physical measurements are unavailable   |

The initial `product_weight_status` domain is:

| Value      | Meaning                                     |
| ---------- | ------------------------------------------- |
| `positive` | Product weight is greater than zero         |
| `zero`     | Product weight is present and equal to zero |
| `missing`  | Product weight is unavailable               |

Missing or zero measurements remain preserved in `dim_product`.

Products with incomplete measurements remain valid for analyses not dependent on physical dimensions. They must be conditionally excluded from calculations requiring complete measurements.

Products with zero or missing weight must be excluded from calculations requiring a positive product weight.

Mercury must not:

- replace missing measurements with zero;
- convert zero weight to `NULL`;
- infer measurements from similar products;
- manufacture plausible physical values;
- silently exclude the entire product because one measurement is unusable.

### 3.5 Product category semantics

`product_category_name` preserves the normalized category supplied by the source.

The initial canonical model does not introduce a separate product-category dimension because the source provides only a category label and no independent category identifier, hierarchy, effective dates, or governed category reference.

Mercury must not:

- translate category names without an approved reference mapping;
- infer category hierarchies from category text;
- treat a missing category as a new product category;
- generate product identity from category membership.

A governed category dimension may be introduced later if Mercury receives a reusable category taxonomy or an approved translation and hierarchy mapping.

### 3.6 Product and seller separation

Seller is not a fixed attribute of the canonical product.

The relationship is expressed through fct_order_items:

```text
dim_product 1 ────< fct_order_items >──── 1 dim_seller
```

A product may be sold by multiple sellers, and a seller may sell multiple products.

`dim_product` must therefore not contain:

- one arbitrarily selected `seller_key`;
- one assumed current seller;
- seller-specific price;
- seller-specific freight value;
- seller-specific shipping terms.

Seller, price, freight, and fulfilment context remain attributes of the order-item event.

### 3.7 Product-to-order-item relationship

`fct_order_items` obtains its product reference through:

```text
stg_order_items.product_id
        ↓
stg_products.product_id
        ↓
dim_product.product_key
```

The join must preserve the order-item grain:

```text
one row per source namespace, order_id, and order_item_id
```

The product-related columns on `fct_order_items` include:

| Column | Responsibility |
| --- | --- |
| `product_key` | Foreign key to `dim_product` |
| `source_product_id` | Preserved product identifier from the order item |
| `product_reference_status` | Describes the result of product-reference resolution |

The initial `product_reference_status` domain is:

| Value | Meaning |
| --- | --- |
| `matched` | The order item resolved to one canonical product |
| `missing_product` | The order item’s `source_product_id` references no staged product |

When `product_reference_status` is `missing_product`:

- the order item remains publishable;
- `source_product_id` remains preserved;
- `product_key` is `NULL`;
- the item is excluded only from product-dependent outputs;
- the missing parent is investigated through the applicable quality control.

Mercury must not invent a product entity solely to satisfy an unmatched order-item reference.

### 3.8 Repeated products and quantity semantics

Repeated `product_id` values across order-item rows are expected and do not represent duplicate product entities.

Within one order, repeated (`order_id`, `product_id`) combinations may represent multiple units of the same product. The canonical order-item fact must preserve every source item row at its natural grain.

The initial source supports deriving quantity through an explicit aggregation because repeated order-product combinations currently retain consistent:

- seller;
- unit price;
- freight value;
- shipping-limit timestamp.

A reusable quantity grouping must include:

```text
order_key
product_key
source_product_id
seller_key
source_seller_id
unit_price
freight_value
shipping_limit_timestamp
```
The preserved source identifiers prevent distinct unresolved products or sellers from being combined when a canonical foreign key is `NULL`.

Quantity may then be derived as:

```sql
COUNT(*) AS quantity
```

This aggregation belongs in an approved summary model or downstream data product. `dim_product` must not store transactional quantity.

If repeated order-product rows later contain different sellers, prices, freight values, or shipping limits, they must remain separate commercial groups.

### 3.9 Product anomaly dispositions

Product and product-reference controls are applied as follows:

| Condition | Canonical treatment |
| --- | --- |
| `missing_catalog_metadata` | Retain the product, preserve nullable attributes, and limit only analyses requiring the missing metadata |
| `missing_physical_measurement` | Retain and flag the product; exclude it only from calculations requiring complete measurements |
| `zero_product_weight` | Retain and flag the product; exclude it only from calculations requiring positive weight |
| `order_items_without_product` | Retain the item, preserve `source_product_id`, set `product_key` to `NULL`, and mark the reference as `missing_product` |
| `products_without_order_items` | Retain the product as valid catalogue data and exclude it only from analyses requiring observed sales |
| `repeated_order_product_combinations` | Preserve every item row and derive quantity only through an explicit aggregation |
| `repeated_order_products_with_multiple_sellers` | Preserve seller-level item separation |
| `repeated_order_products_with_multiple_prices` | Preserve price-level item separation |
| `repeated_order_products_with_multiple_freight_values` | Preserve freight-level item separation |
| `repeated_order_products_with_multiple_shipping_limits` | Preserve shipping-limit-level item separation |

Mercury must not treat an unsold product as invalid merely because it has no order-item relationship.

The current zero baseline for `products_without_order_items` describes the Olist extract and is not a universal canonical requirement.

### 3.10 Product publication controls

`dim_product` must enforce:

- one row per `product_key`;
- one row per unique combination of `source_namespace` and `source_product_id`;
- non-null canonical and source identity columns;
- deterministic consistency between `product_key` and its key inputs;
- valid catalogue-metadata status values;
- valid physical-measurement status values;
- valid product-weight status values;
- consistency between each status and its underlying attributes;
- non-negative count and measurement values when present;
- preservation of missing and zero source measurements;
- preservation of the staged product count.

Product resolution on `fct_order_items` must enforce:

- preservation of the staged order-item count;
- no row amplification during the product join;
- valid `product_reference_status` values;
- a valid `dim_product` reference whenever `product_reference_status = "matched"`;
- a `NULL` `product_key` whenever `product_reference_status = "missing_product"`;
- preservation of `source_product_id`;
- at most one matched product for each order item.

A blocking canonical control must fail if product resolution changes the number of order-item rows.

The existing product-quality and product–order-item relationship views remain responsible for monitoring source anomalies, reference coverage, repeated order-product behavior, and changes to the validated commercial grouping assumptions.

## 4. Seller Identity and Marketplace Context

### 4.1 Seller identity

The canonical seller entity uses:

```text
seller_id
```

as the source identifier for seller identity.

`dim_seller` has the grain:

```text
one row per source namespace and seller_id
```

The canonical key is generated from:

```text
key_version
    +
seller entity type
    +
source_namespace
    +
seller_id
```

The initial source namespace is:

```text
olist
```

The same source namespace and `seller_id` must always generate the same `seller_key`.

The source does not provide a separate cross-system seller master identifier. Mercury must not infer that sellers from different source namespaces represent the same business merely because their city, state, postal-code prefix, or product activity is similar.

### 4.2 Seller dimension

The initial `dim_seller` includes:

| Column | Responsibility |
| --- | --- |
| `seller_key` | Canonical primary key for the seller |
| `source_namespace` | Stable namespace identifying the originating source instance |
| `source_seller_id` | Preserved source `seller_id` |
| `location_key` | Foreign key to the seller’s canonical location |
| `source_postal_code_prefix` | Preserved postal-code prefix from the seller record |
| `source_city` | Preserved normalized city from the seller record |
| `source_state` | Preserved normalized state from the seller record |
| `resolved_city` | Deterministically resolved city from `dim_location` |
| `resolved_state` | Deterministically resolved state from `dim_location` |
| `geolocation_coverage_status` | Indicates whether geographic reference evidence exists |
| `seller_geographic_status` | Describes agreement between source and resolved geography |

The initial dimension represents the seller information available in the current source snapshot.

The source does not provide sufficient temporal metadata to reconstruct seller-address history. `dim_seller` must not claim to implement historical versioning or slowly changing dimension behavior unless a future source and contract explicitly support it.

### 4.3 Seller location

Each seller is linked to the canonical location derived from:

```text
country_code = "BR"
seller_zip_code_prefix
```

The relationship is:

```text
stg_sellers.seller_zip_code_prefix
        ↓
dim_location.postal_code_prefix
        ↓
dim_seller.location_key
```

Because `dim_location` includes placeholder locations for every seller postal-code prefix, `location_key` remains available even when staged geolocation observations are missing.

`dim_seller` preserves the source city and state independently from the resolved city and state.

The source-derived values must not be overwritten by geographic resolution.

### 4.4 Seller geographic status

The initial `seller_geographic_status` domain is:

| Value | Meaning |
| --- | --- |
| `matched` | Geolocation evidence exists and the source state agrees with the resolved state |
| `state_mismatch` | Geolocation evidence exists but the source state differs from the resolved state |
| `missing_reference` | No staged geolocation observation exists for the seller’s postal-code prefix |

When `seller_geographic_status` is `matched`:

- `geolocation_coverage_status` is `resolved`;
- `source_state` equals `resolved_state`.

When `seller_geographic_status` is `state_mismatch`:

- `geolocation_coverage_status` is `resolved`;
- both source and resolved states remain available;
- geographic analysis may use the resolved state;
- source lineage and the mismatch remain visible.

When `seller_geographic_status` is `missing_reference`:

- `location_key` remains available;
- `geolocation_coverage_status` is `missing_reference`;
- resolved city and state remain `NULL`;
- the seller remains valid for non-geographic analysis.

The known seller-state mismatches are treated as deterministic downstream corrections under ADR-02. They do not authorize modification of `stg_sellers`.

### 4.5 Seller marketplace relationships

A seller may participate in multiple order-item rows and multiple orders.

The primary commercial relationship is:

```text
dim_seller 1 ────< fct_order_items
```

Orders and sellers form a many-to-many relationship through order items:

```text
fct_orders 1 ────< fct_order_items >──── 1 dim_seller
```

Products and sellers also form a many-to-many relationship through order items:

```text
dim_product 1 ────< fct_order_items >──── 1 dim_seller
```

These relationships mean that seller identity belongs to the order-item event.

Seller must not be represented as:

- one unqualified attribute on `fct_orders`;
- one permanent attribute on `dim_product`;
- a value inferred from `product_key`;
- one arbitrarily selected seller for a multi-seller order.

Seller activity, seller concentration, and the number of products or orders associated with a seller are derived transactional measures. They must not be stored as permanent seller identity attributes without a separately governed snapshot or aggregate contract.

### 4.6 Seller-to-order-item resolution

`fct_order_items` obtains its seller reference through:

```text
stg_order_items.seller_id
        ↓
stg_sellers.seller_id
        ↓
dim_seller.seller_key
```

The join must preserve the order-item grain:

```text
one row per source namespace, order_id, and order_item_id
```

The seller-related columns on `fct_order_items` include:

| Column | Responsibility |
| --- | --- |
| `seller_key` | Foreign key to `dim_seller` |
| `source_seller_id` | Preserved seller identifier from the order item |
| `seller_reference_status` | Describes the result of seller-reference resolution |

The initial `seller_reference_status` domain is:

| Value | Meaning |
| --- | --- |
| `matched` | The order item resolved to one canonical seller |
| `missing_seller` | The order item’s `source_seller_id` references no staged seller |

When `seller_reference_status` is `missing_seller`:

- the order item remains publishable;
- `source_seller_id` remains preserved;
- `seller_key` is `NULL`;
- the item is excluded only from seller-dependent outputs;
- the missing parent is investigated through the applicable quality control.

Mercury must not invent a seller entity solely to satisfy an unmatched order-item reference.

### 4.7 Multi-seller orders

An order may contain items supplied by more than one seller.

The current source contains valid multi-seller orders, so `fct_orders` must not expose one unqualified `seller_key`.

Seller-level order analysis must aggregate order items at:

```text
order_key
seller_key
source_seller_id
```

Measures derived at this grain may include:

- item count;
- distinct product count;
- item price total;
- freight total;
- earliest shipping-limit timestamp;
- latest shipping-limit timestamp.

Any order-level seller summary must preserve every seller association.

Multi-seller orders must not be:

- treated as duplicate orders;
- assigned to one arbitrarily selected seller;
- flattened into one seller value;
- joined to payments or reviews before seller-level item measures are aggregated.

### 4.8 Seller and product relationships

A seller may supply multiple products, and a product may be supplied by multiple sellers.

Seller therefore remains attached to each order-item event.

The current source contains products associated with multiple sellers across different orders. This is valid marketplace behavior and must not be treated as conflicting product identity.

Within a single order-product combination, seller-aware quantity grouping must preserve:

```text
order_key
product_key
source_product_id
seller_key
source_seller_id
unit_price
freight_value
shipping_limit_timestamp
```

If one order-product combination later contains multiple sellers, each seller association must remain a separate commercial group.

### 4.9 Seller anomaly dispositions

Seller and seller-reference controls are applied as follows:

| Condition | Canonical treatment |
| --- | --- |
| `order_items_without_seller` | Retain the item, preserve `source_seller_id`, set `seller_key` to `NULL`, and mark the reference as `missing_seller` |
| `sellers_without_order_items` | Retain the seller as valid marketplace data and exclude it only from analyses requiring observed activity |
| `orders_with_multiple_sellers` | Preserve every seller association and require seller-aware aggregation |
| `products_with_multiple_sellers` | Preserve seller on the order-item event and do not model seller as a fixed product attribute |
| `order_product_combinations_with_multiple_sellers` | Preserve seller-level item separation and use seller-aware quantity aggregation |
| `sellers_without_geolocation_prefix` | Retain the seller and location key while leaving resolved geographic attributes unavailable |
| `seller_prefixes_without_geolocation` | Publish placeholder locations and monitor changes in missing reference coverage |
| `sellers_disagreeing_with_modal_geolocation_state` | Preserve the source state, expose the resolved state, and flag the mismatch |

Mercury must not treat a seller without order items as invalid merely because the seller has no observed transaction activity.

The current zero baseline for `sellers_without_order_items` describes the Olist extract and is not a universal marketplace requirement.

The known multi-seller order and multi-seller product baselines describe valid marketplace topology rather than source-quality failures.

### 4.10 Seller publication controls

`dim_seller` must enforce:

- one row per `seller_key`;
- one row per unique combination of `source_namespace` and `source_seller_id`;
- non-null canonical and source identity columns;
- deterministic consistency between `seller_key` and its key inputs;
- preservation of the staged seller count;
- preservation of source postal-code, city, and state values;
- deterministic consistency between `location_key`, the governed `"BR"` country context, and `source_postal_code_prefix`;
- valid `geolocation_coverage_status` values;
- valid `seller_geographic_status` values;
- `seller_geographic_status = "matched"` whenever geographic coverage exists and `source_state` equals `resolved_state`;
- `seller_geographic_status = "state_mismatch"` whenever geographic coverage exists and `source_state` differs from `resolved_state`;
- `seller_geographic_status = "missing_reference"` whenever geographic coverage is unavailable;
- `NULL` resolved city and state whenever `seller_geographic_status = "missing_reference"`;
- no arbitrary replacement of source geographic values;
- no row amplification during location enrichment.

Seller resolution on `fct_order_items` must enforce:

- preservation of the staged order-item count;
- no row amplification during the seller join;
- valid `seller_reference_status` values;
- a valid `dim_seller` reference whenever `seller_reference_status = "matched"`;
- a `NULL` `seller_key` whenever `seller_reference_status = "missing_seller"`;
- preservation of `source_seller_id`;
- at most one matched seller for each order item.

A blocking canonical control must fail if seller resolution changes the number of order-item rows.

The existing seller–order-item and geographic relationship-quality views remain responsible for monitoring seller-reference coverage, marketplace cardinalities, missing geolocation coverage, and source-versus-resolved state disagreement.

## 5. Date Dimension and Role-Playing Date Semantics

### 5.1 Date dimension responsibility

`dim_date` provides one governed calendar reference for canonical relations containing business dates or timestamps.

Its grain is:

```text
one row per calendar date
```

The primary key is:

```text
date_key
```

`date_key` uses the calendar date directly as a stable natural key.

Unlike source-derived entity keys, it does not require:

- a source namespace;
- an entity-type prefix;
- SHA-256 generation;
- a source identifier.

The same calendar date represents the same canonical date across all source systems and business processes.

### 5.2 Calendar population

`dim_date` must contain one continuous row for every date between the earliest and latest dates required by the canonical model.

The initial bounds are derived from all applicable staged temporal fields:

- order purchase timestamp;
- order approval timestamp;
- carrier-delivery timestamp;
- customer-delivery timestamp;
- estimated-delivery date;
- order-item shipping-limit timestamp;
- review-creation date;
- review-answer timestamp.

The generated range is:

```text
minimum applicable calendar date
        through
maximum applicable calendar date
```

Both boundaries are inclusive.

The range must remain continuous even when no business event occurred on a particular date.

Calendar generation must depend on validated staging temporal values rather than on already-built canonical facts. This prevents circular dependencies between `dim_date` and the facts that reference it.

If a future canonical relation requires a date outside the current range, the generated calendar must expand to include it.

Because `date_key` is the calendar date itself, expanding the range does not change existing keys.

### 5.3 Calendar attributes

The initial `dim_date` includes:

| Column | Responsibility |
| --- | --- |
| `date_key` | Calendar date and canonical primary key |
| `calendar_year` | Four-digit calendar year |
| `calendar_quarter` | Calendar quarter number from 1 to 4 |
| `calendar_quarter_name` | Stable quarter label such as `Q1` |
| `calendar_month` | Calendar month number from 1 to 1 |
| `calendar_month_name` | Full English calendar-month name |
| `calendar_year_month` | Stable year-month label in `YYYY-MM` format |
| `calendar_day_of_month` | Day number within the month |
| `calendar_day_of_year` | Day number within the year |
| `iso_day_of_week` | ISO weekday number from 1 for Monday through 7 for Sunday |
| `calendar_day_name` | Full English weekday name |
| `iso_week` | ISO week number |
| `iso_year` | ISO week-numbering year |
| `week_start_date` | Monday starting the ISO week |
| `week_end_date` | Sunday ending the ISO week |
| `month_start_date` | First calendar date of the month |
| `month_end_date` | Last calendar date of the month |
| `quarter_start_date` | First calendar date of the quarter |
| `quarter_end_date` | Last calendar date of the quarter |
| `year_start_date` | First calendar date of the year |
| `year_end_date` | Last calendar date of the year |
| `is_weekend` | Indicates Saturday or Sunday |

Calendar attributes must be derived deterministically from `date_key`.

The initial date dimension does not define:

- public holidays;
- working days;
- retail calendars;
- fiscal calendars;
- promotional periods;
- source-specific reporting periods.

Those concepts require separately governed business definitions and must not be inferred from the Gregorian calendar alone.

### 5.4 Date and timestamp separation

A timestamp represents an event at a point in time.

A date key represents the calendar date associated with that event under the canonical date-extraction convention.

Canonical facts must preserve the staged timestamp when meaningful time-of-day information exists. Deriving a date key must not replace or truncate the original timestamp.

For example:

```text
order_purchase_timestamp
        +
purchase_date_key
```

Both fields remain available because they serve different analytical purposes.

Source fields already governed as calendar dates remain date-semantic and must not be converted into artificial midnight timestamps.

### 5.5 Timezone convention

The Olist source timestamps do not contain explicit timezone offsets.

The staging layer has already parsed them into BigQuery `TIMESTAMP` values. The initial canonical model preserves those staged values without applying an inferred timezone conversion.

Role-specific date keys are derived using an explicit UTC extraction convention:

```sql
DATE(source_timestamp, "UTC")
```

This convention ensures deterministic results. It does not assert that the original business event occurred in the UTC timezone.

Mercury must not:

- infer a Brazilian timezone from city or state;
- shift timestamps using an assumed local offset;
- apply daylight-saving corrections unsupported by the source;
- describe staged timestamps as timezone-verified event times.

If authoritative source-timezone metadata becomes available, changing the extraction convention constitutes a canonical contract change and requires impact assessment.

### 5.6 Order date roles

`fct_orders` uses the following role-specific date keys:

| Date key | Derived from | Nullability |
| --- | --- | --- |
| `purchase_date_key` | `order_purchase_timestamp` | Required |
| `approval_date_key` | `order_approved_timestamp` | Nullable |
| `carrier_delivery_date_key` | `order_delivered_carrier_timestamp` | Nullable |
| `customer_delivery_date_key` | `order_delivered_customer_timestamp` | Nullable |
| `estimated_delivery_date_key` | `order_estimated_delivery_date` | Required |

The corresponding timestamps and source dates remain available on `fct_orders`.

Nullable lifecycle timestamps produce nullable date keys.

Mercury must not generate a date key for a lifecycle event that is absent from the source.

### 5.7 Order-item date roles

`fct_order_items` uses:

| Date key                  | Derived from               | Nullability |
| ------------------------- | -------------------------- | ----------- |
| `shipping_limit_date_key` | `shipping_limit_timestamp` | Required    |

The full `shipping_limit_timestamp` remains available on the order-item fact.

The date key supports calendar aggregation while the timestamp preserves the complete source value.

### 5.8 Review date roles

`fct_reviews` uses:

| Date key                   | Derived from              | Nullability |
| -------------------------- | ------------------------- | ----------- |
| `review_creation_date_key` | `review_creation_date`    | Required    |
| `review_answer_date_key`   | `review_answer_timestamp` | Required    |

`review_creation_date` is already governed as a calendar date. Therefore:

```text
review_creation_date_key = review_creation_date
```

`review_answer_timestamp` remains available because it contains meaningful time-of-day information.

The source review chronology must remain unchanged even when a future record contains an answer timestamp before its creation date.

### 5.9 Role-playing dimension behavior

The date roles all reference the same physical `dim_date` relation.

Conceptually:

```text
purchase_date_key
approval_date_key
carrier_delivery_date_key
customer_delivery_date_key
estimated_delivery_date_key
shipping_limit_date_key
review_creation_date_key
review_answer_date_key
        ↓
dim_date.date_key
```

A data product may present role-specific aliases or views when that improves usability. It must not create conflicting calendar definitions for each role.

Each role must preserve its own business meaning. For example:

- purchase date must not be substituted for approval date;
- estimated-delivery date must not be treated as actual delivery date;
- review-creation date must not be substituted for review-answer date;
- shipping-limit date must not be interpreted as shipment date.

### 5.10 Temporal anomaly dispositions

Temporal anomalies are applied as follows:

| Condition | Canonical treatment |
| --- | --- |
| Missing optional lifecycle timestamp | Preserve the `NULL` timestamp and corresponding `NULL` date key |
| Delivered order missing approval | Retain the order and do not infer an approval timestamp or date key |
| Delivered order missing carrier delivery | Retain the order and do not infer a carrier-delivery timestamp or date key |
| Delivered order missing customer delivery | Retain the order and do not infer a customer-delivery timestamp or date key |
| Carrier delivery before purchase | Preserve both timestamps and date keys; flag the chronology anomaly |
| Customer delivery before carrier delivery | Preserve both timestamps and date keys; flag the chronology anomaly |
| Review answer before review creation | Preserve both temporal values and date keys; exclude the record only from calculations requiring valid chronology |
| Unparseable required temporal value | Block publication through the applicable staging or canonical control |

Mercury must not:

- invent missing lifecycle events;
- reorder timestamps;
- replace anomalous timestamps with plausible values;
- derive durations from incomplete required endpoints without an explicit nullable result;
- treat estimated and actual events as interchangeable;
- discard an otherwise usable order or review solely because one optional lifecycle event is unavailable.

### 5.11 Duration semantics

Durations must be derived from the preserved timestamps rather than from date keys.

Examples include:

- purchase-to-approval duration;
- purchase-to-carrier-delivery duration;
- purchase-to-customer-delivery duration;
- estimated-versus-actual delivery difference;
- review response duration.

Date keys support calendar grouping and filtering. They are not sufficiently precise for elapsed-time calculations involving timestamp-semantic events.

A duration must remain `NULL` when a required endpoint is unavailable.

A negative or otherwise anomalous duration must be preserved or flagged according to its anomaly disposition. Mercury must not apply an absolute value or silently reorder the endpoints.

### 5.12 Date publication controls

`dim_date` must enforce:

- one row per `date_key`;
- non-null and unique `date_key` values;
- continuous daily coverage between the configured minimum and maximum dates;
- no missing dates within the generated range;
- deterministic consistency between `date_key` and every derived calendar attribute;
- valid month, quarter, weekday, day-of-year, and ISO-week domains;
- correct start-date and end-date boundaries;
- `is_weekend = TRUE` only for Saturday and Sunday;
- complete coverage of every non-null canonical date key.

Canonical facts must enforce:

- a valid `dim_date` reference for every non-null role-specific date key;
- a non-null date key whenever its required source date or timestamp is non-null;
- a `NULL` date key whenever its optional source timestamp is `NULL`;
- equality between `review_creation_date_key` and the preserved `review_creation_date`;
- deterministic UTC date extraction from timestamp-semantic fields;
- preservation of the original staged timestamp or date;
- no row amplification when date attributes are joined.

A blocking canonical control must fail if:

- `dim_date` contains duplicate or missing calendar dates;
- a required date role cannot resolve to `dim_date`;
- a derived date key is inconsistent with its source temporal value;
- joining a fact to `dim_date` changes the fact row count.

The existing order-lifecycle and review-chronology quality views remain responsible for monitoring incomplete or anomalous temporal sequences.