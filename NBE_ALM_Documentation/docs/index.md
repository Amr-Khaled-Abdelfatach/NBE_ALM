# NBE ALM Simulation Center

A Streamlit application that lets ALM analysts run **what-if interest-rate and liquidity scenarios** on a bank balance sheet and compare *Before* vs *After* results, backed by an existing MySQL database.

!!! note "Prototype status"
    This is a prototype with an NBE-inspired visual theme. It is not an official NBE-branded application.

## What it does

| Capability | Description |
|---|---|
| Baseline | Builds NII, NIM, cost of funds, loan/deposit ratio, repricing gap and LCR proxy from the latest `Positions` snapshot and `Cash_Flows`. |
| Scenarios | Rate shock, pass-through, loan/deposit growth, liquidity shift; as templates, individual parameters, combined stress, or free text. |
| Repricing engine | Event-based interest calculation driven by the `Market_Data` yield curve. |
| Analytics | KPI comparison, risk summary, data-quality checks, independent calculation validation. |
| Persistence | Saves scenario, run and KPI results back to MySQL for history and audit. |
| Local AI | Optional Ollama/Phi-3 for parsing free-text scenarios and explaining results. |

## Core design principles

1. **Deterministic calculations.** All financial numbers come from Python code. The LLM never calculates or overwrites a number (`AI_EXPLANATION_ONLY = True`).
2. **Existing database, no DDL.** The application never creates or alters tables. It validates that the 7 required tables exist.
3. **Clear data domains.** Interest/NII metrics use `Positions` (+ `Market_Data`); liquidity metrics use `Cash_Flows` only. Financial Statements are out of scope.
4. **Self-checking.** An independent validation table recomputes key KPIs and reports PASS / FAIL.
5. **Local-first AI.** Ollama runs locally, so no bank data is sent to an external service.

## Technology stack

Python, Streamlit (UI), pandas / NumPy (calculations), SQLAlchemy + PyMySQL (database), Plotly (charts), Ollama + Phi-3 (optional AI).

## Code map

| File | Role |
|---|---|
| `app.py` | Thin entry point; calls `ui.run_app()`. |
| `config.py` | Constants, defaults, limits, DB/AI settings, theme. |
| `database.py` | Connection, table validation, reads, persistence. |
| `calculations.py` | Normalization, market curve, repricing, scenario engine. |
| `scenarios.py` | Scenario mapping, free-text parsing, Ollama integration. |
| `analytics.py` | KPI comparison, risk summary, data quality, validation. |
| `ui.py` | All Streamlit pages and charts. |
