# Monika System Architecture & Technical Specification

> **Version**: 1.0.0 | **Author**: Saiful Akbar | **Status**: Production-Ready

---

## 1. Architectural Philosophy & Layer Discipline

Monika is structured under strict **Clean Architecture (Hexagonal / Ports-and-Adapters)** principles. Dependencies flow **strictly inward**:

```mermaid
flowchart TD
    subgraph L4["Interfaces Layer"]
        CLI["CLI / TUI Textual"]
        TG["Telegram Bot & Webhooks"]
        WEB["Dashboard (FastAPI / Vite React)"]
        GW["Gateway (ACP / OpenAI Ingress)"]
    end

    subgraph L3["Application Layer"]
        BOOT["Bootstrap / ServiceContainer"]
        USE["Use-Case Services (Trading, Risk, Intel)"]
        HARN["Agent Harness & Subagents"]
        SCHED["Cron & Poller Schedulers"]
    end

    subgraph L2["Domain Layer"]
        RISK["Mechanical Fortress (RiskGate)"]
        ALPHA["Alpha Zoo (463 Formulas)"]
        MODELS["Pure Domain Models & Invariants"]
    end

    subgraph L1["Core Layer"]
        CONFIG["Config (AtomicWriter / EnvValidator)"]
        LOGS["Telemetry & Structured Logging"]
        TYPES["Domain Primitives & Constants"]
    end

    subgraph INFRA["Infrastructure Layer (Implements Ports)"]
        MT5["MT5 Broker Client & Wine Bridge"]
        DB["PostgreSQL / AsyncSession / Alembic"]
        LLM["Gemini / OpenRouter Client Adapters"]
        NOTIF["Telegram & Discord Emitters"]
    end

    L4 --> L3
    L3 --> L2
    L2 --> L1
    INFRA --> L2
    INFRA --> L1
    L3 -.->|Consumes via Ports| INFRA
```

### Layer Rules & Invariants
1. **Interfaces Layer (`src/monika/interfaces`)**:
   - Thin adapters translating protocol/UI events into application use-case calls.
   - Zero financial calculation, zero SQL, zero direct broker communication.
2. **Application Layer (`src/monika/application`)**:
   - Orchestration workflows, background task management, and composition root.
   - Depends only on Domain and Core; communicates with Infrastructure strictly via abstract interfaces (ports).
3. **Domain Layer (`src/monika/domain`)**:
   - Business entities, deterministic risk algorithms, mathematical sizing, and alpha formulas.
   - Pure Python: zero network, zero database, zero framework imports.
4. **Core Layer (`src/monika/core`)**:
   - Primitive data types, configuration parsers, and low-level utility primitives.
5. **Infrastructure Layer (`src/monika/infrastructure`)**:
   - Concrete implementations of external systems: MT5 bridge, PostgreSQL database, AI model providers, scrapers.

---

## 2. Process Topology & Mechanical Fortress

```mermaid
graph TD
    subgraph System["Operating System Environment"]
        subgraph Daemon["Main Daemon Process (PID A)"]
            APP["FastAPI App (Port 8000)"]
            WS["WebSocket Live Streamer"]
            SCHEDULER["Analysis Cycle Scheduler"]
            RISK_GATE["Deterministic RiskGate Filter"]
            EXEC["Execution Service"]
        end

        subgraph Guardian["Guardian Process (PID B)"]
            SUPER["Guardian Supervisor (Port 8001)"]
            KILL_EP["/kill Emergency Endpoint"]
            WATCHDOG["Heartbeat Watchdog (Stale > 60s)"]
            FLAG["Emergency Halt Flag"]
        end

        subgraph Broker["MetaTrader 5 Terminal"]
            EA["Watchdog Expert Advisor"]
            SOCKET["IPC Socket / Native API"]
        end
    end

    APP --> WS
    SCHEDULER --> RISK_GATE
    RISK_GATE -->|Approved Trade| EXEC
    EXEC --> SOCKET
    SOCKET --> EA

    SUPER --> WATCHDOG
    WATCHDOG -.->|Kill Signal on Freeze| SOCKET
    KILL_EP -.->|Immediate Order Liquidation| SOCKET
    FLAG -.->|Halt Execution| RISK_GATE
```

### The Invariants of the Mechanical Fortress
- **Rule 1 (AI Proposes, Fortress Disposes)**: LLMs formulate structured trade hypotheses; LLMs NEVER talk directly to broker sockets or place orders.
- **Rule 2 (Unbypassable RiskGate)**: Every trade must satisfy position sizing, margin capacity, drawdown ceilings, and stop-loss invariants.
- **Rule 3 (Fail-Closed Execution)**: In any calculation error, network timeout, or ambiguous signal, the proposal is rejected immediately.
- **Rule 4 (Autonomous Watchdog)**: The independent Guardian process on port 8001 liquidates positions and halts trading even if the primary Python event loop is blocked.
- **Rule 5 (Paper Trading by Default)**: All operations run in simulated paper mode unless live credentials and explicit human operator confirmation are present.
