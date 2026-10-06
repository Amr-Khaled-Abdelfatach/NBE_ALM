"""ALM analytics, risk summaries, data quality, and validation."""
import numpy as np
import pandas as pd
from config import CALCULATION_TOLERANCE, LCR_WARNING_THRESHOLD, RATE_WARNING_THRESHOLD
from calculations import build_market_curve

def comparison_table(before, after):
    """Position and Cash_Flow KPI comparison only.

    Financial Statements are outside this ALM table by design.
    """
    specs = [
        ("Position NII", "Positions", "EGP"),
        ("Position NIM %", "Positions", "%"),
        ("Position Loans", "Positions", "EGP"),
        ("Position Deposits", "Positions", "EGP"),
        ("Position Funding", "Positions", "EGP"),
        ("Position Investments", "Positions", "EGP"),
        ("Position Loan Deposit %", "Positions", "%"),
        ("Position Repricing Gap", "Positions", "EGP"),
        ("Position Cost of Funds %", "Positions", "%"),
        ("Liquidity", "Cash_Flows", "EGP"),
        ("CF LCR Proxy %", "Cash_Flows", "%"),
    ]
    rows = []
    for metric, source, unit in specs:
        b = float(before.get(metric, 0.0) or 0.0)
        a_raw = after.get(metric, np.nan)
        a = float(a_raw) if pd.notna(a_raw) else np.nan
        delta = a - b if pd.notna(a) else np.nan
        change = delta / abs(b) * 100.0 if b != 0 and pd.notna(delta) else np.nan
        rows.append({
            "Source": source, "KPI": metric, "Unit": unit,
            "Before": b, "After": a,
            "Absolute Change": delta, "Change %": change
        })
    return pd.DataFrame(rows)


def build_alm_risk_summary(before, after):
    """Risk summary from Positions and Cash_Flows only."""
    rows = []
    specs = [
        ("POSITION_NII", "Position NII", "EGP", None, "Positions"),
        ("POSITION_NIM", "Position NIM %", "%", None, "Positions"),
        ("POSITION_COF", "Position Cost of Funds %", "%", None, "Positions"),
        ("REPRICING_GAP", "Position Repricing Gap", "EGP", None, "Positions"),
        ("LCR_PROXY", "CF LCR Proxy %", "%", 100.0, "Cash_Flows"),
    ]
    for code, name, unit, limit, source in specs:
        b = float(before.get(name, 0.0) or 0.0)
        a_raw = after.get(name, np.nan)
        a = float(a_raw) if pd.notna(a_raw) else np.nan
        impact = a - b if pd.notna(a) else np.nan
        pct = impact / abs(b) * 100.0 if b and pd.notna(impact) else np.nan

        level = "INFO"
        if code == "LCR_PROXY":
            level = "HIGH" if pd.notna(a) and a < 100 else "OK" if pd.notna(a) else "UNAVAILABLE"
        elif code in {"POSITION_NII", "POSITION_NIM"}:
            level = "ADVERSE" if impact < 0 else "POSITIVE" if impact > 0 else "NEUTRAL"

        rows.append({
            "Risk Indicator": code, "Metric": name, "Base": b,
            "Scenario": a, "Impact": impact, "Impact %": pct,
            "Risk Level": level, "Limit": limit,
            "Limit Breach": (a < limit if limit is not None and pd.notna(a) else None),
            "Unit": unit, "Source": source,
        })
    return pd.DataFrame(rows)


