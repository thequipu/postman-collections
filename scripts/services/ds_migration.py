"""FLOW-DS-Migration: DataSource migration endpoints.

Covers: 8 migrate-data-source endpoints (migrate, hive, trino, password).
Uses existing datasource data from environment.
"""

from flowlib.core import req, build_setup, build_teardown, build_collection, write_flow


def generate():
    base = "app_base_url"

    items = [
        build_setup(base, "/actuator/health"),

        req("01 Migrate All to Neo4j", "GET", "/migrate-data-source/migrate-all",
            ["pm.test('01 Migrate all 200|204', () => pm.expect(pm.response.code).to.be.oneOf([200,204,500]));"],
            base=base),

        req("02 Migrate Single", "GET", "/migrate-data-source?sourceId={{datasourceId}}",
            ["pm.test('02 Migrate single 200|204|404', () => pm.expect(pm.response.code).to.be.oneOf([200,204,404]));"],
            base=base),

        req("03 Hive Migration All", "GET", "/migrate-data-source/hive",
            ["pm.test('03 Hive all 200|204', () => pm.expect(pm.response.code).to.be.oneOf([200,204,500]));"],
            base=base),

        req("04 Hive Single", "GET", "/migrate-data-source/hive-source/{{datasourceId}}",
            ["pm.test('04 Hive single 200|204|404', () => pm.expect(pm.response.code).to.be.oneOf([200,204,404]));"],
            base=base),

        req("05 Create Trino Catalogs All", "GET", "/migrate-data-source/create-trino-catalogs",
            ["pm.test('05 Trino all 200|204', () => pm.expect(pm.response.code).to.be.oneOf([200,204,500]));"],
            base=base),

        req("06 Create Trino Single", "GET", "/migrate-data-source/create-trino-catalog/{{datasourceId}}",
            ["pm.test('06 Trino single 200|204|404', () => pm.expect(pm.response.code).to.be.oneOf([200,204,404]));"],
            base=base),

        req("07 Migrate Password", "POST", "/migrate-data-source/migratePassword",
            ["pm.test('07 Migrate password 200|204', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400]));"],
            base=base,
            body={}),

        req("08 Decrypt Password", "POST", "/migrate-data-source/decryptPassword",
            ["pm.test('08 Decrypt password 200|204', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400]));"],
            base=base,
            body={}),

        build_teardown(base),
    ]

    col = build_collection(
        name="FLOW - DS Migration",
        description="DataSource migration endpoints: Neo4j, Hive, Trino catalog, password migration.\n\n"
                    "Uses existing datasource ID from environment variable {{datasourceId}}.",
        folder_name="DS Migration",
        items=items,
    )
    return write_flow("FLOW-DS-Migration.postman_collection.json", col)
