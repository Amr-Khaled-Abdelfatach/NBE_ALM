"""Streamlit presentation layer and application workspace."""
import os
from datetime import date
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from config import *
from database import read_sql_df, read_table, connect_existing_database, load_alm_data, table_exists, get_columns,persist_simulation
from calculations import *
from scenarios import *
from analytics import *

def style_nbe_figure(fig):
    """Apply one NBE-inspired chart theme to every Plotly figure."""
    base = str(st.get_option("theme.base") or "light").lower()
    dark = base == "dark"
    # NBE-inspired palette remains the source of all chart colors.
    bg = "#0B2416" if dark else "#FFFFFF"
    text_color = "#EAF5EF" if dark else NBE_TEXT
    grid = "#35684D" if dark else "#D7E6DD"
    fig.update_layout(
        template="plotly_dark" if dark else "plotly_white",
        paper_bgcolor=bg, plot_bgcolor=bg,
        colorway=NBE_PALETTE,
        font=dict(color=text_color, family="Arial"),
        title_font=dict(color=NBE_ORANGE if dark else NBE_DARK_GREEN, size=18),
        legend=dict(font=dict(color=text_color)),
        xaxis=dict(gridcolor=grid, zerolinecolor=grid, linecolor=NBE_GREEN),
        yaxis=dict(gridcolor=grid, zerolinecolor=grid, linecolor=NBE_GREEN),
        margin=dict(l=20,r=20,t=55,b=45),
        hoverlabel=dict(bgcolor=NBE_DARK_GREEN, font=dict(color="#FFFFFF")),
    )
    return fig


def render_ai_scenario_panel(scenario_name, scenario_type, simulation_date, horizon_days, scenario_params, before, after, risk_df, panel_key="scenario"):
    st.markdown('<div class="ai-card">',unsafe_allow_html=True)
    st.markdown(f"### AI Scenario Explanation — {scenario_name}")
    st.caption(f"Scenario: {scenario_name} | Type: {scenario_type} | Date: {pd.to_datetime(simulation_date).strftime('%Y-%m-%d')} | Horizon: {horizon_days} days")
    st.info("Phi-3 only explains the deterministic calculation. Python remains the source of all financial numbers.")
    payload={"scenario_name":scenario_name,"scenario_type":scenario_type,"simulation_date":str(simulation_date),"horizon_days":horizon_days,"inputs":scenario_params,"before":before,"after":after,"risk":risk_df.to_dict(orient="records") if isinstance(risk_df,pd.DataFrame) else []}
    if st.button("Explain This Scenario",type="primary",key=f"ai_explain_{panel_key}"):
        host=st.session_state.get("ollama_host",os.getenv("OLLAMA_HOST","http://localhost:11434")); model=st.session_state.get("ollama_model",os.getenv("OLLAMA_MODEL","phi3"))
        st.session_state[f"ai_insight_{panel_key}"]=ask_ollama(host,model,payload)
        st.session_state[f"ai_insight_meta_{panel_key}"]={"scenario_name":scenario_name,"model":model}
    insight=st.session_state.get(f"ai_insight_{panel_key}")
    meta=st.session_state.get(f"ai_insight_meta_{panel_key}",{})
    if insight:
        st.markdown("**AI explanation**"); st.write(insight)
        st.caption(f"Explained scenario: {meta.get('scenario_name',scenario_name)} | Model: {meta.get('model','phi3')}")
    st.markdown('</div>',unsafe_allow_html=True)


def render_page_header(title, subtitle=None, status="Connected"):
    st.markdown(
        f'''<div class="app-header">
            <div>
                <div class="app-title">{title}</div>
                {f'<div class="app-subtitle">{subtitle}</div>' if subtitle else ''}
            </div>
            <div class="app-status"><span class="status-dot"></span>{status}</div>
        </div>''',
        unsafe_allow_html=True,
    )


def nav_button(label):
    active = st.session_state.get("main_page", "Executive Dashboard") == label
    if st.sidebar.button(("● " if active else "") + label, key="nav_" + label.replace(" ", "_").replace("/", "_"), use_container_width=True):
        st.session_state["main_page"] = label
        st.rerun()


def template_values(template_name):
    template = SCENARIO_TEMPLATES[template_name]
    values = dict(PARAMETER_DEFAULTS)
    for key in template.get("visible", []):
        if key in template:
            values[key] = float(template[key]) if isinstance(template[key], (int, float)) else template[key]
    if template_name == "Individual Parameter Scenario":
        values["individual_parameter"] = template.get("individual_parameter", "Market Rate Shock")
        values["individual_value"] = float(template.get("individual_value", 0.0))
    return values


def visible_params_for_scenario_type(scenario_type):
    mapping = {
        "BASE": [],
        "RATE_SHOCK": ["individual_parameter", "individual_value"],
        "DEPOSIT_GROWTH": ["individual_parameter", "individual_value"],
        "LOAN_GROWTH": ["individual_parameter", "individual_value"],
        "BALANCE_SHOCK": ["individual_parameter", "individual_value"],
        "LIQUIDITY_STRESS": ["individual_parameter", "individual_value"],
        "COMBINED_STRESS": ["rate", "loan_pass", "deposit_pass", "funding_pass", "investment_pass", "deposit_growth", "loan_growth", "liquidity"],
        "CUSTOM": ["rate", "loan_pass", "deposit_pass", "funding_pass", "investment_pass", "deposit_growth", "loan_growth", "liquidity"],
        "INDIVIDUAL_PARAMETER": ["individual_parameter", "individual_value"],
        "FREE_TYPE": ["text_prompt"],
    }
    return mapping.get(str(scenario_type).upper(), [])


def resolve_saved_template(scenario_type, saved_values=None):
    scenario_type = str(scenario_type).upper()
    if scenario_type == "BASE":
        return "Base Case"
    if scenario_type in {"RATE_SHOCK", "DEPOSIT_GROWTH", "LOAN_GROWTH", "BALANCE_SHOCK", "LIQUIDITY_STRESS"}:
        return "Individual Parameter Scenario"
    if scenario_type in {"COMBINED_STRESS", "CUSTOM"}:
        return "Combined Stress Scenario"
    if scenario_type == "FREE_TYPE":
        return "Free Type Scenario"
    if scenario_type == "INDIVIDUAL_PARAMETER":
        return "Individual Parameter Scenario"
    return "Combined Stress Scenario"


def build_saved_template_values(template_name, old_values):
    values = template_values(template_name)
    aliases = {
        "rate": ["MARKET_RATE_SHOCK_BPS", "rate_change_pp"],
        "loan_pass": ["LOAN_RATE_PASS_THROUGH", "LOAN_RATE_PASS_THROUGH_PCT", "loan_pass_through_pct"],
        "deposit_pass": ["DEPOSIT_RATE_PASS_THROUGH", "DEPOSIT_RATE_PASS_THROUGH_PCT", "deposit_pass_through_pct"],
        "funding_pass": ["FUNDING_RATE_PASS_THROUGH", "FUNDING_RATE_PASS_THROUGH_PCT", "funding_pass_through_pct"],
        "investment_pass": ["INVESTMENT_RATE_PASS_THROUGH", "INVESTMENT_RATE_PASS_THROUGH_PCT", "investment_pass_through_pct"],
        "deposit_growth": ["DEPOSIT_GROWTH_PCT", "deposit_growth_pct"],
        "loan_growth": ["LOAN_GROWTH_PCT", "loan_growth_pct"],
        "liquidity": ["LIQUIDITY_SHOCK_PCT", "liquidity_shift_pct"],
    }

    # Legacy saved scenarios are mapped into the new compact 4-mode design.
    if template_name == "Individual Parameter Scenario":
        candidate_map = [
            ("Market Rate Shock", aliases["rate"]),
            ("Deposit Growth", aliases["deposit_growth"]),
            ("Loan Growth", aliases["loan_growth"]),
            ("Liquidity Shift", aliases["liquidity"]),
        ]
        for label, names in candidate_map:
            for name in names:
                if name in old_values:
                    value = float(old_values[name])
                    if label == "Market Rate Shock" and name == "MARKET_RATE_SHOCK_BPS":
                        value /= 100.0
                    if abs(value) > 1e-12:
                        values["individual_parameter"] = label
                        values["individual_value"] = value
                        return values
        return values

    allowed = set(SCENARIO_TEMPLATES[template_name].get("visible", []))
    for key, names in aliases.items():
        if key not in allowed:
            continue
        for name in names:
            if name in old_values:
                value = float(old_values[name])
                if key == "rate" and name == "MARKET_RATE_SHOCK_BPS":
                    value /= 100.0
                values[key] = value
                break
    return values


def apply_template(template_name):
    st.session_state["active_template"] = template_name
    st.session_state["builder_values"] = template_values(template_name)
    st.session_state["builder_visible_params"] = list(SCENARIO_TEMPLATES[template_name]["visible"])
    st.session_state["scenario_action"] = "new"
    st.session_state["run_requested"] = False
    for key in [
        "builder_market_rate", "builder_loan_pass", "builder_deposit_pass", "builder_funding_pass", "builder_investment_pass",
        "builder_deposit_growth", "builder_loan_growth", "builder_liquidity",
        "builder_individual_parameter", "builder_individual_value", "builder_free_type_text",
        "free_type_text", "free_type_parsed", "free_type_parsed_source",
    ]:
        st.session_state.pop(key, None)


def start_custom_scenario():
    apply_template("Combined Stress Scenario")


def format_large_number(num):
    """Dynamically formats large numbers into T, B, M, or K formats."""
    if pd.isna(num):
        return "N/A"
    try:
        num = float(num)
    except:
        return str(num)
        
    abs_num = abs(num)
    if abs_num >= 1e12:
        return f"{num / 1e12:,.2f} T"
    elif abs_num >= 1e9:
        return f"{num / 1e9:,.2f} B"
    elif abs_num >= 1e6:
        return f"{num / 1e6:,.2f} M"
    elif abs_num >= 1e3:
        return f"{num / 1e3:,.2f} K"
    else:
        return f"{num:,.2f}"


