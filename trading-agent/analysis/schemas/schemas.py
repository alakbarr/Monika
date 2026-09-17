from pydantic import BaseModel, Field
from typing import Optional, Literal, Any, Dict, List

def _inline_refs(schema, defs=None):
    """
    Recursively replaces $ref with the actual schema definitions to produce
    a flat JSON schema compatible with raw tool execution payloads.
    Also simplifies anyOf null structures common in Pydantic v2 Optionals.
    """
    if defs is None:
        defs = schema.pop('$defs', {}) if isinstance(schema, dict) else {}
        
    if isinstance(schema, dict):
        if '$ref' in schema:
            ref_name = schema['$ref'].split('/')[-1]
            if ref_name in defs:
                resolved = _inline_refs(dict(defs[ref_name]), defs)
                extra = {k: v for k, v in schema.items() if k != '$ref'}
                if extra:
                    resolved.update(_inline_refs(extra, defs))
                return resolved
            return schema
            
        # Simplify anyOf with null (Pydantic v2 Optionals)
        if 'anyOf' in schema:
            any_of = schema['anyOf']
            null_branches = [s for s in any_of if isinstance(s, dict) and s.get('type') == 'null']
            non_null_branches = [s for s in any_of if not (isinstance(s, dict) and s.get('type') == 'null')]
            
            if null_branches and len(non_null_branches) == 1:
                non_null_schema = non_null_branches[0]
                merged = {k: v for k, v in schema.items() if k != 'anyOf'}
                resolved_non_null = _inline_refs(non_null_schema, defs)
                if isinstance(resolved_non_null, dict):
                    merged.update(resolved_non_null)
                return merged
            elif null_branches and len(non_null_branches) > 1:
                merged = {k: v for k, v in schema.items()}
                merged['anyOf'] = [_inline_refs(s, defs) for s in any_of]
                return merged

        return {k: _inline_refs(v, defs) for k, v in schema.items()}
        
    elif isinstance(schema, list):
        return [_inline_refs(item, defs) for item in schema]
        
    return schema

def get_tool_schema(pydantic_model: type[BaseModel]) -> dict:
    """Generate a flattened JSON schema for a tool definition."""
    schema = pydantic_model.model_json_schema()
    return _inline_refs(schema)

# =============================================================================
# Sub-Schemas & Tool Input Schemas
# (Migrated to pydantic_schemas.py)
# =============================================================================

from analysis.schemas.pydantic_schemas import (
    EntryCondition,
    ReevaluationTrigger,
    PricedInOverrideJustification,
    UpcomingRiskEvent,
    PricedInAssessment,
    SubmitAssetAnalysisSchema,
    SubmitFundamentalBriefSchema
)
