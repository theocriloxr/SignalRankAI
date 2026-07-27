# SignalRankAI V7 Architecture and Critical Flows

**Status:** local repository architecture record  
**Date:** 2026-07-27  
**Deployment target:** Railway modular monolith, one replica and one Uvicorn worker initially

This document describes the architecture represented by the repository after the V7 hardening pass. It does not claim that externally dependent paths have been proven in Railway staging or live production.

## 1. System context

```mermaid
flowchart LR
    User[Telegram user] --> TG[Telegram Bot API]
    TG --> WH[Railway FastAPI webhook ingress]
    TV[TradingView alerts] --> WH
    PS[Paystack webhooks] --> WH

    WH --> RD[(RedisDelivery streams)]
    RD --> APP[SignalRankAI modular monolith]
    APP --> PG[(PostgreSQL via PgBouncer)]
    APP --> RS[(RedisState)]
    APP --> TG

    APP --> MD[Certified market-data providers]
    APP --> GEM[Optional Gemini advisory]
    APP --> META[MetaApi demo broker gateway]

    subgraph Disabled by default
      PAY[Public paid activation]
      EXEC[Real-money execution]
      COPY[Copy trading]
      DCA[Smart DCA]
    end
```

## 2. Runtime component boundaries

```mermaid
flowchart TB
    HTTP[FastAPI ingress and health] --> ACCEPT[Webhook acceptance]
    ACCEPT --> STREAM[RedisDelivery append]
    STREAM --> DISPATCH[Telegram update dispatcher]
    DISPATCH --> COMMANDS[Command registry and handlers]
    DISPATCH --> CALLBACKS[Callback registry and handlers]

    COMMANDS --> ID[Identity, terms, tier and entitlement policy]
    CALLBACKS --> ID
    COMMANDS --> APP[Application services]
    CALLBACKS --> APP

    APP --> MARKET[Instrument master and market-data routing]
    APP --> SIGNAL[Strategies, scoring and risk]
    APP --> DELIVERY[Delivery reservation, send and proof]
    APP --> LIFE[Lifecycle, outcomes and performance]
    APP --> PAPER[Paper, shadow, replay and research]
    APP --> PAYMENT[Payments, receipts and reconciliation]
    APP --> BROKER[Execution intent and reconciliation]

    DELIVERY --> OUTBOX[(PostgreSQL outbox and evidence)]
    LIFE --> PG[(PostgreSQL durable truth)]
    PAYMENT --> PG
    BROKER --> PG
    APP --> STATE[(RedisState reconstructable state)]
```

### Dependency rules

- Domain and policy code must not depend directly on FastAPI, Telegram SDKs, Redis clients, SQLAlchemy sessions, Paystack, MetaApi, Gemini, Railway, or provider SDKs.
- PostgreSQL is durable business truth. Redis is transport or reconstructable state.
- Network I/O occurs after the relevant database transaction closes.
- Public payments, real payouts, automatic trading, copy trading, real execution, live MT5 accounts, and WebSockets are fail-closed in the production example environment.

## 3. Telegram webhook acceptance

```mermaid
sequenceDiagram
    participant TG as Telegram
    participant API as FastAPI webhook
    participant RD as RedisDelivery
    participant W as Update worker
    participant DB as PostgreSQL
    participant BOT as Telegram Bot API

    TG->>API: POST update + secret header
    API->>API: Validate route, size, secret and schema
    API->>RD: XADD versioned update with idempotency metadata
    RD-->>API: Durable stream ID
    API-->>TG: Immediate 2xx

    W->>RD: XREADGROUP
    W->>W: Route command or callback
    W->>DB: Short labelled unit of work
    DB-->>W: Commit result and outbound intent
    W->>BOT: Reply, edit or callback ACK
    BOT-->>W: Telegram result
    W->>DB: Persist message proof or failure state
    W->>RD: XACK only after durable processing
```

## 4. Proof-backed signal delivery and repeat protection

