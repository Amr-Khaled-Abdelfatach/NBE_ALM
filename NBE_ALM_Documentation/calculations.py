"""Deterministic ALM calculation engine."""
from typing import Optional, Dict
import re
import numpy as np
import pandas as pd
from config import (MODEL_AMOUNT_UNIT, TENOR_DAY_FACTORS, DEFAULT_REFERENCE_TENOR_DAYS,
                     MAX_REFERENCE_TENOR_DAYS, MAX_REPRICING_EVENTS, DAYS_PER_YEAR)

def col(df: pd.DataFrame, name: str) -> Optional[str]:
    if df.empty:
        return None
    lookup = {str(c).lower(): c for c in df.columns}
    return lookup.get(name.lower())


def to_num(series, default=0.0):
    return pd.to_numeric(series, errors="coerce").fillna(default)


def normalize_products(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=[
            "product_id", "product_code", "product_name", "product_type",
            "asset_liability_type", "currency_code", "rate_type", "default_rate",
            "repricing_frequency", "active_flag", "tenor", "Interest_Frequency"
        ])
    x = df.copy()
    for c in ["default_rate"]:
        if c in x.columns:
            x[c] = to_num(x[c])
    for c in ["product_id", "active_flag"]:
        if c in x.columns:
            x[c] = pd.to_numeric(x[c], errors="coerce")
    return x


