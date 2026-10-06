# Architecture

## Layered view

```mermaid
graph TD
    U[Analyst / Browser] --> UI[ui.py - Streamlit pages]
    UI --> SC[scenarios.py - parameters, templates, free text]
    UI --> AN[analytics.py - KPIs, risk, quality, validation]
    UI --> DB[database.py - read and persist]
    UI --> CALC[calculations.py - deterministic engine]
    SC -.explain only.-> OLL[(Ollama / Phi-3)]
    AN --> CALC
    DB --> CALC
    DB --> MYSQL[(MySQL - 7 tables)]
    CALC --> CFG[config.py]
    SC --> CFG
    AN --> CFG
    DB --> CFG
    UI --> CFG
```

## Module dependencies

`config` is the base and depends on nothing. `calculations` depends only on `config`. `database`, `analytics` and `scenarios` depend on `config` (and `calculations` for the first two). `ui` imports everything. There are no circular imports.

## End-to-end flow of one simulation

```mermaid
sequenceDiagram
    participant U as User
    participant UI as ui.py
    participant DB as database.py
    participant C as calculations.py
    participant A as analytics.py
    U->>UI: Open app
    UI->>DB: connect_existing_database()
    DB-->>UI: engine (7 tables validated)
    UI->>DB: read_table() x7
    UI->>C: select_latest_positions(), build_model_baseline()
    U->>UI: Choose scenario and Run
    UI->>C: apply_scenario(baseline, positions, market_data, params)
    C-->>UI: after KPIs + position-level results
    UI->>A: comparison_table, build_alm_risk_summary
    UI->>A: calculation_validation_table, build_data_quality_checks
    UI->>DB: persist_simulation()
    DB-->>UI: run_id, scenario_id
```

## State handling

Streamlit re-executes the script on every interaction. Connection settings, the active template, current scenario parameters and AI output are kept in `st.session_state`. The 7 tables are re-read from MySQL on each rerun (see [Limitations](limitations.md)).

## Local AI boundary

```mermaid
graph LR
    T[Free text] --> P{Ollama available?}
    P -- yes --> J[Phi-3 returns JSON]
    P -- no --> R[Regex parser]
    J --> M[Merge: regex fills gaps]
    R --> M
    M --> E[Numeric parameters]
    E --> D[Deterministic engine]
    D --> X[Numbers]
    X -.read only.-> O[Phi-3 explanation]
```

The model only (a) extracts explicit numbers from text and (b) narrates results already computed in Python.
