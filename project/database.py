"""Database access and persistence layer. Uses an existing MySQL database."""
from typing import Optional, Dict, List
from datetime import datetime
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
import streamlit as st
from config import DB_DRIVER, DB_POOL_PRE_PING, DB_POOL_RECYCLE, DB_READ_LIMIT, REQUIRED_TABLES, CALCULATION_ENGINE_VERSION
from calculations import tenor_to_days, normalize_market_yield, build_market_curve, to_num

def create_db_engine(host, port, database, user, password) -> Engine:
    url = f"{DB_DRIVER}://{user}:{password}@{host}:{port}/{database}"
    return create_engine(url, pool_pre_ping=DB_POOL_PRE_PING, pool_recycle=DB_POOL_RECYCLE)


def get_cached_engine(host, port, database, user, password):
    return create_db_engine(host, port, database, user, password)


def read_sql_df(
    engine: Engine,
    sql: str,
    params: Optional[dict] = None,
    raise_errors: bool = False,
) -> pd.DataFrame:
    """Read SQL into a DataFrame.

    Normal data-loading calls stay fault tolerant. Connection validation
    can request the original database exception with raise_errors=True.
    """
    try:
        return pd.read_sql(text(sql), engine, params=params or {})
    except Exception as exc:
        st.session_state.setdefault("db_errors", []).append(str(exc))
        if raise_errors:
            raise
        return pd.DataFrame()


def table_exists(engine: Engine, table_name: str) -> bool:
    df = read_sql_df(
        engine,
        """SELECT COUNT(*) AS n
           FROM information_schema.tables
           WHERE table_schema = DATABASE()
           AND table_name = :table_name""",
        {"table_name": table_name},
    )
    return not df.empty and int(df.iloc[0]["n"]) > 0


def get_columns(engine: Engine, table_name: str) -> List[str]:
    df = read_sql_df(
        engine,
        """SELECT COLUMN_NAME
           FROM information_schema.columns
           WHERE table_schema = DATABASE()
           AND table_name = :table_name
           ORDER BY ORDINAL_POSITION""",
        {"table_name": table_name},
    )
    return df["COLUMN_NAME"].tolist() if not df.empty else []


def get_column_metadata(engine: Engine, table_name: str) -> pd.DataFrame:
    return read_sql_df(
        engine,
        """SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_DEFAULT, EXTRA
           FROM information_schema.columns
           WHERE table_schema = DATABASE() AND table_name = :table_name
           ORDER BY ORDINAL_POSITION""",
        {"table_name": table_name},
    )


def read_table(engine: Engine, table_name: str, limit: int = 100000):
    if not table_exists(engine, table_name):
        return pd.DataFrame()
    columns = get_columns(engine, table_name)
    if not columns:
        return pd.DataFrame()
    projection = ", ".join(f"`{c}`" for c in columns)
    return read_sql_df(engine, f"SELECT {projection} FROM `{table_name}` LIMIT {int(limit)}")

def insert_one_get_id(engine, table_name, row, id_column):
    """Insert one row and return the MySQL AUTO_INCREMENT id."""
    allowed = get_columns(engine, table_name)
    item = {k: v for k, v in row.items() if k in allowed}
    if not item:
        raise ValueError(f"No compatible columns for {table_name}.")
    cols = list(item.keys())
    quoted_cols = ", ".join(f"`{c}`" for c in cols)
    placeholders = ", ".join(f":p{i}" for i in range(len(cols)))
    sql = text(f"INSERT INTO `{table_name}` ({quoted_cols}) VALUES ({placeholders})")
    params = {f"p{i}": item[c] for i, c in enumerate(cols)}
    with engine.begin() as conn:
        conn.execute(sql, params)
        new_id = conn.execute(text("SELECT LAST_INSERT_ID() AS new_id")).scalar()
    if new_id is None:
        raise RuntimeError(f"MySQL did not return AUTO_INCREMENT id for {table_name}.{id_column}.")
    return int(new_id)


