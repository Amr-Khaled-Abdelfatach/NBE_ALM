# Analytics & Validation (`analytics.py`)

## KPI comparison

`comparison_table(before, after)` returns 11 KPIs, each with *Before*, *After*, *Absolute Change* and *Change %*:

Position NII, NIM %, Loans, Deposits, Funding, Investments, Loan/Deposit %, Repricing Gap, Cost of Funds %, Liquidity, and CF LCR Proxy %.

## Risk summary

`build_alm_risk_summary(before, after)` produces five indicators.

| Indicator | Rule |
|---|---|
| `POSITION_NII`, `POSITION_NIM` | **ADVERSE** if impact < 0, **POSITIVE** if > 0, else NEUTRAL |
| `POSITION_COF`, `REPRICING_GAP` | INFO |
| `LCR_PROXY` | **HIGH** if below 100 %, **OK** otherwise, UNAVAILABLE if undefined; limit breach flagged |

## Data-quality checks

`build_data_quality_checks()` returns a Check / Status / Detail table:

- latest position date is present
- rate convention note (decimal fraction)
- count of position rates above 200 %
- baseline NII is finite
- `Cash_Flows` loaded (liquidity metrics available)
- `Market_Data` loaded and how many yield-curve tenors are usable
- scenario NII is finite

## Independent calculation validation

`calculation_validation_table()` **recomputes** the main KPIs from raw components and compares them to the engine output (tolerance 0.01 for amounts and 0.0001 for ratios). Each row is PASS, FAIL or SKIP.

| Check | Formula |
|---|---|
| NII reconciliation | Base NII + loan Δ + investment Δ − deposit Δ − funding Δ |
| NIM | NII / (Loans + Investments) × 100 |
| Cost of funds | Interest expense / (Deposits + Funding) × 100 |
| Loan/Deposit | Loans / Deposits × 100 |
| LCR proxy | HQLA / max(Outflow − Inflow, 0) × 100 |
| Position interest | Balance × decimal rate, for the first 20 positions |

The overall result is stored in `Simulation_Runs` when the `calc_validation_status` column exists.