```mermaid
sequenceDiagram
    participant E as Deterministic engine
    participant DB as PostgreSQL
    participant D as Delivery worker
    participant TG as Telegram
    participant R as Repeat policy

    E->>DB: Persist candidate and delivery reservation
    DB-->>D: Outbound intent
    D->>TG: sendMessage
    alt Telegram confirms send
        TG-->>D: chat_id + message_id
        D->>DB: sent_ok=true + delivery proof
        DB-->>R: Proven delivery timestamp
        R->>DB: Start four-hour same-user same-asset lock
    else timeout or uncertain result
        D->>DB: UNKNOWN/RECONCILING state
        R->>DB: Do not start repeat lock
    end
```

## 5. User-scoped signal callback

```mermaid
sequenceDiagram
    participant U as Telegram user
    participant C as Callback handler
    participant DB as PostgreSQL
    participant X as Chart or Gemini service
    participant TG as Telegram Bot API

    U->>C: signal_chart_<id> or ask_gemini_<id>
    C->>TG: Immediate callback ACK
    C->>DB: Verify sent_ok delivery belongs to Telegram user
    DB-->>C: Authorised signal or none
    alt authorised
        C->>X: Generate chart or optional advisory
        X-->>C: Result or explicit unavailable state
        C->>TG: Photo or user-visible response
    else forged, forwarded or stale
        C->>TG: Reject without disclosing signal data
    end
```

## 6. Payment convergence

```mermaid
sequenceDiagram
    participant U as User
    participant API as SignalRankAI
    participant PS as Paystack
    participant DB as PostgreSQL
    participant O as Outbox worker

    U->>API: Request payment initialisation
    API->>DB: Create internal payment reference
    API->>PS: Initialise server-side amount in subunits
    PS-->>API: Authorisation URL and provider reference
    PS->>API: Signed webhook
    API->>DB: Inbox dedupe + pending verification
    API-->>PS: Fast acknowledgement
    O->>PS: Server-side transaction verification
    O->>DB: Match reference, amount, currency, customer and environment
    DB->>DB: Atomically grant entitlement and immutable receipt
```

Public payment activation remains disabled until Paystack test-mode E2E, replay, wrong-amount, refund, receipt, reconciliation, pricing, and legal gates pass.

## 7. Broker execution intent

```mermaid
sequenceDiagram
    participant U as Authorised user
    participant A as Execution application service
    participant DB as PostgreSQL
    participant B as Broker gateway
    participant R as Reconciler

    U->>A: Manual confirmed execution request
    A->>DB: Validate consent, tier, account ownership, mode and idempotency
    A->>A: Validate quote freshness, symbol specification and Decimal risk
    A->>DB: Reserve execution intent
    A->>B: Submit with stable client idempotency key
    alt acknowledgement received
        B-->>A: Order or position ID
        A->>DB: Persist acknowledgement and broker evidence
    else uncertain result
        A->>DB: UNKNOWN_RESULT / RECONCILING
        R->>B: Query broker history and open state
        R->>DB: Resolve without blind resubmission
    end
```

Real execution remains disabled. MetaApi must first be proven with a dedicated demo account.

## 8. Core relational model

```mermaid
erDiagram
    USERS ||--o{ SUBSCRIPTIONS : has
    USERS ||--o{ SIGNAL_DELIVERIES : receives
    USERS ||--o{ ACTIVE_SIGNAL_MESSAGES : owns
    USERS ||--o{ SIGNAL_ENGAGEMENTS : records
    SIGNALS ||--o{ SIGNAL_DELIVERIES : delivered_as
    SIGNALS ||--o{ ACTIVE_SIGNAL_MESSAGES : displayed_as
    SIGNALS ||--|| SIGNAL_LIFECYCLES : tracked_by
    SIGNALS ||--o{ OUTCOMES : produces
    SIGNALS ||--o{ SIGNAL_ENGAGEMENTS : receives
    PAYMENTS ||--o| RECEIPTS : creates
    USERS ||--o{ PAYMENTS : initiates
    USERS ||--o{ BROKER_ACCOUNTS : owns
    BROKER_ACCOUNTS ||--o{ EXECUTION_INTENTS : receives
    EXECUTION_INTENTS ||--o{ BROKER_ORDERS : creates
```

## 9. Activation boundary

The strongest evidence-supported state after this pass is **local repository hardened**. Railway staging, live Telegram probes, PgBouncer/PostgreSQL migration rehearsal, separate Redis services, provider certification, Paystack test-mode E2E, MetaApi demo execution, restore drills, and 24–72 hour soak remain separate release evidence gates.