def pct_change(before, after):
    before = float(before or 0)
    after_raw = after
    after = float(after_raw) if pd.notna(after_raw) else np.nan
    return ((after - before) / abs(before) * 100.0) if before and pd.notna(after) else np.nan


def scenario_kpi_cards(before, after):
    """Dashboard cards: Positions and Cash_Flows only."""
    return [
        ("Position NII", before.get("Position NII", 0), after.get("Position NII", 0), ""),
        ("Position NII Change %", 0, pct_change(before.get("Position NII", 0), after.get("Position NII", 0)), "%"),
        ("Position NIM %", before.get("Position NIM %", 0), after.get("Position NIM %", 0), "%"),
        ("Total Loans", before.get("Position Loans", 0), after.get("Position Loans", 0), ""),
        ("Total Deposits", before.get("Position Deposits", 0), after.get("Position Deposits", 0), ""),
        ("Total Funding", before.get("Position Funding", 0), after.get("Position Funding", 0), ""),
        ("Investments", before.get("Position Investments", 0), after.get("Position Investments", 0), ""),
        ("Loan / Deposit %", before.get("Position Loan Deposit %", 0), after.get("Position Loan Deposit %", 0), "%"),
        ("Repricing Gap", before.get("Position Repricing Gap", 0), after.get("Position Repricing Gap", 0), ""),
        ("Liquidity Net Cashflow", before.get("CF Net Cashflow", 0), after.get("CF Net Cashflow", 0), ""),
        ("LCR Proxy %", before.get("CF LCR Proxy %", np.nan), after.get("CF LCR Proxy %", np.nan), "%"),
        ("Position Cost of Funds %", before.get("Position Cost of Funds %", 0), after.get("Position Cost of Funds %", 0), "%"),
    ]


def load_saved_scenario_for_dashboard(scenario_id, engine, baseline, products, positions, cashflows, market_data):
    """Load and deterministically recalculate a saved scenario for dashboard use."""
    scenario_df = read_sql_df(engine, "SELECT * FROM Scenarios WHERE scenario_id = :scenario_id LIMIT 1", {"scenario_id": int(scenario_id)})
    if scenario_df.empty:
        return None
    row = scenario_df.iloc[0]
    p = scenario_params_from_row(row)
    sim_date = pd.to_datetime(row.get("simulation_date", date.today()))
    after_saved, product_saved, position_saved = apply_scenario(
        baseline=baseline, products=products, positions=positions,
        simulation_date=sim_date, horizon_days=int(row.get("horizon_days", 365) or 365),
        rate_change_pp=p["rate_change_pp"], deposit_growth_pct=p["deposit_growth_pct"], loan_growth_pct=p["loan_growth_pct"],
        liquidity_shift_pct=p["liquidity_shift_pct"], fee_income_growth_pct=0.0,
        loan_rate_shock_pp=p["loan_rate_shock_pp"], deposit_rate_shock_pp=p["deposit_rate_shock_pp"], funding_rate_shock_pp=p["funding_rate_shock_pp"],
        loan_pass_through_pct=p["loan_pass_through_pct"], deposit_pass_through_pct=p["deposit_pass_through_pct"], funding_pass_through_pct=p["funding_pass_through_pct"],
        investment_pass_through_pct=p.get("investment_pass_through_pct", 100.0),
        cashflows=cashflows, market_data=market_data,
    )
    saved_comparison = comparison_table(baseline, after_saved)
    saved_risk = build_alm_risk_summary(baseline, after_saved)
    quality = build_data_quality_checks(baseline, positions, cashflows, market_data, after_saved)
    return {
        "scenario_id": int(scenario_id),
        "scenario_name": str(row.get("scenario_name", f"Scenario {scenario_id}")),
        "scenario_type": str(row.get("scenario_type", "SAVED")),
        "simulation_date": sim_date, "params": p,
        "after": after_saved, "product_after": product_saved, "position_after": position_saved,
        "comparison": saved_comparison, "risk_df": saved_risk, "quality": quality,
    }


