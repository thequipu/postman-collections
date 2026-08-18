# Schema Diff — UI `usermgmt` vs Newman `pm_flow_singleds_1786975730768`

Comparison of a **UI-created** schema (real product flow, ingests) against a **newman-flow-created**
schema (`FLOW-SingleDS-Realm`, lands 0 rows), both targeting the **same database** (`user_management`,
same datasource `dataSourceID=259`).

## Sources

| Schema | versionUri | Dump file | Nodes / Links |
|---|---|---|---|
| UI `usermgmt` | `usermgmtVersion#v1` | `ui_usermgmt.json` | 306 / 516 |
| Newman `pm_flow_singleds_1786975730768` | `pm-flow-singleds-1786975730768Version#v1` | `newman_pm_flow_singleds_1786975730768.json` | 283 / 401 |

Read via `GET applicationService/schema-graph?versionUri=<encoded>`. `.sorted.json` variants (nodes/links
sorted, keys sorted) are provided for line-level `diff`.

---

## A. Structural — nodes present/absent

| node_type | UI | newman | note |
|---|---|---|---|
| Schema | 1 | 1 | names differ (expected) |
| Version | 1 | 1 | names differ (expected) |
| data_source | 1 | 1 | ✅ |
| table | 20 | 20 | ✅ |
| property | 120 | 120 | ✅ |
| Node | 20 | 20 | ✅ |
| Node Property | 120 | 120 | ✅ |
| **Node Relationship** | **23** | **0** | ❌ absent in newman |

## B. Structural — links present/absent

| link kind | UI | newman |
|---|---|---|
| HAS_VERSION | 1 | 1 |
| Has_Node | 20 | 20 |
| has_tables | 20 | 20 |
| has_property | 120 | 120 |
| has_node_property | 120 | 120 |
| maps_to_column | 120 | 120 |
| **Foreign_Key** | **23** | **0** |
| **has_node_relationship** | **23** | **0** |
| **maps_to_foreign_key_column** | **23** | **0** |
| **maps_to_target_node_property** | **23** | **0** |
| **FK_&lt;constraint&gt; (distinct edges)** | **23** | **0** |

→ **115 FK-layer links missing** in newman.

The 23 foreign keys the UI captured (newman has none):

```
FK_addresses_user_id_to_users
FK_audit_logs_user_id_to_users
FK_contact_preferences_email_phone_number_to_user_role_assignments
FK_customer_orders_email_country_to_customers
FK_customer_orders_phone_number_country_to_customers
FK_permissions_history_changed_by_to_users
FK_permissions_history_new_permission_id_to_permissions
FK_permissions_history_old_permission_id_to_permissions
FK_permissions_history_role_id_to_roles
FK_product_orders_product_code_vendor_id_to_products
FK_roles_history_changed_by_to_users
FK_roles_history_new_role_id_to_roles
FK_roles_history_old_role_id_to_roles
FK_roles_history_user_id_to_users
FK_supplier_orders_supplier_name_contact_email_to_suppliers
FK_user_role_assignments_email_to_email_addresses
FK_user_role_assignments_phone_number_to_phone_numbers
FK_user_role_assignments_role_id_to_roles
FK_user_role_assignments_user_id_to_users
FK_user_role_details_user_id_role_id_to_user_role_assignments
FK_user_role_history_user_id_role_id_to_user_role_assignments
FK_users_address_id_to_addresses
FK_users_role_id_to_roles
```

## C. Per-node fields — UI populates, newman leaves null/absent

| node_type | fields missing in newman |
|---|---|
| **data_source** | `identity`, `createdBy`, `created_by`, `tenantId`, `tenant_id`, `description` |
| **table** | `identity`, `createdBy`, `created_by`, `tenantId`, `tenant_id`, `description` |
| **property** | `identity`, `createdBy`, `created_by`, `tenantId`, `tenant_id`, `description`, `foreign_key`, `unique_key`, `compositeKey`, `compositeKeyColumns`, `composite_key`, `composite_key_columns` |
| **Node** | `identity`, `createdBy`, `created_by`, `tenantId`, `tenant_id`, `updatedBy`, `updated_by`, `description`, `entity_label`, `named_entity` |
| **Node Property** | `identity`, `description`, `unique_key`, `alternateLabel`, `alternate_label`, `preferredLabel`, `preferred_label`, `freeText`, `timeLabel`, `time_label`, `timeFormat`, `time_format` |

**`identity` coverage: UI 100% of nodes / newman 0% of nodes.**

## D. Value differences on matched nodes (same uri, different value)

| field | # nodes | UI | newman |
|---|---|---|---|
| **Node Property `dataType` / `data_type`** | **52** | `BIGINT` | `INTEGER` / `SMALLINT` |
| property `primaryKey` | 11 | absent (null) | `false` |
| property `uniqueKey` | 9 | absent (null) | `false` |

**Type-map bug:** the server maps all integer types (`int2`/`int4`/`serial`/`smallserial`) → `BIGINT`;
our `graph_builder_js` maps `int4→INTEGER`, `int2→SMALLINT`.

## E. Link attributes — stripped on newman links

UI links carry 13 attributes newman omits entirely:

```
altLabel, dashed, pathIds, prefLabel, primaryKey, rel_uri, relation_only_column,
target_column, target_node_uri, timeLabel, uniqueKey, uriMatching, identity
```

Newman links carry only: `source, target, relationship, direction, node_uri, prefix`.

## F. Identical (no difference)

- All 20 table `uri`/`node_id`, all 120 column `uri`/`node_id`, `dataSourceID=259`
- All core links (Has_Node, has_tables, has_property, has_node_property, maps_to_column)
- Column `label`, `nullable`, `foreignKey` (camelCase), `node_type`, and `dataType` on the other 68 columns
- No newman-only fields, links, or nodes anywhere (except expected Schema/Version names)

---

## Root cause

| Difference | Source | Fixed by |
|---|---|---|
| A (Node Relationship), B (FK links), C (identity/audit/snake/composite) | **entity layer skipped** — flow never calls `POST /entity` | create entities via `POST /entity` per table |
| D (dataType BIGINT), E (link attributes) | **our fabrication** in `graph_builder_js` | correct the type map / emit link attrs (also come free from the entity layer) |

Every difference collapses to one root: **the UI created entities through the entity layer
(`POST /entity`), which mints `identity` + audit metadata, canonicalizes types, and auto-discovers the
foreign-key relationship graph; our newman flow fabricates the `/schema-graph` payload directly in
`graph_builder_js` and calls neither.**

The one independently-fixable bug is **D** (integer → BIGINT), which is wrong in `graph_builder_js`
regardless of approach.

## Likely ingestion relevance

The newman schema lands **0 rows** on every datasource. The candidates from this diff that the ingester
plausibly depends on:

1. **Node Relationship / FK graph absent** (A, B) — isolated tables, no inter-entity edges.
2. **`identity` null on all nodes** (C) — entities were never persisted through the entity layer, so
   there is no entity-graph (`entity-graph/entity-subgraph`) for the stream generator to resolve.
3. **`dataType` mismatch** (D) — declared column types differ from the physical/expected types.

The product-faithful fix (create entities via `POST /entity`, then build the schema from those entity
URIs) resolves 1, 2, and most of C/E in one move.
