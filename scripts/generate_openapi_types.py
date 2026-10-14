#!/usr/bin/env python3
# ==============================================================================
# File: scripts/generate_openapi_types.py
# Description: Generate OpenAPI JSON & TypeScript definitions from FastAPI schema
# ==============================================================================

"""
Automated OpenAPI TypeScript generator.

Extracts canonical OpenAPI 3.1.0 schema directly from FastAPI app instance
and compiles TypeScript interfaces and route contract types into frontend/src/types/.
Supports --check flag for zero-drift verification in CI/CD pipeline.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Set

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))


def get_openapi_spec() -> Dict[str, Any]:
    """Import FastAPI app and generate OpenAPI dictionary."""
    os.environ["FASTAPI_DOCS_DISABLE"] = "false"
    from monika.interfaces.dashboard.api import app

    return app.openapi()


def schema_to_ts_type(prop: Dict[str, Any], components: Dict[str, Any]) -> str:
    """Convert an OpenAPI property schema to a TypeScript type string."""
    if "$ref" in prop:
        ref_name = prop["$ref"].split("/")[-1]
        return ref_name

    prop_type = prop.get("type")
    if prop_type == "string":
        if "enum" in prop:
            return " | ".join(f"'{val}'" for val in prop["enum"])
        return "string"
    elif prop_type in ("integer", "number"):
        return "number"
    elif prop_type == "boolean":
        return "boolean"
    elif prop_type == "array":
        items = prop.get("items", {})
        item_type = schema_to_ts_type(items, components)
        return f"{item_type}[]"
    elif prop_type == "object":
        if "additionalProperties" in prop and isinstance(prop["additionalProperties"], dict):
            val_type = schema_to_ts_type(prop["additionalProperties"], components)
            return f"Record<string, {val_type}>"
        return "Record<string, unknown>"
    elif "anyOf" in prop:
        sub_types = [schema_to_ts_type(sub, components) for sub in prop["anyOf"] if sub.get("type") != "null"]
        if any(sub.get("type") == "null" for sub in prop["anyOf"]):
            sub_types.append("null")
        return " | ".join(sub_types) if sub_types else "unknown"

    return "unknown"


def generate_typescript(spec: Dict[str, Any]) -> str:
    """Compile OpenAPI components.schemas into TypeScript declarations."""
    lines: List[str] = [
        "/* eslint-disable */",
        "/**",
        " * AUTO-GENERATED FILE - DO NOT EDIT MANUALLY.",
        " * Generated from FastAPI OpenAPI schema via scripts/generate_openapi_types.py",
        " */",
        "",
    ]

    components = spec.get("components", {})
    schemas = components.get("schemas", {})

    for schema_name, schema_def in sorted(schemas.items()):
        if schema_def.get("type") == "object":
            lines.append(f"export interface {schema_name} {{")
            properties = schema_def.get("properties", {})
            required_fields: Set[str] = set(schema_def.get("required", []))

            for prop_name, prop_def in sorted(properties.items()):
                is_opt = prop_name not in required_fields
                ts_type = schema_to_ts_type(prop_def, components)
                desc = prop_def.get("description")
                if desc:
                    lines.append(f"  /** {desc} */")
                lines.append(f"  {prop_name}{'?' if is_opt else ''}: {ts_type};")

            lines.append("}\n")
        elif "enum" in schema_def:
            vals = " | ".join(f"'{v}'" for v in schema_def["enum"])
            lines.append(f"export type {schema_name} = {vals};\n")

    # Generate Endpoint Contract Map
    lines.append("/** Registered API Routes and Methods */")
    lines.append("export interface ApiEndpoints {")
    paths = spec.get("paths", {})
    for path, path_item in sorted(paths.items()):
        for method in ("get", "post", "put", "delete", "patch"):
            if method in path_item:
                op = path_item[method]
                summary = op.get("summary") or op.get("operationId") or ""
                lines.append(f"  '{method.upper()} {path}': {{")
                lines.append(f"    summary: '{summary}';")
                lines.append("  };")
    lines.append("}\n")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate OpenAPI JSON & TypeScript definitions.")
    parser.add_argument("--check", action="store_true", help="Check for drift without writing files.")
    parser.add_argument(
        "--json-out",
        type=Path,
        default=ROOT_DIR / "frontend" / "src" / "types" / "openapi.json",
        help="Path to output openapi.json",
    )
    parser.add_argument(
        "--ts-out",
        type=Path,
        default=ROOT_DIR / "frontend" / "src" / "types" / "openapi.ts",
        help="Path to output openapi.ts",
    )
    args = parser.parse_args()

    spec = get_openapi_spec()
    spec_json = json.dumps(spec, indent=2, sort_keys=True) + "\n"
    ts_code = generate_typescript(spec)

    if args.check:
        drift = False
        if args.json_out.exists():
            current_json = args.json_out.read_text(encoding="utf-8")
            if current_json != spec_json:
                print(f"[DRIFT DETECTED] {args.json_out} is out of sync with FastAPI schema.")
                drift = True
        else:
            print(f"[DRIFT DETECTED] {args.json_out} does not exist.")
            drift = True

        if args.ts_out.exists():
            current_ts = args.ts_out.read_text(encoding="utf-8")
            if current_ts != ts_code:
                print(f"[DRIFT DETECTED] {args.ts_out} is out of sync with FastAPI schema.")
                drift = True
        else:
            print(f"[DRIFT DETECTED] {args.ts_out} does not exist.")
            drift = True

        if drift:
            print("Run `python scripts/generate_openapi_types.py` to synchronize contracts.")
            return 1
        print("[OK] OpenAPI TypeScript contracts are 100% in sync.")
        return 0

    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(spec_json, encoding="utf-8")
    print(f"Generated: {args.json_out}")

    args.ts_out.parent.mkdir(parents=True, exist_ok=True)
    args.ts_out.write_text(ts_code, encoding="utf-8")
    print(f"Generated: {args.ts_out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