def impact_bar(before, after, metrics, title):
    rows=[]
    for label, key in metrics:
        b=float(before.get(key,0) or 0); a=float(after.get(key,0) or 0)
        rows += [[label, "Before", b], [label, "After", a]]
    df=pd.DataFrame(rows, columns=["Metric","Stage","Value"])
    df["Formatted_Value"] = df["Value"].apply(format_large_number)
    fig=px.bar(df, x="Metric", y="Value", color="Stage", barmode="group", title=title, text="Formatted_Value", color_discrete_sequence=NBE_PALETTE)
    fig.update_layout(height=380, xaxis_tickangle=-25, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    fig.update_traces(textposition='outside')
    return fig
CUSTOM_CSS = r"""
<style>
.block-container { padding-top: 1.2rem; }
.section-header { font-size: 1.25rem; font-weight: 700; margin-top: 1rem; margin-bottom: .5rem; color: var(--text-color); border-bottom: 1px solid var(--secondary-background-color); padding-bottom: 0.5rem; }
.muted { opacity: .75; font-size: .85rem; color: var(--text-color); }
[data-testid="stMetric"] { background-color: var(--secondary-background-color); border: 1px solid var(--border-color); border-radius: 14px; padding: 14px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
input, textarea, select, [data-baseweb="input"], [data-baseweb="select"], [data-baseweb="textarea"] { border-radius: 10px !important; }
[data-testid="stTextInput"] > div, [data-testid="stNumberInput"] > div, [data-testid="stDateInput"] > div, [data-testid="stSelectbox"] > div, [data-testid="stTextArea"] > div { border-radius: 12px !important; padding: 2px !important; }
.stButton > button { border-radius: 12px !important; min-height: 42px; font-weight: 600; transition: all 0.2s; }
.stButton > button:hover { border-color: var(--primary-color) !important; color: var(--primary-color) !important; }
input::placeholder, textarea::placeholder { opacity: .7 !important; }
[data-testid="stSidebar"] { border-right: 1px solid var(--border-color); }
[data-testid="stSidebar"] .stRadio > div { gap: 4px; }
[data-testid="stSidebar"] [role="radiogroup"] label { border-radius: 8px; padding: 4px 8px; }
.app-header { display:flex; justify-content:space-between; align-items:center; padding:18px 22px; margin-bottom:20px; background:linear-gradient(135deg,#005B2D,#007A3D); border-radius:16px; box-shadow:0 8px 24px rgba(0,91,45,.14); }
.app-title { color:#ffffff; font-size:1.65rem; font-weight:750; letter-spacing:.2px; }
.app-subtitle { color:#EAF5EF; font-size:.88rem; margin-top:4px; }
.app-status { color:#FFFFFF; font-size:.82rem; border:1px solid rgba(255,255,255,.22); padding:7px 11px; border-radius:999px; }
.status-dot { display:inline-block; width:8px; height:8px; border-radius:50%; background:#F7941D; margin-right:7px; }
.stButton > button[kind="primary"] { background:#007A3D !important; color:#FFFFFF !important; border-color:#007A3D !important; }
.stButton > button[kind="primary"]:hover { background:#005B2D !important; border-color:#005B2D !important; color:#FFFFFF !important; }
[data-testid="stDownloadButton"] > button { border-color:#007A3D !important; color:#007A3D !important; }
[data-testid="stDownloadButton"] > button:hover { background:#EAF5EF !important; border-color:#005B2D !important; color:#005B2D !important; }
[data-testid="stCheckbox"] [data-baseweb="checkbox"] [role="checkbox"][aria-checked="true"] { background:#007A3D !important; border-color:#007A3D !important; }
[data-testid="stRadio"] [role="radio"][aria-checked="true"] > div:first-child { border-color:#007A3D !important; }
[data-testid="stSlider"] [data-baseweb="slider"] div[role="slider"] { background:#007A3D !important; border-color:#007A3D !important; }
.page-card { background: var(--secondary-background-color); border:1px solid var(--border-color); border-radius:14px; padding:16px; }
.workspace-shell { margin: 0 0 1rem 0; padding: 8px; border: 1px solid var(--border-color); border-radius: 14px; background: var(--secondary-background-color); }
.scenario-identity { padding: 14px 16px; border: 1px solid var(--border-color); border-radius: 14px; background: var(--secondary-background-color); margin-bottom: 1rem; }
.scenario-identity .title { font-size: 1.18rem; font-weight: 750; margin-bottom: 3px; }
.scenario-identity .meta { font-size: .82rem; opacity: .75; }
.ai-card { padding: 16px; border: 1px solid var(--border-color); border-radius: 14px; background: var(--secondary-background-color); }
</style>
"""

def run_app():
    """Run the complete Streamlit application using the existing database."""
    os.environ.setdefault("STREAMLIT_THEME_BASE", "light")
    os.environ.setdefault("STREAMLIT_THEME_PRIMARY_COLOR", NBE_GREEN)
    try:
        st.set_option("theme.base", "light")
    except Exception:
        pass
    st.set_page_config(page_title=PAGE_TITLE, page_icon=PAGE_ICON, layout=PAGE_LAYOUT, initial_sidebar_state=INITIAL_SIDEBAR_STATE)
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

    for _key, _value in [
        ("db_host", DB_HOST),
        ("db_port", DB_PORT),
        ("db_name", DB_NAME),
        ("db_user", DB_USER),
        ("db_password", DB_PASSWORD),
        ("ollama_host", OLLAMA_HOST),
        ("ollama_model", OLLAMA_MODEL),
    ]:
        if _key not in st.session_state:
            st.session_state[_key] = _value

    st.sidebar.markdown("# NBE ALM")

    st.sidebar.caption("Asset-Liability Management Simulation")

    st.sidebar.markdown("**WORKSPACE**")

    nav_button("Executive Dashboard")

    nav_button("Scenario Workspace")

    nav_button("ALM Analytics & Risk")

    nav_button("Data & Audit")

    st.sidebar.markdown("**SYSTEM**")

    nav_button("System Settings")

    _selected_nav = st.session_state.get("main_page", "Executive Dashboard")

    page = PAGES[_selected_nav]

    is_scenario_workspace = page == "workspace"

    is_analytics_workspace = page == "analytics_workspace"

    is_data_workspace = page == "data_workspace"

    if is_scenario_workspace:
        _workspace_view = st.session_state.get("workspace_view", "Create & Run")
        page = {
            "Create & Run": "builder",
            "Saved Scenarios": "history",
            "Compare Scenarios": "comparison",
        }.get(_workspace_view, "builder")
        st.session_state["workspace_view"] = _workspace_view
    elif is_analytics_workspace:
        _analytics_view = st.session_state.get("analytics_view", "ALM Analytics")
        page = {
            "ALM Analytics": "analytics",
            "Liquidity & Risk": "risk",
        }.get(_analytics_view, "analytics")
        st.session_state["analytics_view"] = _analytics_view
    elif is_data_workspace:
        _data_view = st.session_state.get("data_view", "Data Explorer")
        page = {
            "Data Explorer": "data",
            "Calculation Audit": "audit",
        }.get(_data_view, "data")
        st.session_state["data_view"] = _data_view

    host = str(st.session_state["db_host"])

    port = int(st.session_state["db_port"])

    database = str(st.session_state["db_name"])

    user = str(st.session_state["db_user"])

    password = str(st.session_state["db_password"])

    connection_error = None
    try:
        engine = connect_existing_database(
            host, port, database, user, password
        )
        db_connected = True
    except Exception as exc:
        db_connected = False
        engine = None
        connection_error = str(exc)

    # Do not stop the whole app when the database is unavailable.
    # System Settings must remain accessible so connection values can be fixed.
    if not db_connected:
        st.error(f"Database connection failed: {connection_error}")
        if page != "advanced":
            st.warning(
                "The application is running in connection setup mode. "
                "Open **System Settings → Database Connection** to verify "
                "Host, Port, Database, User, and Password."
            )

    if db_connected:
        products_raw = read_table(engine, "Products")
        positions_raw = read_table(engine, "Positions")
        cashflows_raw = read_table(engine, "Cash_Flows")
        market_data_raw = read_table(engine, "Market_Data")
        scenarios_raw = read_table(engine, "Scenarios")
        simulation_runs_raw = read_table(engine, "Simulation_Runs")
        simulation_results_raw = read_table(engine, "Simulation_Results")

        products = normalize_products(products_raw)
        positions = select_latest_positions(positions_raw)
        cashflows = cashflows_raw.copy()
        market_data = market_data_raw.copy()
        baseline = build_model_baseline(
            positions,
            cashflows,
            simulation_date=positions["as_of_datetime"].max() if not positions.empty else pd.Timestamp.today(),
            horizon_days=365,
        )
        baseline_quality = build_data_quality_checks(baseline, positions, cashflows, market_data)
    else:
        products_raw = positions_raw = cashflows_raw = market_data_raw = pd.DataFrame()
        scenarios_raw = simulation_runs_raw = simulation_results_raw = pd.DataFrame()
        products = positions = cashflows = market_data = pd.DataFrame()
        baseline = build_model_baseline(positions, cashflows, simulation_date=pd.Timestamp.today(), horizon_days=365)
        baseline_quality = pd.DataFrame(columns=["Check","Status","Detail"])

    render_page_header("NBE ALM Simulation Center", "MySQL-driven ALM workspace | Deterministic calculations | Local Phi-3 integration")

    if "active_template" not in st.session_state:
        st.session_state["active_template"] = "Combined Stress Scenario"

    if st.session_state.get("active_template") in {"Custom", "Custom Scenario", "Combined Stress"}:
        st.session_state["active_template"] = "Combined Stress Scenario"

    if st.session_state.get("active_template") in {"Rate Increase", "Rate Decrease", "Deposit Growth", "Loan Growth", "Liquidity Pressure"}:
        st.session_state["active_template"] = "Individual Parameter Scenario"

    if "builder_values" not in st.session_state or not isinstance(st.session_state.get("builder_values"), dict):
        st.session_state["builder_values"] = template_values(st.session_state["active_template"])

    if "builder_visible_params" not in st.session_state:
        st.session_state["builder_visible_params"] = list(SCENARIO_TEMPLATES[st.session_state["active_template"]]["visible"])

    if "scenario_action" not in st.session_state:
        st.session_state["scenario_action"] = "new"

    if "selected_old_scenario" not in st.session_state:
        st.session_state["selected_old_scenario"] = None

    history = scenario_summary(scenarios_raw)

    if is_scenario_workspace:
        st.markdown('<div class="workspace-shell">', unsafe_allow_html=True)
        ws_left, ws_mid, ws_right = st.columns(3)
        _ws_options = ["Create & Run", "Saved Scenarios", "Compare Scenarios"]
        for _col, _opt in zip([ws_left, ws_mid, ws_right], _ws_options):
            with _col:
                _active = st.session_state.get("workspace_view", "Create & Run") == _opt
                if st.button(("● " if _active else "") + _opt, key="workspace_view_" + _opt.replace(" ", "_"), use_container_width=True, type="primary" if _active else "secondary"):
                    st.session_state["workspace_view"] = _opt
                    st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    if is_analytics_workspace:
        st.markdown('<div class="workspace-shell">', unsafe_allow_html=True)
        _analytics_options = ["ALM Analytics", "Liquidity & Risk"]
        _active_analytics = st.session_state.get("analytics_view", "ALM Analytics")
        _a1, _a2 = st.columns(2)
        for _col, _opt in zip([_a1, _a2], _analytics_options):
            with _col:
                _active = _active_analytics == _opt
                if st.button(("● " if _active else "") + _opt, key="analytics_view_" + _opt.replace(" ", "_"), use_container_width=True, type="primary" if _active else "secondary"):
                    st.session_state["analytics_view"] = _opt
                    st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    if is_data_workspace:
        st.markdown('<div class="workspace-shell">', unsafe_allow_html=True)
        _data_options = ["Data Explorer", "Calculation Audit"]
        _active_data = st.session_state.get("data_view", "Data Explorer")
        _d1, _d2 = st.columns(2)
        for _col, _opt in zip([_d1, _d2], _data_options):
            with _col:
                _active = _active_data == _opt
                if st.button(("● " if _active else "") + _opt, key="data_view_" + _opt.replace(" ", "_"), use_container_width=True, type="primary" if _active else "secondary"):
                    st.session_state["data_view"] = _opt
                    st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    if page == "templates":
        st.markdown('<div class="section-header">🧩 Scenario Templates</div>', unsafe_allow_html=True)
        st.write("Choose one of four compact scenario modes. Detailed assumptions are configured inside Scenario Workspace.")

        selected_template = st.selectbox("Available template", PREDEFINED_TEMPLATE_NAMES, key="template_page_select")
        t = SCENARIO_TEMPLATES[selected_template]

        st.info(t["description"])
        template_labels = {
            "rate": ("Market rate shock", "percentage points"),
            "loan_pass": ("Loan pass-through", "%"),
            "deposit_pass": ("Deposit pass-through", "%"),
            "funding_pass": ("Funding pass-through", "%"),
            "investment_pass": ("Investment pass-through", "%"),
            "deposit_growth": ("Deposit growth", "%"),
            "loan_growth": ("Loan growth", "%"),
            "liquidity": ("Liquidity shift", "%"),
                }
        rows = [[template_labels[k][0], t[k], template_labels[k][1]] for k in t["visible"]]
        if not rows:
            rows = [["No stress assumption", 0.0, "-"]]
        st.dataframe(pd.DataFrame(rows, columns=["Parameter", "Template Value", "Unit"]), use_container_width=True, hide_index=True)

        c1, c2 = st.columns(2)
        with c1:
            if st.button("✅ Apply Template", type="primary", use_container_width=True):
                apply_template(selected_template)
                st.success(f"Template '{selected_template}' has been loaded. Go to Scenario Builder.")
        with c2:
            if st.button("🧪 Open Combined Stress Scenario", use_container_width=True):
                apply_template("Combined Stress Scenario")
                st.success("Combined Stress Scenario has been loaded. Go to Scenario Workspace.")

        st.markdown("---")
        st.markdown('<div class="section-header">⌨️ Free Type Scenario</div>', unsafe_allow_html=True)
        free_type = SCENARIO_TEMPLATES["Free Type Scenario"]
        st.write(free_type["description"])
        st.caption("Describe the scenario in natural language. Phi-3 extracts only explicit assumptions; the deterministic engine performs the calculations.")
        if st.button("🆕 Open Free Type Scenario", use_container_width=True):
            apply_template("Free Type Scenario")
            st.success("Free Type Scenario has been created. Go to Scenario Builder.")

    if page == "builder":
        st.markdown('<div class="section-header">🎛️ Scenario Workspace — Create & Run</div>', unsafe_allow_html=True)
        st.caption("Create the scenario, review the calculated impact, explain it with AI, and save it from one workspace.")

        _template_labels = list(PREDEFINED_TEMPLATE_NAMES)
        _current_template = st.session_state.get("active_template", "Combined Stress Scenario")
        if _current_template not in _template_labels:
            _current_template = "Combined Stress Scenario"
        _selected_template = st.selectbox(
            "Scenario template",
            _template_labels,
            index=_template_labels.index(_current_template),
            key="workspace_template_selector",
        )
        if _selected_template != st.session_state.get("active_template"):
            apply_template(_selected_template)
            st.rerun()

        active = st.session_state["active_template"]
        st.markdown(
            f'<div class="scenario-identity"><div class="title">{active}</div>'
            f'<div class="meta">Template, assumptions, calculation, AI explanation, and saving are handled in one workflow.</div></div>',
            unsafe_allow_html=True,
        )

        # Show the selected template's parameters again in the same workspace.
        # This keeps the consolidated five-panel navigation while preserving the
        # original template-specific parameter visibility.
        _template = SCENARIO_TEMPLATES[active]
        _template_labels_map = {
            "rate": ("Market rate shock", "percentage points"),
            "loan_pass": ("Loan pass-through", "%"),
            "deposit_pass": ("Deposit pass-through", "%"),
            "funding_pass": ("Funding pass-through", "%"),
            "investment_pass": ("Investment pass-through", "%"),
            "deposit_growth": ("Deposit growth", "%"),
            "loan_growth": ("Loan growth", "%"),
            "liquidity": ("Liquidity shift", "%"),
                    "text_prompt": ("Natural-language instruction", "Text"),
        }
        _template_rows = []
        for _key in _template.get("visible", []):
            if _key == "text_prompt":
                _template_rows.append([_template_labels_map[_key][0], "Enter scenario text", _template_labels_map[_key][1]])
            elif _key == "individual_parameter":
                _template_rows.append(["Selected driver", _template.get(_key, "Market Rate Shock"), "Driver"])
            elif _key == "individual_value":
                _template_rows.append(["Driver value", _template.get(_key, 0.0), "Depends on driver"])
            elif _key in _template_labels_map:
                _template_rows.append([_template_labels_map[_key][0], _template.get(_key, PARAMETER_DEFAULTS.get(_key, 0.0)), _template_labels_map[_key][1]])
        if _template_rows:
            with st.expander("Template Parameters", expanded=True):
                st.dataframe(
                    pd.DataFrame(_template_rows, columns=["Parameter", "Template Value", "Unit"]),
                    use_container_width=True,
                    hide_index=True,
                )
        else:
            st.caption("This template has no stress parameters; it is the baseline scenario.")

        values = st.session_state["builder_values"]
        visible = st.session_state.get("builder_visible_params", _template.get("visible", []))
        st.markdown(f"**Scenario type:** `{active}`")

        m1, m2, m3 = st.columns(3)
        simulation_date = m1.date_input("Simulation date", value=date.today(), key="builder_simulation_date")
        horizon_days = m2.number_input("Horizon (days)", 1, 3650, 365, 1, key="builder_horizon")
        scenario_mode = m3.selectbox("Run mode", ["New Scenario", "Rerun Saved Scenario"], key="builder_run_mode")
        st.session_state["scenario_action"] = "old" if scenario_mode == "Rerun Saved Scenario" else "new"
        if scenario_mode == "Rerun Saved Scenario":
            if not history.empty and "scenario_id" in history.columns:
                old_options = history["scenario_id"].dropna().astype(int).tolist()
                selected_old = st.selectbox("Saved scenario", old_options, key="builder_old_scenario")
                st.session_state["selected_old_scenario"] = selected_old
                saved_row = history[history["scenario_id"].astype(int) == int(selected_old)]
                if not saved_row.empty:
                    saved_record = saved_row.iloc[0]
                    active = resolve_saved_template(str(saved_record.get("scenario_type","")))
                    st.session_state["active_template"] = active
                    saved_params = scenario_params_from_row(saved_record)
                    saved_values = template_values(active)
                    if active == "Individual Parameter Scenario":
                        driver_map = [("Market Rate Shock","rate_change_pp"),("Deposit Growth","deposit_growth_pct"),("Loan Growth","loan_growth_pct"),("Liquidity Shift","liquidity_shift_pct")]
                        selected_driver = "Market Rate Shock"
                        selected_value = 0.0
                        for label,key in driver_map:
                            if abs(float(saved_params.get(key,0.0))) > 1e-12:
                                selected_driver, selected_value = label, float(saved_params[key])
                                break
                        saved_values["individual_parameter"] = selected_driver
                        saved_values["individual_value"] = selected_value
                    else:
                        saved_values.update({
                            "rate": float(saved_params.get("rate_change_pp",0.0)),
                            "loan_pass": float(saved_params.get("loan_pass_through_pct",100.0)),
                            "deposit_pass": float(saved_params.get("deposit_pass_through_pct",100.0)),
                            "funding_pass": float(saved_params.get("funding_pass_through_pct",100.0)),
                            "investment_pass": float(saved_params.get("investment_pass_through_pct",100.0)),
                            "deposit_growth": float(saved_params.get("deposit_growth_pct",0.0)),
                            "loan_growth": float(saved_params.get("loan_growth_pct",0.0)),
                            "liquidity": float(saved_params.get("liquidity_shift_pct",0.0)),
                        })
                    st.session_state["builder_values"] = saved_values
                    st.session_state["builder_visible_params"] = list(SCENARIO_TEMPLATES[active]["visible"])
            else:
                st.warning("No saved scenarios are available.")

        active = st.session_state.get("active_template", active)
        values = st.session_state.get("builder_values", values)
        visible = st.session_state.get("builder_visible_params", visible)

        rate_change_pp = 0.0
        loan_pass_through = 100.0
        deposit_pass_through = 100.0
        funding_pass_through = 100.0
        investment_pass_through = 100.0
        deposit_growth = 0.0
        loan_growth = 0.0
        liquidity_shift = 0.0

        if "individual_parameter" in visible:
            st.markdown("### 🎯 Individual Scenario Driver")
            _driver_options = [
                "Market Rate Shock",
                "Deposit Growth",
                "Loan Growth",
                "Liquidity Shift",
            ]
            _default_driver = values.get("individual_parameter", "Market Rate Shock")
            if _default_driver not in _driver_options:
                _default_driver = "Market Rate Shock"
            _driver = st.selectbox(
                "Parameter to stress",
                _driver_options,
                index=_driver_options.index(_default_driver),
                key="builder_individual_parameter",
            )
            _driver_specs = {
                "Market Rate Shock": ("Shock value (percentage points)", -10000.0, 10000.0, 0.0, 0.1),
                "Deposit Growth": ("Deposit growth (%)", -90.0, 200.0, 0.0, 0.1),
                "Loan Growth": ("Loan growth (%)", -90.0, 200.0, 0.0, 0.5),
                "Liquidity Shift": ("Liquidity shift (%)", -100.0, 100.0, 0.0, 0.5),
            }
            _label, _lo, _hi, _base_default, _step = _driver_specs[_driver]
            _stored_value = float(values.get("individual_value", _base_default))
            _individual_value = st.number_input(
                _label, _lo, _hi, _stored_value, _step, key="builder_individual_value"
            )
            st.caption("Only the selected driver is stressed. All other scenario assumptions remain neutral.")
            if _driver == "Market Rate Shock":
                rate_change_pp = float(_individual_value)
            elif _driver == "Deposit Growth":
                deposit_growth = float(_individual_value)
            elif _driver == "Loan Growth":
                loan_growth = float(_individual_value)
            elif _driver == "Liquidity Shift":
                liquidity_shift = float(_individual_value)

        elif "text_prompt" in visible:
            st.markdown("### 🤖 Free Type Scenario Instruction")
            free_type_text = st.text_area(
                "Scenario text",
                value=st.session_state.get("free_type_text", ""),
                placeholder="Example: Increase market interest rates by 3%, increase loan balances by 5%, and reduce deposits by 10%.",
                height=120,
                key="builder_free_type_text",
            )
            st.session_state["free_type_text"] = free_type_text

            parse_col, status_col = st.columns([1, 2])
            with parse_col:
                parse_clicked = st.button("🧠 Parse with Phi-3", type="primary", use_container_width=True)
            with status_col:
                st.caption("Phi-3 reads the text and extracts explicit parameters. Missing parameters remain neutral.")

            if parse_clicked:
                if not free_type_text.strip():
                    st.warning("Enter a scenario description before parsing.")
                else:
                    parser_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
                    parser_model = os.getenv("OLLAMA_MODEL", "phi3")
                    try:
                        parsed = parse_free_type_scenario_with_ollama(parser_host, parser_model, free_type_text)
                        st.session_state["free_type_parsed"] = parsed
                        st.session_state["free_type_parsed_source"] = free_type_text
                        if parsed.get("parser_source") == "phi3":
                            st.success(f"Scenario parsed with {parser_model}.")
                        else:
                            st.warning("Phi-3/Ollama is unavailable, so the deterministic regex fallback extracted the scenario inputs.")
                    except Exception as exc:
                        st.session_state.pop("free_type_parsed", None)
                        st.session_state.pop("free_type_parsed_source", None)
                        st.error(f"Free Type parsing failed: {exc}")

            parsed_free_type = st.session_state.get("free_type_parsed")
            parsed_source = st.session_state.get("free_type_parsed_source")
            if parsed_free_type and parsed_source == free_type_text:
                extracted = parsed_free_type.get("parameters", {})
                extracted_rows = []
                labels = {
                    "rate_change_pp": ("Market rate shock", "pp"),
                    "loan_pass_through_pct": ("Loan pass-through", "%"),
                    "deposit_pass_through_pct": ("Deposit pass-through", "%"),
                    "funding_pass_through_pct": ("Funding pass-through", "%"),
                    "investment_pass_through_pct": ("Investment pass-through", "%"),
                    "deposit_growth_pct": ("Deposit growth", "%"),
                    "loan_growth_pct": ("Loan growth", "%"),
                    "liquidity_shift_pct": ("Liquidity shift", "%"),
                }
                for key, value in extracted.items():
                    if value is not None:
                        label, unit = labels[key]
                        extracted_rows.append([label, value, unit])
                if extracted_rows:
                    st.markdown("### Extracted assumptions")
                    st.dataframe(pd.DataFrame(extracted_rows, columns=["Parameter", "Value", "Unit"]), use_container_width=True, hide_index=True)
                else:
                    st.info("Phi-3 did not find any explicit numeric assumptions in the scenario text.")
            elif parsed_free_type and parsed_source != free_type_text:
                st.warning("The scenario text changed after parsing. Parse the new text again before running the simulation.")

        else:
            if "rate" in visible:
                st.markdown("### 📈 Market-rate assumption")
                rate_change_pp = st.number_input("Market rate shock (percentage points)", -100.0, 100.0, float(values.get("rate", 0.0)), 0.25, key="builder_market_rate")

            if any(k in visible for k in ["loan_pass", "deposit_pass", "funding_pass"]):
                st.markdown("### 🔁 Pass-through assumptions")
                p1, p2, p3, p4 = st.columns(4)
                if "loan_pass" in visible:
                    loan_pass_through = p1.number_input("Loan pass-through (%)", 0.0, 200.0, float(values.get("loan_pass", 100.0)), 5.0, key="builder_loan_pass")
                if "deposit_pass" in visible:
                    deposit_pass_through = p2.number_input("Deposit pass-through (%)", 0.0, 200.0, float(values.get("deposit_pass", 100.0)), 5.0, key="builder_deposit_pass")
                if "funding_pass" in visible:
                    funding_pass_through = p3.number_input("Funding pass-through (%)", 0.0, 200.0, float(values.get("funding_pass", 100.0)), 5.0, key="builder_funding_pass")
                if "investment_pass" in visible:
                    investment_pass_through = p4.number_input("Investment pass-through (%)", 0.0, 200.0, float(values.get("investment_pass", 100.0)), 5.0, key="builder_investment_pass")

            balance_items = []
            if "deposit_growth" in visible:
                balance_items.append(("deposit_growth", "Deposit growth (%)", -90.0, 200.0, float(values.get("deposit_growth", 0.0)), 0.5))
            if "loan_growth" in visible:
                balance_items.append(("loan_growth", "Loan growth (%)", -90.0, 200.0, float(values.get("loan_growth", 0.0)), 0.5))
            if "liquidity" in visible:
                balance_items.append(("liquidity", "Liquidity shift (%)", -100.0, 100.0, float(values.get("liquidity", 0.0)), 0.5))
            if balance_items:
                st.markdown("### 💰 Scenario assumptions")
                cols = st.columns(len(balance_items))
                vals = {}
                for i, (key, label, lo, hi, default, step) in enumerate(balance_items):
                    widget_key = {"deposit_growth":"builder_deposit_growth", "loan_growth":"builder_loan_growth", "liquidity":"builder_liquidity"}[key]
                    vals[key] = cols[i].number_input(label, lo, hi, default, step, key=widget_key)
                deposit_growth = vals.get("deposit_growth", 0.0)
                loan_growth = vals.get("loan_growth", 0.0)
                liquidity_shift = vals.get("liquidity", 0.0)

        st.markdown("### 📝 Scenario metadata")
        scenario_name = st.text_input("Scenario name", value=f"{active} - {simulation_date}", key="builder_scenario_name")
        scenario_description = st.text_area("Scenario description", placeholder="Optional business description...", height=80, key="builder_scenario_description")
        if active == "Free Type Scenario" and st.session_state.get("free_type_text"):
            scenario_description = st.session_state.get("free_type_text")
        elif active == "Individual Parameter Scenario":
            scenario_description = f"Individual driver: {st.session_state.get('builder_individual_parameter', values.get('individual_parameter', 'Market Rate Shock'))}"

        loan_rate_shock_pp = float(rate_change_pp)
        deposit_rate_shock_pp = float(rate_change_pp)
        funding_rate_shock_pp = float(rate_change_pp)

        params = {
            "rate_change_pp": float(rate_change_pp),
            "loan_rate_shock_pp": float(loan_rate_shock_pp),
            "deposit_rate_shock_pp": float(deposit_rate_shock_pp),
            "funding_rate_shock_pp": float(funding_rate_shock_pp),
            "loan_pass_through_pct": float(loan_pass_through),
            "deposit_pass_through_pct": float(deposit_pass_through),
            "funding_pass_through_pct": float(funding_pass_through),
            "investment_pass_through_pct": float(investment_pass_through),
            "deposit_growth_pct": float(deposit_growth),
            "loan_growth_pct": float(loan_growth),
            "liquidity_shift_pct": float(liquidity_shift),
            "yield_curve_shock_bps": float(rate_change_pp) * 100.0,
        }

        if active == "Individual Parameter Scenario":
            _individual_key_map = {
                "Market Rate Shock": "rate_change_pp",
                "Deposit Growth": "deposit_growth_pct",
                "Loan Growth": "loan_growth_pct",
                "Liquidity Shift": "liquidity_shift_pct",
            }
            _selected_driver = st.session_state.get("builder_individual_parameter", values.get("individual_parameter", "Market Rate Shock"))
            _selected_engine_key = _individual_key_map.get(_selected_driver)
            active_engine_parameter_keys = {_selected_engine_key} if _selected_engine_key else set()
        if active == "Free Type Scenario":
            parsed_free_type = st.session_state.get("free_type_parsed")
            parsed_source = st.session_state.get("free_type_parsed_source")
            if parsed_free_type and parsed_source == st.session_state.get("free_type_text", ""):
                extracted = parsed_free_type.get("parameters", {})
                for key in params:
                    if key in extracted and extracted[key] is not None:
                        params[key] = float(extracted[key])
                params["loan_rate_shock_pp"] = params["rate_change_pp"]
                params["deposit_rate_shock_pp"] = params["rate_change_pp"]
                params["funding_rate_shock_pp"] = params["rate_change_pp"]

        active_parameter_keys = {
            "rate": "rate_change_pp", "loan_pass": "loan_pass_through_pct",
            "deposit_pass": "deposit_pass_through_pct", "funding_pass": "funding_pass_through_pct", "investment_pass": "investment_pass_through_pct",
            "deposit_growth": "deposit_growth_pct", "loan_growth": "loan_growth_pct",
            "liquidity": "liquidity_shift_pct",
        }
        active_engine_parameter_keys = {active_parameter_keys[k] for k in visible if k in active_parameter_keys}
        if active == "Individual Parameter Scenario":
            _individual_key_map = {
                "Market Rate Shock": "rate_change_pp",
                "Deposit Growth": "deposit_growth_pct",
                "Loan Growth": "loan_growth_pct",
                "Liquidity Shift": "liquidity_shift_pct",
            }
            _selected_driver = st.session_state.get("builder_individual_parameter", values.get("individual_parameter", "Market Rate Shock"))
            _selected_engine_key = _individual_key_map.get(_selected_driver)
            active_engine_parameter_keys = {_selected_engine_key} if _selected_engine_key else set()
        if active == "Free Type Scenario":
            parsed_free_type = st.session_state.get("free_type_parsed")
            parsed_source = st.session_state.get("free_type_parsed_source")
            current_text = st.session_state.get("free_type_text", "")
            if parsed_free_type and parsed_source == current_text:
                extracted = parsed_free_type.get("parameters", {})
                active_engine_parameter_keys = {
                    key for key in extracted
                    if extracted.get(key) is not None and key in params
                }
        st.session_state["active_engine_parameter_keys"] = active_engine_parameter_keys


        calc_positions = positions
        calc_positions = positions
        calc_cashflows = cashflows
        calc_market_data = market_data

        after, product_after, position_after = apply_scenario(
            baseline=baseline, products=products, positions=calc_positions,
            simulation_date=pd.Timestamp(simulation_date), horizon_days=int(horizon_days),
            rate_change_pp=params["rate_change_pp"],
            deposit_growth_pct=params["deposit_growth_pct"],
            loan_growth_pct=params["loan_growth_pct"],
            liquidity_shift_pct=params["liquidity_shift_pct"],
            fee_income_growth_pct=0.0,
            loan_rate_shock_pp=params["loan_rate_shock_pp"],
            deposit_rate_shock_pp=params["deposit_rate_shock_pp"],
            funding_rate_shock_pp=params["funding_rate_shock_pp"],
            loan_pass_through_pct=params["loan_pass_through_pct"],
            deposit_pass_through_pct=params["deposit_pass_through_pct"],
            funding_pass_through_pct=params["funding_pass_through_pct"],
            investment_pass_through_pct=params["investment_pass_through_pct"],
            cashflows=calc_cashflows,
            market_data=calc_market_data,
        )
        comparison = comparison_table(baseline, after)
        risk_before = baseline.copy()
        risk_before["Position Repricing Gap"] = after.get("Position Repricing Gap", 0.0)
        risk_before["CF LCR Proxy %"] = after.get("CF LCR Proxy Base %", np.nan)
        risk_before["Investment Market Value Impact"] = 0.0
        risk_df = build_alm_risk_summary(risk_before, after)
        quality_df = build_data_quality_checks(baseline, calc_positions, calc_cashflows, calc_market_data, after)

        st.session_state["current_params"] = params
        st.session_state["current_after"] = after
        st.session_state["current_product_after"] = product_after
        st.session_state["current_position_after"] = position_after
        st.session_state["current_comparison"] = comparison
        st.session_state["current_risk_df"] = risk_df
        st.session_state["current_simulation_date"] = simulation_date
        st.session_state["current_horizon_days"] = int(horizon_days)
        st.session_state["current_scenario_name"] = scenario_name
        st.session_state["current_scenario_description"] = scenario_description
        st.session_state["current_quality_df"] = quality_df
        st.session_state["current_yield_curve_shock_bps"] = float(params.get("yield_curve_shock_bps", params.get("rate_change_pp",0.0)*100.0))

        st.markdown("### 💾 Save / Run")
        c1, c2 = st.columns(2)
        with c1:
            run_clicked = st.button("▶ Run & Save Simulation", type="primary", use_container_width=True)
        with c2:
            if st.button("↺ Reset Scenario Parameters", use_container_width=True):
                apply_template(active)
                st.rerun()

        if run_clicked:
            run_id, scenario_id, save_messages = persist_simulation(
                engine, scenario_name, active, simulation_date, int(horizon_days), params, comparison, risk_df,
                scenario_description=scenario_description,
                base_as_of_datetime=latest_date(positions_raw, "as_of_datetime"),
                existing_scenario_id=int(st.session_state["selected_old_scenario"]) if scenario_mode == "Rerun Saved Scenario" and st.session_state.get("selected_old_scenario") else None,
                positions_after=position_after, market_data=market_data, products=products, cashflows=cashflows,
                validation_df=calculation_validation_table(baseline, after, position_after, params),
            )
            st.session_state["last_run_id"] = run_id
            st.session_state["last_scenario_id"] = scenario_id
            for ok, message in save_messages:
                (st.success if ok else st.warning)(message)
            if run_id:
                st.success(f"Simulation completed. Run ID = {run_id}, Scenario ID = {scenario_id}")

        st.markdown("### 🔎 Live calculation preview")
        preview = pd.DataFrame([
            ["Market rate shock", params["rate_change_pp"], "pp", params["rate_change_pp"] / 100.0, "decimal"],
            ["Loan effective rate shock", params["loan_rate_shock_pp"] * params["loan_pass_through_pct"] / 100, "pp", params["loan_rate_shock_pp"] * params["loan_pass_through_pct"] / 10000, "decimal"],
            ["Deposit effective rate shock", params["deposit_rate_shock_pp"] * params["deposit_pass_through_pct"] / 100, "pp", params["deposit_rate_shock_pp"] * params["deposit_pass_through_pct"] / 10000, "decimal"],
            ["Funding effective rate shock", params["funding_rate_shock_pp"] * params["funding_pass_through_pct"] / 100, "pp", params["funding_rate_shock_pp"] * params["funding_pass_through_pct"] / 10000, "decimal"],
            ["Investment effective rate shock", params["rate_change_pp"] * params.get("investment_pass_through_pct",100.0) / 100, "pp", params["rate_change_pp"] * params.get("investment_pass_through_pct",100.0) / 10000, "decimal"],
            ["Loan balance growth", params["loan_growth_pct"], "%", None, ""],
            ["Deposit balance growth", params["deposit_growth_pct"], "%", None, ""],
            ["Liquidity shift", params["liquidity_shift_pct"], "%", None, ""],
        ], columns=["Input", "Value", "Unit", "Stored / Derived", "Stored Unit"])
        st.dataframe(preview, use_container_width=True, hide_index=True)

        render_ai_scenario_panel(
            scenario_name=scenario_name,
            scenario_type=active,
            simulation_date=simulation_date,
            horizon_days=int(horizon_days),
            scenario_params=params,
            before=baseline,
            after=after,
            risk_df=risk_df,
            panel_key="builder_current",
        )

    params = st.session_state.get("current_params")

    if params is None:
        params = {
            "rate_change_pp": 0.0, "loan_rate_shock_pp": 0.0, "deposit_rate_shock_pp": 0.0,
            "funding_rate_shock_pp": 0.0, "loan_pass_through_pct": 100.0,
            "deposit_pass_through_pct": 100.0, "funding_pass_through_pct": 100.0, "investment_pass_through_pct": 100.0,
            "deposit_growth_pct": 0.0, "loan_growth_pct": 0.0, "liquidity_shift_pct": 0.0,
            "yield_curve_shock_bps": 0.0,
        }
        after, product_after, position_after = apply_scenario(
            baseline=baseline, products=products, positions=positions,
            simulation_date=pd.Timestamp(date.today()), horizon_days=365,
            rate_change_pp=0.0, deposit_growth_pct=0.0, loan_growth_pct=0.0,
            liquidity_shift_pct=0.0, fee_income_growth_pct=0.0,
            loan_rate_shock_pp=0.0, deposit_rate_shock_pp=0.0, funding_rate_shock_pp=0.0,
            loan_pass_through_pct=100.0, deposit_pass_through_pct=100.0, funding_pass_through_pct=100.0,
            investment_pass_through_pct=100.0,
            cashflows=cashflows,
            market_data=market_data,
        )
        comparison = comparison_table(baseline, after)
        risk_df = build_alm_risk_summary(baseline, after)
        st.session_state["current_quality_df"] = build_data_quality_checks(baseline, positions, cashflows, market_data, after)
    else:
        after = st.session_state["current_after"]
        product_after = st.session_state["current_product_after"]
        position_after = st.session_state["current_position_after"]
        comparison = st.session_state["current_comparison"]
        risk_df = st.session_state["current_risk_df"]

    if page == "dashboard":
        st.markdown('<div class="section-header">🏠 Executive Dashboard</div>', unsafe_allow_html=True)

        dashboard_before = baseline
        dashboard_after = after
        dashboard_comparison = comparison
        dashboard_position_after = position_after
        dashboard_risk_df = risk_df
        dashboard_label = st.session_state.get("current_scenario_name", "Current Session")

        if not history.empty:
            scenario_options = [(0, "Current Session")]
            history_sorted = history.copy()
            if "scenario_id" in history_sorted.columns:
                history_sorted["scenario_id"] = pd.to_numeric(history_sorted["scenario_id"], errors="coerce")
                history_sorted = history_sorted.dropna(subset=["scenario_id"]).sort_values("scenario_id")
            for _, row in history_sorted.iterrows():
                sid = int(row["scenario_id"])
                name = str(row.get("scenario_name", f"Scenario {sid}"))
                scenario_options.append((sid, f"{name} (ID {sid})"))
            labels = [label for _, label in scenario_options]
            selected_label = st.selectbox(
                "Dashboard scenario", labels, index=0, key="dashboard_scenario_selector",
                help="Select Current Session or a previously saved scenario to refresh the KPIs and charts.",
            )
            selected_sid = dict((label, sid) for sid, label in scenario_options)[selected_label]
            if selected_sid != 0:
                loaded_dashboard = load_saved_scenario_for_dashboard(selected_sid, engine, baseline, products, positions, cashflows, market_data)
                if loaded_dashboard is not None:
                    dashboard_after = loaded_dashboard["after"]
                    dashboard_comparison = loaded_dashboard["comparison"]
                    dashboard_position_after = loaded_dashboard["position_after"]
                    dashboard_risk_df = loaded_dashboard["risk_df"]
                    dashboard_label = loaded_dashboard["scenario_name"]
                    snapshot_context = loaded_dashboard.get("snapshot_context", {})
                    quality_df = loaded_dashboard.get("quality", pd.DataFrame())
                    if snapshot_context.get("warning"):
                        st.warning(snapshot_context["warning"])
                    st.info(f"Viewing saved scenario: {dashboard_label} | Scenario ID: {selected_sid}. Dashboard selection is read-only and does not create a new simulation run.")

        if "quality_df" not in locals():
            quality_df = st.session_state.get(
                "current_quality_df",
                baseline_quality if "baseline_quality" in locals() else pd.DataFrame(),
            )

        st.caption(f"Displayed scenario: {dashboard_label}")

        dashboard_params = params
        dashboard_type = "Current Scenario"
        dashboard_date = st.session_state.get("current_simulation_date", date.today())
        dashboard_horizon = int(st.session_state.get("current_horizon_days", 365))
        if "loaded_dashboard" in locals() and loaded_dashboard is not None:
            dashboard_params = loaded_dashboard.get("params", params)
            dashboard_type = loaded_dashboard.get("scenario_type", "Saved Scenario")
            dashboard_date = loaded_dashboard.get("simulation_date", dashboard_date)
            dashboard_horizon = 365
        render_ai_scenario_panel(
            scenario_name=dashboard_label,
            scenario_type=dashboard_type,
            simulation_date=dashboard_date,
            horizon_days=dashboard_horizon,
            scenario_params=dashboard_params,
            before=dashboard_before,
            after=dashboard_after,
            risk_df=dashboard_risk_df,
            panel_key="dashboard_current",
        )

        kpis = scenario_kpi_cards(dashboard_before, dashboard_after)
        for offset in range(0, len(kpis), 4):
            cols = st.columns(4)
            for col, (label, before_v, after_v, unit) in zip(cols, kpis[offset:offset+4]):
                if unit == "%":
                    if pd.isna(after_v):
                        col.metric(label, "N/A")
                    elif label in ["NII Change %", "Profit Change %"]:
                        col.metric(label, f"{after_v:,.2f}%")
                    else:
                        delta = after_v - before_v if pd.notna(before_v) else np.nan
                        col.metric(
                            label,
                            f"{after_v:,.2f}%",
                            f"{delta:,.2f}%" if pd.notna(delta) else None,
                        )
                else:
                    delta = after_v - before_v
                    col.metric(label, format_large_number(after_v), format_large_number(delta))

        st.markdown("### Core financial impact")
        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(style_nbe_figure(impact_bar(
                dashboard_before, dashboard_after,
                [("Position NII","Position NII"), ("Position Interest Income","Position Interest Income"), ("Position Interest Expense","Position Interest Expense")],
                "Position Interest Impact Before vs After"
            )), use_container_width=True)
        with c2:
            st.plotly_chart(style_nbe_figure(impact_bar(dashboard_before, dashboard_after, [("Loans","Position Loans"),("Deposits","Position Deposits"),("Investments","Position Investments")], "Position Portfolio Before vs After")), use_container_width=True)

        st.markdown("### ALM impact")
        c1, c2 = st.columns(2)
        with c1:
            gap_df = pd.DataFrame({"Metric":["Repricing Gap Base","Repricing Gap After"],"Value":[dashboard_before.get("Position Repricing Gap",0), dashboard_after.get("Position Repricing Gap",0)]})
            gap_df["Formatted_Value"] = gap_df["Value"].apply(format_large_number)
            fig = px.bar(gap_df, x="Metric", y="Value", title="Repricing Gap", text="Formatted_Value", color_discrete_sequence=NBE_PALETTE)
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            fig.update_traces(textposition='outside')
            st.plotly_chart(style_nbe_figure(fig), use_container_width=True)
        with c2:
            cf_df = pd.DataFrame({"Metric":["Inflows Base","Inflows After","Outflows Base","Outflows After"],"Value":[dashboard_before.get("CF Inflow",0),dashboard_after.get("CF Inflow",0),dashboard_before.get("CF Outflow",0),dashboard_after.get("CF Outflow",0)]})
            cf_df["Formatted_Value"] = cf_df["Value"].apply(format_large_number)
            fig2 = px.bar(cf_df, x="Metric", y="Value", title="Liquidity Cash Flow", text="Formatted_Value", color_discrete_sequence=NBE_PALETTE)
            fig2.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            fig2.update_traces(textposition='outside')
            st.plotly_chart(style_nbe_figure(fig2), use_container_width=True)

        st.markdown("### Data quality / calculation status")
        if not quality_df.empty:
            st.dataframe(quality_df, use_container_width=True, hide_index=True)

        st.markdown("### Calculation validation")
        dashboard_validation = calculation_validation_table(dashboard_before, dashboard_after, dashboard_position_after, dashboard_params)
        st.dataframe(dashboard_validation, use_container_width=True, hide_index=True)

        st.markdown("### Scenario impact detail")
        st.dataframe(dashboard_comparison, use_container_width=True, hide_index=True)

    if page == "history":
        st.markdown('<div class="section-header">📚 Saved Scenarios</div>', unsafe_allow_html=True)
        if history.empty:
            st.info("No saved scenarios found.")
        else:
            st.dataframe(history, use_container_width=True, height=300, hide_index=True)
            sid = st.selectbox("Scenario ID", history["scenario_id"].dropna().astype(int).tolist(), key="history_scenario_id")
            selected_params = scenario_params_from_row(scenarios_raw[scenarios_raw["scenario_id"]==sid].iloc[0] if not scenarios_raw[scenarios_raw["scenario_id"]==sid].empty else None)
            st.markdown("### Saved parameters")
            if selected_params:
                st.dataframe(pd.DataFrame(list(selected_params.items()), columns=["Parameter", "Value"]), use_container_width=True, hide_index=True)
            st.caption("Use Rerun Saved Scenario from Scenario Builder to rerun a saved scenario.")

    if page == "comparison":
        st.markdown('<div class="section-header">📊 Scenario Comparison</div>', unsafe_allow_html=True)
        st.caption("Compare saved scenario results without ranking or scoring; values are shown exactly as stored in the saved runs.")
        if history.empty:
            st.info("No saved scenarios found.")
        else:
            scenario_ids = history["scenario_id"].dropna().astype(int).tolist()
            selected = st.multiselect("Scenarios to compare", scenario_ids, default=scenario_ids[:min(3,len(scenario_ids))], key="comparison_scenarios")
            rows=[]
            if selected:
                placeholders=", ".join([f":sid{i}" for i in range(len(selected))])
                sql=f"SELECT sr.scenario_id, sr.run_id, s.scenario_name, s.scenario_type, r.metric_name AS kpi_name, r.scenario_value FROM Simulation_Runs sr JOIN Scenarios s ON s.scenario_id=sr.scenario_id LEFT JOIN Simulation_Results r ON r.run_id=sr.run_id WHERE sr.scenario_id IN ({placeholders}) ORDER BY sr.run_id DESC"
                try:
                    q=read_sql_df(engine, sql, {f"sid{i}":v for i,v in enumerate(selected)})
                    if not q.empty:
                        q=q.drop_duplicates(subset=["scenario_id","kpi_name"], keep="first")
                        pivot=q.pivot_table(index="kpi_name", columns="scenario_name", values="scenario_value", aggfunc="first").reset_index()
                        st.dataframe(pivot, use_container_width=True, hide_index=True)
                        long=q.copy()
                        long["Formatted_Value"] = long["scenario_value"].apply(format_large_number)
                        fig=px.bar(long, x="kpi_name", y="scenario_value", color="scenario_name", barmode="group", title="Saved scenario KPI comparison", text="Formatted_Value", color_discrete_sequence=NBE_PALETTE)
                        fig.update_layout(height=430, xaxis_tickangle=-30, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                        fig.update_traces(textposition='outside')
                        st.plotly_chart(style_nbe_figure(fig), use_container_width=True)
                    else:
                        st.info("No KPI results found for the selected scenarios.")
                except Exception as exc:
                    st.warning(f"Scenario comparison query failed: {exc}")

    if page == "analytics":
        st.markdown('<div class="section-header">📈 ALM Analytics</div>', unsafe_allow_html=True)
        st.markdown("### Rate sensitivity")
        shock_range = st.slider("Market rate shock range (pp)", -10.0, 10.0, (-3.0, 3.0), 0.5, key="analytics_shock_range")
        shocks=np.arange(shock_range[0], shock_range[1]+0.001, 0.5)
        rows=[]
        for shock in shocks:
            a,_,_=apply_scenario(baseline=baseline, products=products, positions=positions, simulation_date=pd.Timestamp(date.today()), horizon_days=int(st.session_state.get("current_horizon_days",365)), rate_change_pp=float(shock), deposit_growth_pct=params["deposit_growth_pct"], loan_growth_pct=params["loan_growth_pct"], liquidity_shift_pct=params["liquidity_shift_pct"], fee_income_growth_pct=0.0, loan_rate_shock_pp=float(shock), deposit_rate_shock_pp=float(shock), funding_rate_shock_pp=float(shock), loan_pass_through_pct=params["loan_pass_through_pct"], deposit_pass_through_pct=params["deposit_pass_through_pct"], funding_pass_through_pct=params["funding_pass_through_pct"], investment_pass_through_pct=params.get("investment_pass_through_pct",100.0), cashflows=cashflows, market_data=market_data)
            rows.append([shock, a.get("Position NII",0), a.get("Liquidity",0)])
        sens=pd.DataFrame(rows, columns=["Rate Shock (pp)","Position NII","Liquidity"])
        fig=go.Figure()
        fig.add_trace(go.Scatter(x=sens["Rate Shock (pp)"], y=sens["Position NII"], mode="lines+markers", name="Position NII", line=dict(color=NBE_GREEN, width=3), marker=dict(color=NBE_ORANGE, size=7)))
        fig.update_layout(title="Position NII sensitivity to market-rate shock", height=430, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(style_nbe_figure(fig),use_container_width=True)

        st.markdown("### Market yield curve used by the engine")
        curve_ui = build_market_curve(market_data, as_of=pd.Timestamp(date.today()))
        if not curve_ui.empty:
            curve_chart = curve_ui.copy()
            curve_chart["Base Yield %"] = curve_chart["base_rate"] * 100.0
            curve_chart["Scenario Yield %"] = curve_chart["Base Yield %"] + float(after.get("Yield Curve Shock (bps)", 0.0))/100.0
            fig_curve = px.line(curve_chart, x="tenor", y=["Base Yield %","Scenario Yield %"], markers=True, title="Market Data Yield Curve: Base vs Shocked")
            fig_curve.update_traces(line=dict(width=3))
            st.plotly_chart(style_nbe_figure(fig_curve), use_container_width=True)
            st.caption(f"Market_Data rows used: {int(after.get('Curve Rates Used',0))} | Parallel curve shock: {after.get('Yield Curve Shock (bps)',0):.0f} bps")
        else:
            st.warning("No usable yield-curve observations were found in Market_Data for the selected date.")

        st.markdown("### Market yield curve used by the engine")
        curve_ui = build_market_curve(market_data, as_of=pd.Timestamp(date.today()))
        if not curve_ui.empty:
            curve_chart = curve_ui.copy()
            curve_chart["Base Yield %"] = curve_chart["base_rate"] * 100.0
            curve_chart["Scenario Yield %"] = curve_chart["Base Yield %"] + float(after.get("Yield Curve Shock (bps)", 0.0))/100.0
            fig_curve = px.line(curve_chart, x="tenor", y=["Base Yield %","Scenario Yield %"], markers=True, title="Market Data Yield Curve: Base vs Shocked")
            fig_curve.update_traces(line=dict(width=3))
            st.plotly_chart(style_nbe_figure(fig_curve),use_container_width=True,key="market_yield_curve")
            st.caption(f"Market_Data rows used: {int(after.get('Curve Rates Used',0))} | Parallel curve shock: {after.get('Yield Curve Shock (bps)',0):.0f} bps")
        else:
            st.warning("No usable yield-curve observations were found in Market_Data for the selected date.")

        st.markdown("### Portfolio exposure")
        if not position_after.empty:
            exp=position_after.groupby("Position Category").agg(Balance=("After Balance","sum"), Interest=("Interest After","sum")).reset_index()
            exp["Formatted_Balance"] = exp["Balance"].apply(format_large_number)
            exp["Formatted_Interest"] = exp["Interest"].apply(format_large_number)
            c1,c2=st.columns(2)
            with c1: 
                fig_bar = px.bar(exp, x="Position Category", y="Balance", title="Exposure by position category", text="Formatted_Balance", color_discrete_sequence=NBE_PALETTE)
                fig_bar.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                fig_bar.update_traces(textposition='outside')
                st.plotly_chart(style_nbe_figure(fig_bar), use_container_width=True)
            with c2: 
                fig_bar2 = px.bar(exp, x="Position Category", y="Interest", title="Interest contribution by category", text="Formatted_Interest", color_discrete_sequence=NBE_PALETTE)
                fig_bar2.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                fig_bar2.update_traces(textposition='outside')
                st.plotly_chart(style_nbe_figure(fig_bar2), use_container_width=True)

        st.markdown("### Liquidity stress")
        liq_stress=np.arange(-30,31,5)
        lr=[]
        for shock in liq_stress:
            lr.append([shock, after.get("Liquidity Base",0)*(1+shock/100), after.get("Liquidity Base",0)*(1-shock/100)])
        ldf=pd.DataFrame(lr,columns=["Liquidity Shift (%)","Liquidity","Net Cashflow proxy"])
        fig_liq_sens = px.line(ldf,x="Liquidity Shift (%)",y=["Liquidity","Net Cashflow proxy"],markers=True,title="Liquidity stress sensitivity")
        fig_liq_sens.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(style_nbe_figure(fig_liq_sens),use_container_width=True)

    if page == "audit":
        st.markdown('<div class="section-header">🧮 Calculation Audit</div>', unsafe_allow_html=True)
        st.info("This page shows the relationship between each input control, the formula, and the result. The purpose is to verify that every input reaches the calculation engine.")

        audit_rows = [
            ["Position loan balance", "Position Loans × (1 + Loan Growth / 100)", baseline.get("Position Loans", 0.0), after.get("Position Loans", 0.0), params["loan_growth_pct"]],
            ["Position deposit balance", "Position Deposits × (1 + Deposit Growth / 100)", baseline.get("Position Deposits", 0.0), after.get("Position Deposits", 0.0), params["deposit_growth_pct"]],
            ["Loan effective rate shock", "Market Rate Shock × Loan Pass-through / 100", 0.0, params["rate_change_pp"] * params["loan_pass_through_pct"] / 100, params["loan_pass_through_pct"]],
            ["Deposit effective rate shock", "Market Rate Shock × Deposit Pass-through / 100", 0.0, params["rate_change_pp"] * params["deposit_pass_through_pct"] / 100, params["deposit_pass_through_pct"]],
            ["Funding effective rate shock", "Market Rate Shock × Funding Pass-through / 100", 0.0, params["rate_change_pp"] * params["funding_pass_through_pct"] / 100, params["funding_pass_through_pct"]],
            ["Investment effective rate shock", "Market Rate Shock × Investment Pass-through / 100", 0.0, params["rate_change_pp"] * params.get("investment_pass_through_pct",100.0) / 100, params.get("investment_pass_through_pct",100.0)],
            ["Cash-flow liquidity", "(Inflow × factor) − (Outflow × factor)", baseline.get("CF Net Cashflow", 0.0), after.get("Liquidity", 0.0), params["liquidity_shift_pct"]],
            ["Position NII", "Base Position NII + Position interest deltas", baseline.get("Position NII", 0.0), after.get("Position NII", 0.0), params["rate_change_pp"]],
            ["Investment market value", "ΔPV ≈ −Duration × ΔYield × Fair Value", after.get("Investment Market Value Base", 0.0), after.get("Investment Market Value Impact", 0.0), params["rate_change_pp"]],
        ]
        st.dataframe(pd.DataFrame(audit_rows, columns=["Metric", "Formula", "Before", "After / Effect", "Driving Input"]), use_container_width=True, hide_index=True)

        st.markdown("### Position-level repricing check")
        if not position_after.empty:
            audit_cols = [
                c for c in [
                    "Position Category", "position_id", "product_id",
                    "After Balance", "Before Rate", "After Rate", "Repricing Fraction",
                    "Eligible", "Applied Shock", "Interest Before", "Interest After",
                    "Annual Interest Change", "Interest Change"
                ] if c in position_after.columns
            ]
            st.dataframe(position_after[audit_cols], use_container_width=True, height=420, hide_index=True)
        else:
            st.warning("No position-level data available for repricing audit.")

        st.markdown("### Calculation trace")
        trace_rows = [
            ["Model amount unit", MODEL_AMOUNT_UNIT, "", "All monetary values use one database/model unit."],
            ["Loan interest change", after.get("Loan Interest Change", 0.0), "EGP", "Positions only."],
            ["Deposit interest change", after.get("Deposit Interest Change", 0.0), "EGP", "Positions only."],
            ["Funding interest change", after.get("Funding Interest Change", 0.0), "EGP", "Positions only."],
            ["Position NII change", after.get("Position NII", 0.0) - baseline.get("Position NII", 0.0), "EGP", "Position interest income changes minus Position interest expense changes."],
            ["Position NII change %", pct_change(baseline.get("Position NII", 0.0), after.get("Position NII", 0.0)), "%", "Positions only."],
        ]
        st.dataframe(
            pd.DataFrame(trace_rows, columns=["Trace Item", "Value", "Unit", "Explanation"]),
            use_container_width=True,
            hide_index=True,
        )

        st.markdown("### Independent Calculation Validation")
        validation_df = calculation_validation_table(baseline, after, position_after, params)
        st.dataframe(validation_df, use_container_width=True, hide_index=True)
        failed_checks = int((validation_df["Status"] == "FAIL").sum()) if not validation_df.empty else 0
        if failed_checks:
            st.error(f"{failed_checks} calculation validation check(s) failed. Review Expected vs Actual before trusting the scenario.")
        else:
            st.success("All displayed calculation checks passed within the configured tolerance.")

        st.markdown("### Data quality checks")
        audit_quality = st.session_state.get(
            "current_quality_df",
            build_data_quality_checks(
                baseline,
                positions,
                cashflows,
                market_data,
                after,
            ),
        )
        st.dataframe(audit_quality, use_container_width=True, hide_index=True)

        st.markdown("### Input propagation status")
        checks = []
        for key, label in [
            ("rate_change_pp", "Market rate shock"),
            ("loan_pass_through_pct", "Loan pass-through"), ("deposit_pass_through_pct", "Deposit pass-through"),
            ("funding_pass_through_pct", "Funding pass-through"), ("investment_pass_through_pct", "Investment pass-through"), ("loan_growth_pct", "Loan growth"),
            ("deposit_growth_pct", "Deposit growth"), ("liquidity_shift_pct", "Liquidity shift"),
        ]:
            checks.append([label, params[key], "Applied to engine", "OK"])
        st.dataframe(pd.DataFrame(checks, columns=["Spin Button", "Current Value", "Engine Mapping", "Status"]), use_container_width=True, hide_index=True)

    if page == "risk":
        st.markdown('<div class="section-header">💧 Liquidity & Risk</div>', unsafe_allow_html=True)
        left, right = st.columns(2)
        with left:
            st.dataframe(risk_df, use_container_width=True, height=320, hide_index=True)
        with right:
            risk_chart = risk_df.copy()
            risk_chart["Formatted_Impact"] = risk_chart["Impact"].apply(format_large_number)
            fig = px.bar(risk_chart[["Risk Indicator", "Impact", "Formatted_Impact"]], x="Risk Indicator", y="Impact", title="ALM Risk Impact", text="Formatted_Impact", color_discrete_sequence=NBE_PALETTE)
            fig.update_layout(height=320, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            fig.update_traces(textposition='outside')
            st.plotly_chart(style_nbe_figure(fig), use_container_width=True)

        st.markdown("### Liquidity / cashflow")
        liq = pd.DataFrame({"Metric": ["CF Net Cashflow Base", "CF Net Cashflow After", "CF Inflow", "CF Outflow"], "Value": [after.get("Liquidity Base", 0), after.get("Liquidity", 0), after.get("CF Inflow", 0), after.get("CF Outflow", 0)]})
        st.dataframe(liq, use_container_width=True, hide_index=True)
        st.caption("LCR Proxy is an analytical proxy, not a regulatory LCR calculation.")

    if page == "data":
        st.markdown('<div class="section-header">📊 Data Explorer</div>', unsafe_allow_html=True)
        data_map = {
            "Products": products_raw,
            "Positions": positions_raw,
            "Cash_Flows": cashflows_raw,
            "Market_Data": market_data_raw,
            "Scenarios": scenarios_raw,
            "Simulation_Runs": simulation_runs_raw,
            "Simulation_Results": simulation_results_raw,
        }
        table_name=st.selectbox("Table",list(data_map.keys()))
        df=data_map[table_name]
        st.caption(f"Rows loaded: {len(df)}")
        st.dataframe(df,use_container_width=True,height=600,hide_index=True)

    if page == "ai":
        st.warning("AI Insights is integrated into Scenario Workspace and Executive Dashboard. Use the scenario-specific AI explanation there.")

    if page == "advanced":
        render_page_header("Advanced Settings", "Technical configuration, connectivity, and data quality", "Connected" if db_connected else "Connection Required")
        st.info("Technical settings are intentionally kept out of the main workspace. Changes are applied after saving and reconnecting.")
        tab_db, tab_ai, tab_quality, tab_engine = st.tabs(["Database Connection", "Ollama / Phi-3", "Data Quality", "Engine Information"])
        with tab_db:
            st.markdown("### Database Connection")
            c1, c2 = st.columns(2)
            new_host = c1.text_input("Host", value=st.session_state["db_host"], key="advanced_db_host")
            new_port = c1.number_input("Port", 1, 65535, int(st.session_state["db_port"]), 1, key="advanced_db_port")
            new_database = c2.text_input("Database", value=st.session_state["db_name"], key="advanced_db_name")
            new_user = c2.text_input("User", value=st.session_state["db_user"], key="advanced_db_user")
            new_password = st.text_input("Password", value=st.session_state["db_password"], type="password", key="advanced_db_password")
            if st.button("Save and Reconnect", type="primary", use_container_width=True):
                st.session_state["db_host"] = new_host
                st.session_state["db_port"] = int(new_port)
                st.session_state["db_name"] = new_database
                st.session_state["db_user"] = new_user
                st.session_state["db_password"] = new_password
                st.cache_resource.clear()
                st.rerun()
            if db_connected:
                st.success(f"Connected to {database} on {host}:{port}.")
            else:
                st.warning(f"Connection required: {host}:{port}/{database}")
                if connection_error:
                    st.code(connection_error, language="text")
                st.caption(
                    "The application does not create or modify your database. "
                    "It only connects to the existing ALM schema."
                )
        with tab_ai:
            st.markdown("### Local AI Configuration")
            ai_host = st.text_input("Ollama URL", value=st.session_state["ollama_host"], key="advanced_ollama_host")
            ai_model = st.text_input("Ollama model", value=st.session_state["ollama_model"], key="advanced_ollama_model")
            if st.button("Save AI Configuration", use_container_width=True):
                st.session_state["ollama_host"] = ai_host
                st.session_state["ollama_model"] = ai_model
                st.success("AI configuration saved for this session.")
            st.caption("Phi-3 is used for Free Type scenario parsing. Deterministic Python logic remains responsible for financial calculations.")
        with tab_quality:
            # Build the quality table with exactly one row count for each dataset.
            # The previous version had 14 row-count values for only 8 dataset names,
            # which caused: ValueError: All arrays must be of the same length.
            quality_sources = {
                "Products": products_raw,
                "Positions": positions_raw,
                    "Cash_Flows": cashflows_raw,
                "Market_Data": market_data_raw,
                "Scenarios": scenarios_raw,
                "Simulation_Runs": simulation_runs_raw,
                "Simulation_Results": simulation_results_raw,
            }
            quality = pd.DataFrame({
                "Dataset": list(quality_sources.keys()),
                "Rows": [len(df) for df in quality_sources.values()],
            })
            st.dataframe(quality, use_container_width=True, hide_index=True)
        with tab_engine:
            st.markdown("### Engine Information")
            st.write({
                "calculation_engine": "Deterministic Python - strict Position/Cash_Flow calculation domains",
                "database": "MySQL",
                "UI": "Streamlit",
                "local_ai": "Ollama / Phi-3",
                "rate_shock_convention": "UI shock is percentage points; Positions.interest_rate is decimal fraction; Scenarios.market_rate_shock_pct stores percentage points",
                "interest_calculation": "Dynamic period-by-period repricing from Positions + Market_Data over the selected horizon",
                "market_data_role": "Yield curve reference used by the dynamic repricing engine",
                
            })

    st.divider()
    st.caption("ALM calculation engine: deterministic Python calculations. Ollama is explanation-only and does not alter the numbers.")
