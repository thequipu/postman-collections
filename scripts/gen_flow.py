#!/usr/bin/env python3
"""
Master flow generator — generates per-service Postman Flow collections.

Usage:
  python scripts/gen_flow.py                     # Generate ALL flows
  python scripts/gen_flow.py tenant              # Generate just Tenant
  python scripts/gen_flow.py tenant security     # Generate specific flows
  python scripts/gen_flow.py --list              # List available services
"""

import sys
import os

# Add scripts/ to path so flowlib/ is importable
sys.path.insert(0, os.path.dirname(__file__))

from services import tenant, security, realm, schema, entity, permissions
from services import transformation, kg, synapse, nexus, lumen, docgraph, nlp
from services import ingestion, versions, watcher, document_extraction, synapse_query

SERVICES = {
    # Core services
    "tenant":              ("Tenant CRUD",              tenant.generate),
    "security":            ("Security Auth",            security.generate),
    "realm":               ("Realm CRUD",               realm.generate),
    "schema":              ("Schema CRUD",              schema.generate),
    "entity":              ("Entity CRUD",              entity.generate),
    "permissions":         ("Permissions CRUD",          permissions.generate),
    "transformation":      ("Transformation Conn",       transformation.generate),
    "kg":                  ("KnowledgeGraph Metadata",   kg.generate),
    "synapse":             ("Synapse Namespace",         synapse.generate),
    "nexus":               ("Nexus Search",              nexus.generate),
    "lumen":               ("Lumen Pipeline",            lumen.generate),
    "docgraph":            ("DocumentGraph Parse",       docgraph.generate),
    "nlp":                 ("NLP Pipeline",              nlp.generate),
    # Extended coverage
    "ingestion":           ("Ingestion Streams",         ingestion.generate),
    "versions":            ("Version CRUD",              versions.generate),
    "watcher":             ("Watcher CRUD",              watcher.generate),
    "document_extraction": ("Document Extraction",       document_extraction.generate),
    "synapse_query":       ("Synapse Query (Advanced)",  synapse_query.generate),
}


def main():
    args = sys.argv[1:]

    if "--list" in args:
        print("Available services:")
        for key, (name, _) in SERVICES.items():
            print(f"  {key:<18} {name}")
        return

    # If specific services given, generate those; otherwise all
    targets = [a for a in args if not a.startswith("-")]
    if not targets:
        targets = list(SERVICES.keys())

    unknown = [t for t in targets if t not in SERVICES]
    if unknown:
        print(f"ERROR: Unknown service(s): {unknown}")
        print(f"Available: {list(SERVICES.keys())}")
        sys.exit(1)

    print(f"Generating {len(targets)} flow collection(s)...\n")

    for key in targets:
        name, gen_fn = SERVICES[key]
        print(f"  [{key}] {name}")
        gen_fn()

    print(f"\nDone. Generated {len(targets)} collection(s) in flows/")


if __name__ == "__main__":
    main()