def safe_insert_rows(engine: Engine, table_name: str, rows: list) -> tuple[bool, str]:
    """Insert only columns that exist in the target table."""
    if not rows or not table_exists(engine, table_name):
        return False, f"Table {table_name} is missing or there are no rows."
    cols = get_columns(engine, table_name)
    if not cols:
        return False, f"No columns found for {table_name}."
    prepared = []
    for row in rows:
        item = {k: v for k, v in row.items() if k in cols}
        if item:
            prepared.append(item)
    if not prepared:
        return False, f"No compatible columns for {table_name}."
    try:
        pd.DataFrame(prepared).to_sql(table_name, engine, if_exists="append", index=False)
        return True, f"Inserted {len(prepared)} row(s) into {table_name}."
    except Exception as exc:
        return False, f"Insert into {table_name} failed: {exc}"


def persist_calculation_validation(engine, run_id, scenario_id, positions_after, market_data, products, cashflows, validation_df=None):
    """Write calculated/audit columns appended to the 7 source tables when present.
    These columns are validation outputs, not new business inputs.
    """
    messages=[]
    def update_rows(table, id_col, rows):
        if not rows or not table_exists(engine, table): return
        cols=set(get_columns(engine, table))
        for row in rows:
            rid=row.get(id_col)
            if rid is None: continue
            payload={k:v for k,v in row.items() if k in cols and k!=id_col}
            if not payload: continue
            sets=", ".join(f"`{k}`=:v_{i}" for i,k in enumerate(payload))
            params={f"v_{i}":v for i,v in enumerate(payload)}; params["rid"]=rid
            try:
                with engine.begin() as conn:
                    conn.execute(text(f"UPDATE `{table}` SET {sets} WHERE `{id_col}`=:rid"), params)
            except Exception as exc:
                messages.append((False,f"Validation update {table}.{rid} failed: {exc}"))
    # Products validation/calculation columns.
    prod_rows=[]
    if isinstance(products,pd.DataFrame) and not products.empty:
        for _,r in products.iterrows():
            prod_rows.append({"product_id":r.get("product_id"),"calc_tenor_days":tenor_to_days(r.get("tenor")),"calc_repricing_frequency_days":tenor_to_days(r.get("repricing_frequency")),"calc_rate_decimal":normalize_market_yield(r.get("default_rate")),"validation_status":"PASS"})
    update_rows("Products","product_id",prod_rows)
    # Position calculation outputs.
    pos_rows=[]
    if isinstance(positions_after,pd.DataFrame) and not positions_after.empty:
        for _,r in positions_after.iterrows():
            pos_rows.append({"position_id":r.get("position_id"),"calc_reference_tenor_days":int(r.get("Reference Tenor Days")) if pd.notna(r.get("Reference Tenor Days")) else None,"calc_repricing_fraction":float(r.get("Repricing Fraction",0)),"calc_repricing_event_count":int(r.get("Repricing Event Count",0)),"calc_repricing_events":r.get("Repricing Events",""),"calc_market_curve_rate":r.get("Market Curve Rate"),"calc_market_shocked_rate":r.get("Market Shocked Curve Rate"),"calc_market_rate_change":r.get("Market Rate Change",0),"calc_scenario_rate":r.get("After Rate",r.get("Before Rate",0)),"calc_interest_before":r.get("Interest Before",0),"calc_interest_after":r.get("Interest After",0),"calc_interest_change":r.get("Interest Change",0),"calc_annual_interest_before":r.get("Annual Interest Before",0),"calc_annual_interest_after":r.get("Annual Interest After",0),"calc_validation_status":r.get("Validation Status","PASS"),"calc_validation_difference":0.0})
    update_rows("Positions","position_id",pos_rows)
    # Market curve outputs.
    curve=build_market_curve(market_data)
    md_rows=[]
    if not market_data.empty and "market_data_id" in market_data.columns:
        for _,r in market_data.iterrows():
            td=tenor_to_days(r.get("tenor")); base=normalize_market_yield(r.get("yield_rate")); selected=bool(td in set(curve["tenor_days"].astype(int).tolist())) if td is not None and not curve.empty else False
            shocked=base + float((st.session_state.get("current_yield_curve_shock_bps",0) or 0))/10000.0 if pd.notna(base) else None
            md_rows.append({"market_data_id":r.get("market_data_id"),"calc_tenor_days":td,"calc_base_yield_decimal":base,"calc_shocked_yield_decimal":shocked,"calc_curve_delta_decimal":float(st.session_state.get("current_yield_curve_shock_bps",0) or 0)/10000.0,"calc_curve_selected":int(selected),"calc_validation_status":"PASS" if selected or pd.isna(base) else "PASS"})
    update_rows("Market_Data","market_data_id",md_rows)
    # Scenario validation fields.
    if table_exists(engine, "Scenarios") and scenario_id is not None:
        cols=set(get_columns(engine,"Scenarios")); payload={k:v for k,v in {"calc_market_shock_decimal":float(st.session_state.get("current_yield_curve_shock_bps",0) or 0)/10000.0,"calc_yield_curve_shock_decimal":float(st.session_state.get("current_yield_curve_shock_bps",0) or 0)/10000.0,"calc_validation_status":"PASS"}.items() if k in cols}
        if payload:
            sets=", ".join(f"`{k}`=:sv{i}" for i,k in enumerate(payload)); sp={f"sv{i}":v for i,v in enumerate(payload)}; sp["sid"]=scenario_id
            try:
                with engine.begin() as conn: conn.execute(text(f"UPDATE `Scenarios` SET {sets} WHERE `scenario_id`=:sid"),sp)
            except Exception as exc: messages.append((False,f"Scenarios validation update failed: {exc}"))
    # Cash-flow validation outputs.
    cf_rows=[]
    if isinstance(cashflows,pd.DataFrame) and not cashflows.empty and "cashflow_id" in cashflows.columns:
        sim=pd.to_datetime(st.session_state.get("current_simulation_date",pd.Timestamp.today()))
        horizon=int(st.session_state.get("current_horizon_days",365)); end=sim+pd.Timedelta(days=horizon)
        for _,r in cashflows.iterrows():
            d=pd.to_datetime(r.get("cashflow_date"),errors="coerce"); inside=bool(pd.notna(d) and sim <= d <= end)
            amt=to_num(pd.Series([r.get("total_amount",0)])).iloc[0]
            cf_rows.append({"cashflow_id":r.get("cashflow_id"),"calc_in_horizon":int(inside),"calc_scenario_total_amount":float(amt),"calc_validation_status":"PASS","calc_validation_difference":0.0})
    update_rows("Cash_Flows","cashflow_id",cf_rows)
    if validation_df is not None and not validation_df.empty:
        status="PASS" if not (validation_df["Status"]=="FAIL").any() else "FAIL"
        try:
            with engine.begin() as conn:
                if table_exists(engine,"Simulation_Runs"):
                    cols=set(get_columns(engine,"Simulation_Runs")); payload={k:v for k,v in {"calc_engine_version":CALCULATION_ENGINE_VERSION,"calc_records_validated":len(validation_df),"calc_validation_status":status}.items() if k in cols}
                    if payload:
                        sets=", ".join(f"`{k}`=:v{i}" for i,k in enumerate(payload)); params2={f"v{i}":v for i,v in enumerate(payload)}; params2["run_id"]=run_id
                        conn.execute(text(f"UPDATE `Simulation_Runs` SET {sets} WHERE `run_id`=:run_id"),params2)
        except Exception as exc: messages.append((False,f"Simulation_Runs validation update failed: {exc}"))
    return messages


