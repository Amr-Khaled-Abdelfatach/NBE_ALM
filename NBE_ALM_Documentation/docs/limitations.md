# Limitations & Roadmap

An honest list of current boundaries. Knowing them is part of using the model correctly.

## Modelling

| # | Limitation | Impact |
|---|---|---|
| 1 | **Growth does not change interest.** In `dynamic_repricing_calculation`, interest uses `Before Balance`; loan/deposit growth only changes the reported balances (NIM, cost of funds, Loan/Deposit, gap). | Growth scenarios do not move NII. |
| 2 | **Market_Data drives the rate effect.** If no usable curve exists, the market delta is 0 and a rate shock has no effect on interest. | Make sure the curve is loaded. |
| 3 | `loan_rate_shock_pp`, `deposit_rate_shock_pp`, `funding_rate_shock_pp` are echoed in the output but not used in the calculation; the effect flows through the curve shock and pass-through. | Per-product shocks are not independent yet. |
| 4 | **No FX conversion.** `USD` rows exist in `Positions`/`Cash_Flows` but amounts are summed as EGP. | Mixed-currency totals are approximate. |
| 5 | LCR is a **proxy**: it uses all loaded cash-flow rows (not a 30-day window) and no run-off factors. | Not a regulatory LCR. |
| 6 | Simple interest, Actual/365, parallel shock only; no optionality (prepayment, behavioural deposits) and no EVE. | NII-focused sensitivity only. |
| 7 | Positions maturing inside the horizon are not rolled over. | Conservative run-off view. |
| 8 | Numbers use `float` (pandas/NumPy), not `Decimal`. | Tiny rounding differences; acceptable for simulation, not for booking. |

## Data and persistence

| # | Limitation | Impact |
|---|---|---|
| 9 | **Table-name case.** Code uses `Products`, `Positions`…, while the dump creates lower-case names (`products`…). Works on Windows MySQL; on Linux (`lower_case_table_names=0`) the table check fails. | Align the names or set the server option. |
| 10 | `calc_*` audit columns, `expected_value`, `validation_status` and `investment_pass_through_pct` are not in the provided schema. Writes are filtered, so they are silently skipped. | Add the columns to persist full audit data; today an investment pass-through value is not saved with the scenario. |
| 11 | All seven tables are re-read on every Streamlit rerun (limit 100 000 rows each). | Add `st.cache_data` for larger data. |
| 12 | Some `config.py` values (`MAX_REPRICING_EVENTS`, `CALCULATION_TOLERANCE`, `RATE_WARNING_THRESHOLD`) are defined but the code uses its own constants (e.g. 120 events). | Wire config to the engine. |

## Code quality

- `template_values`, `visible_params_for_scenario_type`, `resolve_saved_template` and `build_saved_template_values` exist in both `scenarios.py` and `ui.py`; keep one copy.
- No automated test suite yet.
- Docstrings are sparse, so the API Reference shows signatures only.

## Roadmap

1. Apply growth to balances inside the interest calculation.
2. FX conversion and per-currency reporting.
3. Non-parallel curve shocks (steepener, flattener) and per-product shocks.
4. Regulatory-style LCR/NSFR with a 30-day window and run-off factors; EVE (economic value of equity).
5. Authentication, roles, and per-user audit trail.
6. Unit tests for the engine plus CI; caching and pagination for large data.
