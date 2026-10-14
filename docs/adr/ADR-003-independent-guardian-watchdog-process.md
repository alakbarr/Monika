# ADR-003: Independent OS Guardian Watchdog Process

## Status
Accepted

## Context
If the primary Python process freezes due to an unhandled asyncio event loop block, GIL contention, or heavy synchronous operations, in-process kill switches and emergency listeners become unresponsive. In live financial markets, an unmonitored frozen system can incur unmitigated drawdown.

## Decision
Implement `GuardianProcess` and `GuardianSupervisor` running as an isolated child OS process on dedicated port 8001:
1. Listens on `/kill`, `/health`, and `/shutdown`.
2. Monitors heartbeat timestamps written to shared runtime storage (`stale > 60s`).
3. Possesses dedicated authority to trigger emergency position liquidation and set emergency halt flags even when PID A (main daemon) is completely locked up.

## Consequences
- **Positive**: Guaranteed emergency responsiveness and MT5 liquidation capability even under total daemon event loop stalls.
- **Trade-offs**: Requires dual-process lifecycle management and cross-process heartbeat synchronization via filesystem flags and IPC.