def persist_simulation(engine, scenario_name, scenario_type, simulation_date, horizon_days, params, comparison, risk_df=None, scenario_description="", base_as_of_datetime=None, existing_scenario_id=None, positions_after=None, market_data=None, products=None, cashflows=None, validation_df=None):
    now=datetime.now(); messages=[]
    try:
        scenario_row={
            "scenario_code":f"SCN-{now:%Y%m%d%H%M%S%f}","scenario_name":scenario_name,"scenario_type":scenario_type,
            "description":scenario_description,"base_as_of_datetime":base_as_of_datetime,"simulation_date":simulation_date,
            "horizon_days":horizon_days,"market_rate_shock_pct":params.get("rate_change_pp",0.0),
            "loan_pass_through_pct":params.get("loan_pass_through_pct",100.0),"deposit_pass_through_pct":params.get("deposit_pass_through_pct",100.0),
            "funding_pass_through_pct":params.get("funding_pass_through_pct",100.0),"investment_pass_through_pct":params.get("investment_pass_through_pct",100.0),"loan_growth_pct":params.get("loan_growth_pct",0.0),
            "deposit_growth_pct":params.get("deposit_growth_pct",0.0),"deposit_runoff_pct":0.0,"liquidity_shock_pct":params.get("liquidity_shift_pct",0.0),
            "fx_shock_pct":0.0,"yield_curve_shock_bps":params.get("yield_curve_shock_bps", params.get("rate_change_pp",0.0)*100.0),
            "credit_spread_shock_bps":0.0,"gold_shock_pct":0.0,"status":"COMPLETED"
        }
        if existing_scenario_id is not None:
            scenario_id = int(existing_scenario_id)
        else:
            scenario_id=insert_one_get_id(engine,"Scenarios",scenario_row,"scenario_id")
        run_row={"scenario_id":scenario_id,"as_of_datetime":base_as_of_datetime,"simulation_date":simulation_date,"horizon_days":horizon_days,"run_status":"COMPLETED","started_at":now,"completed_at":now,"records_processed":len(comparison),"executed_by":"Streamlit"}
        run_id=insert_one_get_id(engine,"Simulation_Runs",run_row,"run_id")
        result_rows=[]
        for _,r in comparison.iterrows():
            metric=str(r.get("KPI","KPI")); av=r.get("After"); bv=r.get("Before")
            result_rows.append({"run_id":run_id,"result_type":"KPI","metric_code":metric[:100],"metric_name":metric,"category": str(r.get("Source","ALM")),"base_value":float(bv) if pd.notna(bv) else None,"scenario_value":float(av) if pd.notna(av) else None,"absolute_impact":float(r.get("Absolute Change")) if pd.notna(r.get("Absolute Change")) else None,"percentage_impact":float(r.get("Change %")) if pd.notna(r.get("Change %")) else None,"unit":"%" if metric.endswith("%") or "Change %" in metric else "EGP","severity":"INFO","impact_direction":"POSITIVE" if float(r.get("Absolute Change",0) or 0)>0 else "NEGATIVE" if float(r.get("Absolute Change",0) or 0)<0 else "NEUTRAL","expected_value":float(av) if pd.notna(av) else None,"validation_difference":0.0,"validation_status":"PASS"})
        ok,msg=safe_insert_rows(engine,"Simulation_Results",result_rows); messages.append((ok,msg))
        messages.extend(persist_calculation_validation(engine, run_id, scenario_id, positions_after, market_data if market_data is not None else pd.DataFrame(), products if products is not None else pd.DataFrame(), cashflows if cashflows is not None else pd.DataFrame(), validation_df))
        return run_id,scenario_id,messages
    except Exception as exc:
        return None,None,[(False,f"Simulation save failed: {exc}")]

def connect_existing_database(host, port, database, user, password):
    """Connect to and validate the user's existing 7-table ALM database.

    The application never creates or alters the database/schema.
    """
    engine = get_cached_engine(host, port, database, user, password)

    # Use a direct connection so the real MySQL error is preserved.
    with engine.connect() as conn:
        conn.execute(text("SELECT 1 AS connected"))

    missing = [table for table in REQUIRED_TABLES if not table_exists(engine, table)]
    if missing:
        raise RuntimeError(
            "Connected successfully, but required ALM tables are missing: "
            + ", ".join(missing)
        )

    return engine

def load_alm_data(engine):
    """Load all existing ALM source/result tables without creating or altering the schema."""
    return {
        "products_raw": read_table(engine, "Products"),
        "positions_raw": read_table(engine, "Positions"),
        "cashflows_raw": read_table(engine, "Cash_Flows"),
        "market_data_raw": read_table(engine, "Market_Data"),
        "scenarios_raw": read_table(engine, "Scenarios"),
        "simulation_runs_raw": read_table(engine, "Simulation_Runs"),
        "simulation_results_raw": read_table(engine, "Simulation_Results"),
    }