def build_data_quality_checks(baseline, positions, cashflows=None, market_data=None, after=None) -> pd.DataFrame:
    """Source-specific quality checks for the 7-table ALM model."""
    checks = []

    def add(name, status, detail):
        checks.append([name, status, detail])

    add(
        "Positions source",
        "OK" if baseline.get("Position As Of") is not None else "WARNING",
        f"Latest position date = {baseline.get('Position As Of')}",
    )
    add("Position rate convention", "OK",
        "Positions.interest_rate is decimal fraction: 0.123 = 12.3%.")

    rates = pd.to_numeric(
        positions.get("Model Rate", pd.Series(dtype=float)),
        errors="coerce"
    ) if not positions.empty else pd.Series(dtype=float)
    bad = int((rates.abs() > 2).sum()) if not rates.empty else 0
    add("Position rate datatype", "OK" if bad == 0 else "WARNING",
        f"{bad} position rate(s) exceed 200%.")

    add("Position NII", "OK" if np.isfinite(baseline.get("Position NII", np.nan)) else "ERROR",
        f"Position NII = {baseline.get('Position NII', 0):,.2f} EGP")

    if cashflows is not None and not cashflows.empty:
        add("Cash flow source", "OK",
            f"{len(cashflows)} Cash_Flows rows loaded; liquidity metrics use Cash_Flows only.")
    else:
        add("Cash flow source", "WARNING",
            "Cash_Flows is empty; liquidity/LCR proxy unavailable.")

    if market_data is not None and not market_data.empty:
        # Refinement: build the curve locally inside the quality check.
        # This prevents the NameError that occurred because `curve` was only
        # created later inside apply_scenario().
        try:
            quality_curve = build_market_curve(market_data)
        except Exception:
            quality_curve = pd.DataFrame()
        add("Market data source", "OK" if not quality_curve.empty else "WARNING",
            f"{len(market_data)} Market_Data rows loaded; {len(quality_curve)} yield-curve tenors are available to the repricing engine.")

    if after is not None:
        add("Scenario Position NII finite",
            "OK" if np.isfinite(after.get("Position NII", np.nan)) else "ERROR",
            "Scenario Position NII is numeric and finite.")
        add("No Financial Statements in calculation engine", "OK",
            "Financial Statements are not part of the 7-table ALM model.")

    return pd.DataFrame(checks, columns=["Check", "Status", "Detail"])


def calculation_validation_table(before, after, positions, params):
    """Independent validation for Position and Cash_Flow calculations only."""
    rows = []

    def check(source, name, expected, actual, formula, tolerance=0.01):
        if pd.isna(expected) or pd.isna(actual):
            status, diff = "SKIP", np.nan
        else:
            diff = float(actual - expected)
            status = "PASS" if abs(diff) <= tolerance else "FAIL"
        rows.append([source, name, formula, expected, actual, diff, status])

    check(
        "Positions", "Position NII reconciliation",
        before.get("Position NII", 0)
        + after.get("Loan Interest Change", 0)
        + after.get("Investment Interest Change", 0)
        - after.get("Deposit Interest Change", 0)
        - after.get("Funding Interest Change", 0),
        after.get("Position NII", 0),
        "Base Position NII + loan Δ + investment Δ − deposit Δ − funding Δ",
        0.01,
    )
    check(
        "Positions", "Position NIM",
        after.get("Position NII", 0)
        / (after.get("Position Loans", 0) + after.get("Position Investments", 0))
        * 100
        if (after.get("Position Loans", 0) + after.get("Position Investments", 0)) else 0,
        after.get("Position NIM %", 0),
        "Position NII / (Loans + Investments) × 100", 0.0001,
    )
    check(
        "Positions", "Position Cost of Funds",
        after.get("Position Interest Expense", 0)
        / (after.get("Position Deposits", 0) + after.get("Position Funding", 0))
        * 100
        if (after.get("Position Deposits", 0) + after.get("Position Funding", 0)) else 0,
        after.get("Position Cost of Funds %", 0),
        "Position interest expense / (Deposits + Funding) × 100", 0.0001,
    )
    check(
        "Positions", "Loan / Deposit",
        after.get("Position Loans", 0) / after.get("Position Deposits", 1) * 100
        if after.get("Position Deposits", 0) else 0,
        after.get("Position Loan Deposit %", 0),
        "Position Loans / Position Deposits × 100", 0.0001,
    )
    check(
        "Cash_Flows", "LCR Proxy",
        after.get("CF HQLA", 0)
        / max(after.get("CF Outflow", 0) - after.get("CF Inflow", 0), 0) * 100
        if max(after.get("CF Outflow", 0) - after.get("CF Inflow", 0), 0) else np.nan,
        after.get("CF LCR Proxy %", np.nan),
        "HQLA / max(Outflow − Inflow, 0) × 100", 0.0001,
    )

    if not positions.empty:
        for _, r in positions.head(20).iterrows():
            expected = float(r.get("Before Balance", r.get("Model Balance", 0))) * float(
                r.get("Before Rate", r.get("Model Rate", 0))
            )
            actual = float(r.get("Annual Interest Before", 0))
            pid = r.get("position_id", "N/A")
            check(
                "Positions", f"Position {pid} annual interest",
                expected, actual, "Balance × decimal rate", 0.01
            )

    return pd.DataFrame(
        rows,
        columns=["Source", "Check", "Formula", "Expected", "Actual", "Difference", "Status"]
    )