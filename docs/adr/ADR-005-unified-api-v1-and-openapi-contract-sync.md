# ADR-005: Unified API v1 Standard & OpenAPI TypeScript Contract Sync

## Status
Accepted

## Context
Dashboard REST routes previously lacked versioning prefixes (`/api/...`), lacked formal Pydantic response models, and the React frontend maintained hand-written TypeScript type files (`types/api.ts` with 1,178 lines) that suffered from silent drift against backend responses.

## Decision
1. Standardize all 95+ REST endpoints under explicit `/api/v1` prefix.
2. Formulate canonical Pydantic response models in `schemas.py` and bind `response_model` across all router decorators.
3. Automate TypeScript type generation via `scripts/generate_openapi_types.py` extracting schema directly from `FastAPI.openapi()`.
4. Enforce zero drift in CI via `--check` mode and automated frontend-backend parity tests (`tests/test_api_frontend_contract.py`).

## Consequences
- **Positive**: Strict compile-time and runtime type safety; zero contract drift between Python backend and React frontend; clean OpenAPI 3.1 documentation.
- **Trade-offs**: Frontend and backend endpoint URLs must be kept in sync using the automated generator whenever schema definitions change.