def normalize_positions(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize the new single Positions table without changing database values."""
    if df.empty:
        return pd.DataFrame()
    x = df.copy()
    x["Position Category"] = x.get("position_type", "Other").fillna("Other").astype(str)
    x["Model Balance"] = to_num(x.get("balance_amount", 0.0))
    # IMPORTANT: interest_rate is already a decimal fraction in the new DB.
    # Example: 0.123 = 12.3%, so do NOT divide it by 100.
    x["Model Rate"] = to_num(x.get("interest_rate", 0.0))
    x["Model Rate Type"] = x.get("rate_type", "Unknown").fillna("Unknown").astype(str)
    x["Model Repricing Date"] = pd.to_datetime(x.get("next_repricing_date"), errors="coerce")
    x["Model Maturity Date"] = pd.to_datetime(x.get("maturity_date"), errors="coerce")
    x["Model Currency"] = x.get("currency_code", "EGP").fillna("EGP").astype(str)
    x["as_of_datetime"] = pd.to_datetime(x.get("as_of_datetime"), errors="coerce")
    return x


def latest_date(df: pd.DataFrame, column: str) -> Optional[pd.Timestamp]:
    if df.empty or column not in df.columns:
        return None
    values = pd.to_datetime(df[column], errors="coerce").dropna()
    return values.max() if not values.empty else None


def select_latest_positions(df: pd.DataFrame, as_of=None) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    x = df.copy()
    x["as_of_datetime"] = pd.to_datetime(x.get("as_of_datetime"), errors="coerce")
    valid = x.dropna(subset=["as_of_datetime"])
    if valid.empty:
        return normalize_positions(x)
    target = pd.to_datetime(as_of) if as_of is not None else valid["as_of_datetime"].max()
    candidates = valid[valid["as_of_datetime"] <= target]
    if candidates.empty:
        candidates = valid
    selected_date = candidates["as_of_datetime"].max()
    return normalize_positions(candidates[candidates["as_of_datetime"] == selected_date].copy())


def build_position_baseline(positions: pd.DataFrame, simulation_date=None, horizon_days=365) -> Dict[str, float]:
    """Build the ALM baseline from Positions ONLY.

    HARD DATA-DOMAIN BOUNDARY
    -------------------------
    Financial Statements are intentionally outside this 7-table ALM MVP.

    Interest is calculated consistently over the selected simulation horizon:
        Interest = Balance × Decimal Rate × Horizon Days / 365
    """
    q = normalize_positions(positions)

    if q.empty:
        return {
            "Position NII": 0.0,
            "Position Interest Income": 0.0,
            "Position Interest Expense": 0.0,
            "Position Loan Interest": 0.0,
            "Position Investment Interest": 0.0,
            "Position Deposit Interest": 0.0,
            "Position Funding Interest": 0.0,
            "Position Loans": 0.0,
            "Position Deposits": 0.0,
            "Position Funding": 0.0,
            "Position Investments": 0.0,
            "Position NIM %": 0.0,
            "Position Cost of Funds %": 0.0,
            "Position Loan Deposit %": 0.0,
            "Position Repricing Gap": 0.0,
            "Position As Of": None,
            "Position Horizon Days": int(horizon_days),
        }

    sim = (
        pd.to_datetime(simulation_date)
        if simulation_date is not None
        else q["as_of_datetime"].max()
    )

    horizon_factor = max(float(horizon_days), 0.0) / 365.0

    q["Repricing Fraction"] = q.apply(
        lambda r: repricing_fraction(r, sim, int(horizon_days)), axis=1
    )
    q["Eligible"] = q["Repricing Fraction"].fillna(0).gt(0).astype(bool)

    # Annualized interest is retained for transparency.
    q["Annual Interest"] = q["Model Balance"] * q["Model Rate"]

    # All baseline interest KPIs use the SAME horizon as scenario results.
    q["Interest"] = q["Annual Interest"] * horizon_factor

    cats = q["Position Category"].astype("string").str.lower()
    loan = cats.eq("loan")
    deposit = cats.eq("deposit")
    funding_mask = cats.eq("funding")
    investment = cats.eq("investment")

    loan_interest = float(q.loc[loan, "Interest"].sum())
    investment_interest = float(q.loc[investment, "Interest"].sum())
    deposit_interest = float(q.loc[deposit, "Interest"].sum())
    funding_interest = float(q.loc[funding_mask, "Interest"].sum())

    loans = float(q.loc[loan, "Model Balance"].sum())
    deposits = float(q.loc[deposit, "Model Balance"].sum())
    funding_balance = float(q.loc[funding_mask, "Model Balance"].sum())
    investments = float(q.loc[investment, "Model Balance"].sum())

    income = loan_interest + investment_interest
    expense = deposit_interest + funding_interest
    nii = income - expense

    earning_assets = loans + investments
    funding_base = deposits + funding_balance

    # Explicit boolean masks: never mix a pandas boolean Series with a
    # scalar/numeric value. Each mask remains a boolean Series.
    repricing_assets_mask = (loan | investment) & q["Eligible"]
    repricing_liabilities_mask = (deposit | funding_mask) & q["Eligible"]

    repricing_assets = float(
        q.loc[repricing_assets_mask, "Model Balance"].sum()
    )
    repricing_liabs = float(
        q.loc[repricing_liabilities_mask, "Model Balance"].sum()
    )

    return {
        "Position NII": nii,
        "Position Interest Income": income,
        "Position Interest Expense": expense,
        "Position Loan Interest": loan_interest,
        "Position Investment Interest": investment_interest,
        "Position Deposit Interest": deposit_interest,
        "Position Funding Interest": funding_interest,
        "Position Loans": loans,
        "Position Deposits": deposits,
        "Position Funding": funding_balance,
        "Position Investments": investments,
        "Position NIM %": (nii / earning_assets * 100.0) if earning_assets else 0.0,
        "Position Cost of Funds %": (
            expense / funding_base * 100.0 if funding_base else 0.0
        ),
        "Position Loan Deposit %": (
            loans / deposits * 100.0 if deposits else 0.0
        ),
        "Position Repricing Gap": repricing_assets - repricing_liabs,
        "Position As Of": q["as_of_datetime"].max(),
        "Position Horizon Days": int(horizon_days),
    }


def build_cashflow_baseline(cashflows: pd.DataFrame) -> Dict[str, float]:
    """Liquidity metrics are calculated only from Cash_Flows."""
    if cashflows.empty:
        return {
            "CF Inflow": 0.0, "CF Outflow": 0.0, "CF Net Cashflow": 0.0,
            "CF HQLA": 0.0, "CF LCR Proxy %": np.nan, "CF As Of": None
        }

    cf = cashflows.copy()
    cf["total_amount"] = to_num(cf.get("total_amount", 0.0))
    direction = cf.get("inflow_outflow", "").astype(str).str.lower()
    inflow = float(cf.loc[direction.eq("inflow"), "total_amount"].sum())
    outflow = float(cf.loc[direction.eq("outflow"), "total_amount"].sum())

    hqla_raw = cf.get("hqla_flag", pd.Series(False, index=cf.index))
    hqla_mask = hqla_raw.astype(bool)
    hqla = float(cf.loc[hqla_mask, "total_amount"].sum())
    net_outflow = max(outflow - inflow, 0.0)
    lcr = hqla / net_outflow * 100.0 if net_outflow else np.nan

    return {
        "CF Inflow": inflow,
        "CF Outflow": outflow,
        "CF Net Cashflow": inflow - outflow,
        "CF HQLA": hqla,
        "CF LCR Proxy %": lcr,
        "CF As Of": latest_date(cf, "cashflow_date"),
    }


def build_model_baseline(positions: pd.DataFrame, cashflows: pd.DataFrame,
                         simulation_date=None, horizon_days=365) -> Dict[str, float]:
    """Combine only Position and Cash_Flow namespaces.

    The 7-table ALM baseline contains no Financial Statements domain.
    """
    pos_base = build_position_baseline(
        positions, simulation_date=simulation_date, horizon_days=horizon_days
    )
    cf_base = build_cashflow_baseline(cashflows)
    return {**pos_base, **cf_base, "Baseline Unit": MODEL_AMOUNT_UNIT}


def tenor_to_days(value, default=None):
    """Convert common tenor/frequency strings (1M, 3M, 6M, 1Y, 2Y, etc.) to days."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return default
    text = str(value).strip().upper()
    if not text:
        return default
    m = re.search(r"(\d+(?:\.\d+)?)\s*([DWMY])", text)
    if not m:
        return default
    n = float(m.group(1)); unit = m.group(2)
    factor = {"D":1.0, "W":7.0, "M":30.4375, "Y":365.0}[unit]
    return int(round(n * factor))


def normalize_market_yield(value):
    """Market yield may be stored as 18.5 or 0.185; normalize to decimal rate."""
    try:
        x = float(value)
    except Exception:
        return np.nan
    if not np.isfinite(x):
        return np.nan
    return x / 100.0 if abs(x) > 2.0 else x


def build_market_curve(market_data: pd.DataFrame, as_of=None) -> pd.DataFrame:
    """Build the latest interest-rate/yield curve from Market_Data."""
    if market_data is None or market_data.empty or "yield_rate" not in market_data.columns:
        return pd.DataFrame(columns=["tenor","tenor_days","base_rate"])
    md = market_data.copy()
    md["_date"] = pd.to_datetime(md.get("as_of_datetime"), errors="coerce")
    if as_of is not None and md["_date"].notna().any():
        target = pd.to_datetime(as_of)
        eligible = md[md["_date"] <= target]
        if not eligible.empty:
            md = eligible
    if "data_type" in md.columns:
        mask = md["data_type"].astype(str).str.lower().str.contains("interest|yield|rate", regex=True, na=False)
        md = md[mask]
    if md.empty:
        return pd.DataFrame(columns=["tenor","tenor_days","base_rate"])
    md["tenor_days"] = md.get("tenor", pd.Series(index=md.index)).map(tenor_to_days)
    md["base_rate"] = md["yield_rate"].map(normalize_market_yield)
    md = md.dropna(subset=["tenor_days","base_rate"]).copy()
    if md.empty:
        return pd.DataFrame(columns=["tenor","tenor_days","base_rate"])
    md = md.sort_values(["tenor_days","_date" if "_date" in md.columns else "tenor"]).drop_duplicates("tenor_days", keep="last")
    return md[[c for c in ["tenor","tenor_days","base_rate","instrument_code","instrument_name","as_of_datetime","source"] if c in md.columns]].reset_index(drop=True)


def interpolate_curve_rate(curve: pd.DataFrame, tenor_days: int) -> float:
    if curve is None or curve.empty:
        return np.nan
    x = pd.to_numeric(curve["tenor_days"], errors="coerce").to_numpy(dtype=float)
    y = pd.to_numeric(curve["base_rate"], errors="coerce").to_numpy(dtype=float)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    if len(x) == 0:
        return np.nan
    order = np.argsort(x); x, y = x[order], y[order]
    return float(np.interp(float(tenor_days), x, y))


def build_shocked_curve(curve: pd.DataFrame, shock_bps: float) -> pd.DataFrame:
    if curve is None or curve.empty:
        return pd.DataFrame(columns=["tenor","tenor_days","base_rate","shocked_rate","delta"])
    out = curve.copy()
    shock = float(shock_bps or 0.0) / 10000.0
    out["shocked_rate"] = out["base_rate"] + shock
    out["delta"] = shock
    return out


def position_reference_tenor_days(row, simulation_date):
    """Choose the market-curve tenor that best represents the position repricing horizon."""
    freq = tenor_to_days(row.get("repricing_frequency"), None)
    if freq:
        return freq
    reset = row.get("Model Repricing Date")
    sim = pd.to_datetime(simulation_date)
    if pd.notna(reset):
        days = max((pd.to_datetime(reset) - sim).days, 1)
        return days
    maturity = row.get("Model Maturity Date")
    if pd.notna(maturity):
        days = max((pd.to_datetime(maturity) - sim).days, 1)
        return min(days, 3650)
    return 365


def is_repricing_eligible(row) -> bool:
    rate_type = str(row.get("Model Rate Type", "")).strip().lower()
    if any(w in rate_type for w in ["fixed", "non-interest", "non interest", "zero interest"]):
        return False
    if any(w in rate_type for w in ["floating", "variable", "repric", "adjustable"]):
        return True
    return str(row.get("Position Category", "")).strip().lower() in {"loan","deposit","funding","investment"}


def build_repricing_events(row, simulation_date, horizon_days):
    """Create actual repricing dates; no user-entered repricing fraction."""
    sim = pd.to_datetime(simulation_date)
    end = sim + pd.Timedelta(days=max(int(horizon_days), 0))
    if not is_repricing_eligible(row) or horizon_days <= 0:
        return []
    reset = row.get("Model Repricing Date")
    if pd.isna(reset):
        reset = sim
    else:
        reset = pd.to_datetime(reset)
    freq_days = tenor_to_days(row.get("repricing_frequency"), None)
    maturity = row.get("Model Maturity Date")
    maturity = pd.to_datetime(maturity) if pd.notna(maturity) else None
    if maturity is not None:
        end = min(end, maturity)
    if end <= sim:
        return []
    if reset < sim:
        reset = sim
    events=[]
    current=reset
    max_events=120
    while current < end and len(events) < max_events:
        events.append(current)
        if not freq_days or freq_days <= 0:
            break
        current = current + pd.Timedelta(days=int(freq_days))
    return events


def dynamic_repricing_calculation(row, simulation_date, horizon_days, shocked_curve, pass_through_pct):
    """Calculate interest period-by-period around repricing events."""
    sim = pd.to_datetime(simulation_date)
    end = sim + pd.Timedelta(days=max(int(horizon_days),0))
    maturity = row.get("Model Maturity Date")
    if pd.notna(maturity):
        end = min(end, pd.to_datetime(maturity))
    if end <= sim:
        return {"interest_before":0.0,"interest_after":0.0,"events":[],"repricing_fraction":0.0,"scenario_rate":float(row.get("Before Rate",0.0)),"market_rate":np.nan,"market_delta":0.0}

    balance = float(row.get("Before Balance",0.0))
    base_rate = float(row.get("Before Rate",0.0))
    events = build_repricing_events(row, sim, horizon_days)
    tenor_days = position_reference_tenor_days(row, sim)
    market_base = interpolate_curve_rate(shocked_curve[["tenor_days","base_rate"]] if not shocked_curve.empty else pd.DataFrame(), tenor_days)
    market_shocked = interpolate_curve_rate(shocked_curve[["tenor_days","shocked_rate"]].rename(columns={"shocked_rate":"base_rate"}) if not shocked_curve.empty else pd.DataFrame(), tenor_days)
    if not np.isfinite(market_base): market_base = np.nan
    if not np.isfinite(market_shocked): market_shocked = np.nan
    market_delta = (market_shocked-market_base) if np.isfinite(market_base) and np.isfinite(market_shocked) else 0.0
    effective_delta = market_delta * float(pass_through_pct or 0.0) / 100.0

    interest_before = balance * base_rate * max((end-sim).days,0) / 365.0
    interest_after = 0.0
    cursor=sim
    applied_events=[]
    current_rate=base_rate
    for event in events:
        event=pd.to_datetime(event)
        if event <= cursor or event >= end:
            continue
        days=(event-cursor).days
        interest_after += balance * current_rate * days / 365.0
        current_rate = base_rate + effective_delta
        applied_events.append(event)
        cursor=event
    remaining=(end-cursor).days
    interest_after += balance * current_rate * max(remaining,0) / 365.0
    exposed_days=sum(max((min(pd.to_datetime(e),end)-sim).days,0) for e in applied_events)
    repricing_fraction=max(0.0,min(1.0, (end - min(applied_events) if applied_events else pd.Timedelta(days=0)).days / max((end-sim).days,1))) if applied_events else 0.0
    return {"interest_before":interest_before,"interest_after":interest_after,"events":applied_events,"repricing_fraction":repricing_fraction,"scenario_rate":current_rate,"market_rate":market_base,"market_shocked_rate":market_shocked,"market_delta":market_delta,"tenor_days":tenor_days}


def repricing_fraction(row: pd.Series, simulation_date: pd.Timestamp, horizon_days: int) -> float:
    """Backward-compatible derived metric: fraction of horizon after first repricing event."""
    events=build_repricing_events(row, simulation_date, horizon_days)
    if not events or horizon_days <= 0:
        return 0.0
    end=pd.to_datetime(simulation_date)+pd.Timedelta(days=int(horizon_days))
    return max(0.0,min(1.0,(end-pd.to_datetime(events[0])).days/max(int(horizon_days),1)))


def apply_scenario(
    baseline=None, products=None, positions=None,
    simulation_date=pd.Timestamp.today(), horizon_days=365,
    rate_change_pp=0.0, deposit_growth_pct=0.0, loan_growth_pct=0.0,
    liquidity_shift_pct=0.0, fee_income_growth_pct=0.0,
    cashflows=None, market_data=None,
    loan_rate_shock_pp=None, deposit_rate_shock_pp=None,
    funding_rate_shock_pp=None,
    loan_pass_through_pct=100.0, deposit_pass_through_pct=100.0,
    funding_pass_through_pct=100.0, investment_pass_through_pct=100.0, yield_curve_shock_bps=None, **kwargs,
):
    """Deterministic ALM engine with dynamic event-based repricing.

    Market_Data is an active calculation source:
      Market_Data yield curve -> shocked curve -> position reference tenor ->
      market delta -> pass-through -> effective rate after each repricing event.

    Repricing Fraction is derived from the actual event schedule and is never
    a user input and never the primary multiplier for the interest calculation.
    """
    baseline = baseline or {}
    q = normalize_positions(positions if positions is not None else pd.DataFrame())
    cashflows = cashflows if cashflows is not None else pd.DataFrame()
    market_data = market_data if market_data is not None else pd.DataFrame()
    shock_bps = float(yield_curve_shock_bps if yield_curve_shock_bps is not None else (rate_change_pp * 100.0))
    if loan_rate_shock_pp is None: loan_rate_shock_pp = rate_change_pp
    if deposit_rate_shock_pp is None: deposit_rate_shock_pp = rate_change_pp
    if funding_rate_shock_pp is None: funding_rate_shock_pp = rate_change_pp

    curve = build_market_curve(market_data, as_of=simulation_date)
    shocked_curve = build_shocked_curve(curve, shock_bps)

    if not q.empty:
        q["Before Balance"] = to_num(q["Model Balance"])
        q["Before Rate"] = to_num(q["Model Rate"])
        q["After Balance"] = q["Before Balance"]
        cats = q["Position Category"].astype("string").str.lower()
        q.loc[cats.eq("loan"), "After Balance"] *= 1 + loan_growth_pct/100.0
        q.loc[cats.eq("deposit"), "After Balance"] *= 1 + deposit_growth_pct/100.0
        q["Repricing Fraction"] = 0.0
        q["Eligible"] = False
        q["Applied Shock"] = 0.0
        q["Market Curve Rate"] = np.nan
        q["Market Shocked Curve Rate"] = np.nan
        q["Market Rate Change"] = 0.0
        q["Reference Tenor Days"] = np.nan
        q["Repricing Event Count"] = 0
        q["Repricing Events"] = ""
        q["After Rate"] = q["Before Rate"]
        q["Annual Interest Before"] = q["Before Balance"] * q["Before Rate"]
        q["Annual Interest After"] = q["Annual Interest Before"]
        q["Interest Before"] = 0.0
        q["Interest After"] = 0.0
        q["Annual Interest Change"] = 0.0
        q["Interest Change"] = 0.0
        q["Validation Status"] = "PENDING"

        for idx,row in q.iterrows():
            cat=str(row.get("Position Category","")).lower()
            if cat == "loan": pt=loan_pass_through_pct
            elif cat == "deposit": pt=deposit_pass_through_pct
            elif cat == "funding": pt=funding_pass_through_pct
            elif cat == "investment": pt=investment_pass_through_pct
            else: pt=0.0
            calc=dynamic_repricing_calculation(row, simulation_date, horizon_days, shocked_curve, pt)
            q.at[idx,"Repricing Fraction"]=calc["repricing_fraction"]
            q.at[idx,"Eligible"]=bool(is_repricing_eligible(row))
            q.at[idx,"Market Curve Rate"]=calc.get("market_rate",np.nan)
            q.at[idx,"Market Shocked Curve Rate"]=calc.get("market_shocked_rate",np.nan)
            q.at[idx,"Market Rate Change"]=calc.get("market_delta",0.0)
            q.at[idx,"Reference Tenor Days"]=calc.get("tenor_days",np.nan)
            q.at[idx,"Repricing Event Count"]=len(calc["events"])
            q.at[idx,"Repricing Events"]=", ".join(pd.to_datetime(calc["events"]).strftime("%Y-%m-%d"))
            q.at[idx,"Interest Before"]=calc["interest_before"]
            q.at[idx,"Interest After"]=calc["interest_after"]
            q.at[idx,"Interest Change"]=calc["interest_after"]-calc["interest_before"]
            q.at[idx,"Annual Interest Change"]=q.at[idx,"Interest Change"]*365.0/max(int(horizon_days),1)
            q.at[idx,"After Rate"]=calc["scenario_rate"]
            q.at[idx,"Applied Shock"]=calc["scenario_rate"]-row["Before Rate"]
            q.at[idx,"Annual Interest After"]=q.at[idx,"After Balance"]*q.at[idx,"After Rate"]
            q.at[idx,"Validation Status"]="PASS" if np.isfinite(q.at[idx,"Interest After"]) else "FAIL"
    else:
        q=pd.DataFrame()

    cats=q["Position Category"].str.lower() if not q.empty else pd.Series(dtype=str)
    loan_delta=float(q.loc[cats.eq("loan"),"Interest Change"].sum()) if not q.empty else 0.0
    deposit_delta=float(q.loc[cats.eq("deposit"),"Interest Change"].sum()) if not q.empty else 0.0
    funding_delta=float(q.loc[cats.eq("funding"),"Interest Change"].sum()) if not q.empty else 0.0
    investment_delta=float(q.loc[cats.eq("investment"),"Interest Change"].sum()) if not q.empty else 0.0

    base_nii=float(baseline.get("Position NII",0.0))
    position_nii_after=base_nii+loan_delta+investment_delta-deposit_delta-funding_delta
    loans_after=float(baseline.get("Position Loans",0.0))*(1+loan_growth_pct/100.0)
    deposits_after=float(baseline.get("Position Deposits",0.0))*(1+deposit_growth_pct/100.0)
    funding_after=float(baseline.get("Position Funding",0.0))
    investments_after=float(baseline.get("Position Investments",0.0))
    position_income_after=float(baseline.get("Position Interest Income",0.0))+loan_delta+investment_delta
    position_expense_after=float(baseline.get("Position Interest Expense",0.0))+deposit_delta+funding_delta
    earning_assets_after=loans_after+investments_after
    funding_base_after=deposits_after+funding_after
    position_nim_after=position_nii_after/earning_assets_after*100.0 if earning_assets_after else 0.0
    position_cof_after=position_expense_after/funding_base_after*100.0 if funding_base_after else 0.0
    loan_deposit_after=loans_after/deposits_after*100.0 if deposits_after else 0.0

    if not q.empty:
        asset=cats.isin(["loan","investment"]); liability=cats.isin(["deposit","funding"])
        repricing_asset_base=float(q.loc[asset & q["Eligible"],"Before Balance"].sum())
        repricing_liability_base=float(q.loc[liability & q["Eligible"],"Before Balance"].sum())
        repricing_asset_after=float(q.loc[asset & q["Eligible"],"After Balance"].sum())
        repricing_liability_after=float(q.loc[liability & q["Eligible"],"After Balance"].sum())
    else:
        repricing_asset_base=repricing_liability_base=repricing_asset_after=repricing_liability_after=0.0
    repricing_gap_base=repricing_asset_base-repricing_liability_base
    repricing_gap_after=repricing_asset_after-repricing_liability_after

    cf_base=build_cashflow_baseline(cashflows)
    cf_inflow=float(cf_base["CF Inflow"])*(1+liquidity_shift_pct/100.0)
    cf_outflow=float(cf_base["CF Outflow"])*(1-liquidity_shift_pct/100.0)
    cf_net=cf_inflow-cf_outflow
    cf_hqla=float(cf_base["CF HQLA"])*(1+liquidity_shift_pct/100.0)
    net_outflow=max(cf_outflow-cf_inflow,0.0)
    lcr_after=cf_hqla/net_outflow*100.0 if net_outflow else np.nan

    curve_avg=float(curve["base_rate"].mean()) if not curve.empty else np.nan
    shocked_avg=float(shocked_curve["shocked_rate"].mean()) if not shocked_curve.empty else np.nan
    return {
        "Position NII":position_nii_after,"Position Interest Income":position_income_after,"Position Interest Expense":position_expense_after,
        "Position Loans":loans_after,"Position Deposits":deposits_after,"Position Funding":funding_after,"Position Investments":investments_after,
        "Position NIM %":position_nim_after,"Position Cost of Funds %":position_cof_after,"Position Loan Deposit %":loan_deposit_after,
        "Position Repricing Gap":repricing_gap_after,"Position Repricing Gap Base":repricing_gap_base,"Position Repricing Gap After":repricing_gap_after,
        "CF Inflow":cf_inflow,"CF Outflow":cf_outflow,"CF Net Cashflow":cf_net,"CF HQLA":cf_hqla,"CF LCR Proxy %":lcr_after,
        "CF LCR Proxy Base %":cf_base.get("CF LCR Proxy %",np.nan),"Liquidity":cf_net,"Liquidity Base":cf_base.get("CF Net Cashflow",0.0),
        "Curve Average Rate":curve_avg,"Shocked Curve Average Rate":shocked_avg,"Curve Rates Used":float(len(curve)),
        "Yield Curve Shock (bps)":shock_bps,"Repricing Eligible Positions":float(q["Eligible"].sum()) if not q.empty else 0.0,
        "Repricing Events Total":float(q["Repricing Event Count"].sum()) if not q.empty else 0.0,
        "Loan Interest Change":loan_delta,"Deposit Interest Change":deposit_delta,"Funding Interest Change":funding_delta,"Investment Interest Change":investment_delta,
        "Rate Shock (pp)":float(rate_change_pp),"Loan Rate Shock (pp)":float(loan_rate_shock_pp),"Deposit Rate Shock (pp)":float(deposit_rate_shock_pp),"Funding Rate Shock (pp)":float(funding_rate_shock_pp),
        "Loan Growth (%)":float(loan_growth_pct),"Deposit Growth (%)":float(deposit_growth_pct),"Liquidity Shift (%)":float(liquidity_shift_pct),"Model Amount Unit":MODEL_AMOUNT_UNIT,
    }, products.copy() if products is not None else pd.DataFrame(), q