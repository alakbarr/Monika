# ADR-001: Clean Architecture Layer Boundaries & Inward Dependency Enforcement

## Status
Accepted

## Context
Prior to refactoring, Monika's codebase suffered from extensive cross-layer tangles: circular import cycles, core modules importing infrastructure databases, domain classes performing network calls, and interfaces directly manipulating broker instances. This led to high maintenance friction and untestable paths.

## Decision
Establish strict 4-tier Clean Architecture with inward-only dependencies:
`Interfaces -> Application -> Domain -> Core`
with `Infrastructure` implementing ports defined in inner layers.
Enforce boundaries via `import-linter` contracts executed on every commit and CI run:
1. `Core Layer Boundary`: Core imports only Core (zero domain, application, infra, interfaces).
2. `Domain Layer Boundary`: Domain imports only Domain and Core (zero I/O, zero network, zero SQL).
3. `Application Layer Boundary`: Application imports only Application, Domain, and Core (communicates with Infrastructure via abstract Protocols/ABCs).

## Consequences
- **Positive**: 1,860+ layer violations reduced to 0; circular module dependencies eliminated; testability of domain logic in pure unit tests without mocks or database fixtures.
- **Trade-offs**: Requires explicit port declarations and dependency injection via `ServiceContainer` instead of direct ad-hoc imports.
