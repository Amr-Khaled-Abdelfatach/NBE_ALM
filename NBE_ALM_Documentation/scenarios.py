"""Scenario definitions, parameter parsing, templates, and explanation-only AI."""
import json
import re
from datetime import date
from typing import Dict
import pandas as pd
import requests
import streamlit as st
from config import (SCENARIO_DEFAULTS, SCENARIO_TEMPLATES, PARAMETER_DEFAULTS, OLLAMA_TIMEOUT, OLLAMA_TEMPERATURE)

def scenario_summary(df):
    if df.empty: return df
    fields=["scenario_id","scenario_code","scenario_name","scenario_type","base_as_of_datetime","simulation_date","horizon_days","market_rate_shock_pct","loan_pass_through_pct","deposit_pass_through_pct","funding_pass_through_pct","investment_pass_through_pct","loan_growth_pct","deposit_growth_pct","deposit_runoff_pct","liquidity_shock_pct","fx_shock_pct","yield_curve_shock_bps","credit_spread_shock_bps","gold_shock_pct","status"]
    keep=[c for c in fields if c in df.columns]
    return df[keep].drop_duplicates().reset_index(drop=True)


def scenario_params_from_row(row) -> Dict[str,float]:
    if row is None: return {}
    def f(name):
        try: return float(row.get(name,0) or 0)
        except Exception: return 0.0
    rate=f("market_rate_shock_pct")
    return {
        "rate_change_pp": rate,
        "loan_rate_shock_pp": rate,
        "deposit_rate_shock_pp": rate,
        "funding_rate_shock_pp": rate,
        "loan_pass_through_pct": f("loan_pass_through_pct") or 100.0,
        "deposit_pass_through_pct": f("deposit_pass_through_pct") or 100.0,
        "funding_pass_through_pct": f("funding_pass_through_pct") or 100.0,
        "investment_pass_through_pct": f("investment_pass_through_pct") or 100.0,
        "deposit_growth_pct": f("deposit_growth_pct"),
        "loan_growth_pct": f("loan_growth_pct"),
        "liquidity_shift_pct": f("liquidity_shock_pct"),
        "yield_curve_shock_bps": f("yield_curve_shock_bps"),
    }


def ollama_status(host, model):
    try:
        import requests
        r=requests.get(host.rstrip("/")+"/api/tags",timeout=3)
        r.raise_for_status()
        names=[m.get("name","") for m in r.json().get("models",[])]
        installed=any(model.lower() in n.lower() or n.lower().startswith(model.lower()+":") for n in names)
        return True,installed,names
    except Exception as exc:
        return False,False,str(exc)


def ask_ollama(host, model, payload):
    try:
        import requests
        running,installed,info=ollama_status(host,model)
        if not running: return f"Phi-3 unavailable: Ollama is not running at {host}. Start Ollama and try again."
        if not installed: return f"Phi-3 unavailable: model '{model}' is not installed. Available models: {', '.join(info) if isinstance(info,list) else info}"
        prompt=("You are an ALM analyst. Explain only the supplied deterministic results. Do not change numbers or calculate new values. Identify the selected scenario and the main financial drivers.\n\n"+json.dumps(payload,ensure_ascii=False,indent=2,default=str))
        response=requests.post(host.rstrip("/")+"/api/generate",json={"model":model,"prompt":prompt,"stream":False},timeout=OLLAMA_TIMEOUT)
        response.raise_for_status(); return response.json().get("response","No response.")
    except Exception as exc:
        return f"Phi-3 request failed: {exc}"


def clean_numeric_value(val):
    if val is None or val=="": return None
    if isinstance(val,(int,float)): return float(val)
    s=str(val).strip().replace(",","").lower()
    m=re.search(r"[-+]?\d+(?:\.\d+)?",s)
    if not m: return None
    f=float(m.group(0))
    if "bps" in s: return f/100.0
    return f


def extract_parameters_regex(text_val):
    res={}; lower=text_val.lower()
    patterns={
        "rate_change_pp":r'(?:rate|interest|فائدة|فائده)\D{0,15}?([+-]?\d+(?:\.\d+)?)\s*(%|pp|bps|نقطة|نقطة أساس)?',
        "deposit_growth_pct":r'(?:deposit|deposits|ودائع|الودائع)\D{0,15}?([+-]?\d+(?:\.\d+)?)\s*%?',
        "loan_growth_pct":r'(?:loan|loans|قروض|القروض)\D{0,15}?([+-]?\d+(?:\.\d+)?)\s*%?',
        "investment_pass_through_pct":r'(?:investment|investments|استثمار|استثمارات|الاستثمار|الاستثمارات)\D{0,15}?(?:pass.?through|تمرير|انتقال)\D{0,15}?([+-]?\d+(?:\.\d+)?)\s*%?',
        "liquidity_shift_pct":r'(?:liquidity|سيولة|السيولة)\D{0,15}?([+-]?\d+(?:\.\d+)?)\s*%?',
    }
    for key,pat in patterns.items():
        m=re.search(pat,text_val,re.I)
        if not m: continue
        v=float(m.group(1)); unit=m.group(2) if len(m.groups())>1 else ""
        if "bps" in str(unit).lower() or "نقطة" in str(unit): v/=100.0
        if any(w in lower for w in ["decrease","reduction","reduce","drop","runoff","decrease","انخفاض","تراجع","خفض","سحب"]) and v>0: v=-v
        res[key]=v
    return res


def parse_free_type_scenario_with_ollama(host, model, scenario_text):
    text_value=str(scenario_text or "").strip()
    if not text_value: raise ValueError("Scenario text is empty.")
    allowed=["rate_change_pp","loan_pass_through_pct","deposit_pass_through_pct","funding_pass_through_pct","investment_pass_through_pct","deposit_growth_pct","loan_growth_pct","liquidity_shift_pct"]
    result={k:None for k in allowed}
    parser_source="regex_fallback"
    try:
        import requests
        running,installed,_=ollama_status(host,model)
        if running and installed:
            parser_source="phi3"
            prompt=("Extract explicit ALM scenario assumptions from the text. Return ONLY JSON with numeric values. Keys: "+", ".join(allowed)+". A market rate shock in percent/percentage points must be returned as percentage points, e.g. 3 means +3 pp.\nScenario: "+text_value)
            r=requests.post(host.rstrip("/")+"/api/generate",json={"model":model,"prompt":prompt,"stream":False,"format":"json","options":{"temperature":0}},timeout=OLLAMA_TIMEOUT)
            r.raise_for_status(); raw=r.json().get("response","").strip(); parsed=json.loads(raw)
            for k in allowed:
                v=clean_numeric_value(parsed.get(k)) if isinstance(parsed,dict) else None
                if v is not None: result[k]=v
    except Exception:
        pass
    for k,v in extract_parameters_regex(text_value).items():
        if result.get(k) is None: result[k]=v
    return {"scenario_name":"Free Type Scenario","parameters":result,"parser_source":parser_source}


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

def build_scenario_parameters(values=None):
    """Return a complete, normalized scenario parameter dictionary."""
    params = dict(SCENARIO_DEFAULTS)
    if values:
        params.update({k: v for k, v in values.items() if k in params})
    return params
