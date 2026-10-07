"""Global configuration and model parameters for NBE ALM."""
import os

APP_NAME = "NBE ALM Simulation Center"
APP_VERSION = "1.0.0"
CALCULATION_ENGINE_VERSION = 1

# Model conventions
MODEL_AMOUNT_UNIT = "EGP"
RATE_STORAGE_CONVENTION = "decimal_fraction"
DAYS_PER_YEAR = 365.0
DEFAULT_HORIZON_DAYS = 365
DEFAULT_CURRENCY = "EGP"
DATABASE_NAME = "nbe_alm_simulation"

# Database connection: the application connects to an existing database.
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_NAME = os.getenv("DB_NAME", DATABASE_NAME)
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_DRIVER = os.getenv("DB_DRIVER", "mysql+pymysql")
DB_POOL_PRE_PING = True
DB_POOL_RECYCLE = 1800
DB_READ_LIMIT = 100000

REQUIRED_TABLES = [
    "Products", "Positions", "Cash_Flows", "Market_Data",
    "Scenarios", "Simulation_Runs", "Simulation_Results",
]

# Repricing / market model
TENOR_DAY_FACTORS = {"D": 1.0, "W": 7.0, "M": 30.4375, "Y": 365.0}
DEFAULT_REFERENCE_TENOR_DAYS = 365
MAX_REFERENCE_TENOR_DAYS = 3650
MAX_REPRICING_EVENTS = 3650
DEFAULT_PASS_THROUGH_PCT = 100.0
DEFAULT_YIELD_CURVE_SHOCK_BPS = 0.0
DEFAULT_RATE_SHOCK_PP = 0.0

# Scenario defaults and limits. UI values are percentage points unless explicitly named bps.
PARAMETER_DEFAULTS = {
    "rate": 0.0,
    "loan_pass": 100.0,
    "deposit_pass": 100.0,
    "funding_pass": 100.0,
    "investment_pass": 100.0,
    "deposit_growth": 0.0,
    "loan_growth": 0.0,
    "liquidity": 0.0,
}

SCENARIO_DEFAULTS = {
    "rate_change_pp": 0.0,
    "loan_rate_shock_pp": 0.0,
    "deposit_rate_shock_pp": 0.0,
    "funding_rate_shock_pp": 0.0,
    "loan_pass_through_pct": 100.0,
    "deposit_pass_through_pct": 100.0,
    "funding_pass_through_pct": 100.0,
    "investment_pass_through_pct": 100.0,
    "loan_growth_pct": 0.0,
    "deposit_growth_pct": 0.0,
    "liquidity_shift_pct": 0.0,
    "yield_curve_shock_bps": 0.0,
}

SCENARIO_LIMITS = {
    "rate_change_pp": (-20.0, 20.0),
    "loan_rate_shock_pp": (-20.0, 20.0),
    "deposit_rate_shock_pp": (-20.0, 20.0),
    "funding_rate_shock_pp": (-20.0, 20.0),
    "loan_pass_through_pct": (0.0, 200.0),
    "deposit_pass_through_pct": (0.0, 200.0),
    "funding_pass_through_pct": (0.0, 200.0),
    "investment_pass_through_pct": (0.0, 200.0),
    "loan_growth_pct": (-100.0, 100.0),
    "deposit_growth_pct": (-100.0, 100.0),
    "liquidity_shift_pct": (-100.0, 100.0),
    "yield_curve_shock_bps": (-2000.0, 2000.0),
}

SCENARIO_TEMPLATES = {
    "Base Case": {
        "scenario_type": "BASE",
        "description": "Baseline scenario with no stress assumptions.",
        "visible": [],
    },
    "Combined Stress Scenario": {
        "scenario_type": "COMBINED_STRESS",
        "description": "Full scenario workspace with all model assumptions available for combined stress testing.",
        "rate": 3.0, "loan_pass": 100.0, "deposit_pass": 100.0,
        "funding_pass": 100.0, "investment_pass": 100.0,
        "deposit_growth": -5.0, "loan_growth": 5.0, "liquidity": -15.0,
        "visible": ["rate", "loan_pass", "deposit_pass", "funding_pass", "investment_pass", "deposit_growth", "loan_growth", "liquidity"],
    },
    "Individual Parameter Scenario": {
        "scenario_type": "INDIVIDUAL_PARAMETER",
        "description": "Choose one primary scenario driver and set its value while keeping all other assumptions neutral.",
        "individual_parameter": "Market Rate Shock", "individual_value": 0.0,
        "visible": ["individual_parameter", "individual_value"],
    },
    "Free Type Scenario": {
        "scenario_type": "FREE_TYPE",
        "description": "Describe the scenario in natural language and use Phi-3 to extract explicit numeric assumptions.",
        "visible": ["text_prompt"],
    },
}
PREDEFINED_TEMPLATE_NAMES = list(SCENARIO_TEMPLATES.keys())

PAGES = {
    "Executive Dashboard": "dashboard",
    "Scenario Workspace": "workspace",
    "ALM Analytics & Risk": "analytics_workspace",
    "Data & Audit": "data_workspace",
    "System Settings": "advanced",
}

# Local AI / explanation-only configuration
AI_ENABLED = os.getenv("AI_ENABLED", "true").lower() == "true"
AI_EXPLANATION_ONLY = True
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "phi3")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "300"))
OLLAMA_TEMPERATURE = float(os.getenv("OLLAMA_TEMPERATURE", "0.0"))

# Validation thresholds
CALCULATION_TOLERANCE = float(os.getenv("CALCULATION_TOLERANCE", "1e-6"))
RATE_WARNING_THRESHOLD = float(os.getenv("RATE_WARNING_THRESHOLD", "2.0"))
LCR_WARNING_THRESHOLD = float(os.getenv("LCR_WARNING_THRESHOLD", "100.0"))

# Streamlit / UI
PAGE_TITLE = APP_NAME
PAGE_ICON = "🏦"
PAGE_LAYOUT = "wide"
INITIAL_SIDEBAR_STATE = "expanded"
CHART_HEIGHT = 430
CHART_MARGIN = dict(l=20, r=20, t=55, b=45)
CHART_FONT = "Arial"
UI_BORDER_RADIUS = 14
UI_BUTTON_HEIGHT = 42
DEFAULT_TABLE_HEIGHT = 420

# NBE-inspired visual system. This is a prototype and not an official NBE-branded application.
NBE_GREEN = "#007A3D"
NBE_DARK_GREEN = "#005B2D"
NBE_ORANGE = "#F7941D"
NBE_LIGHT_GREEN = "#EAF5EF"
NBE_PALE_ORANGE = "#FFF3E0"
NBE_TEXT = "#173B2A"
NBE_MUTED = "#66786D"
NBE_PALETTE = [NBE_GREEN, NBE_ORANGE, NBE_DARK_GREEN, "#2E8B57", "#F6A64B", "#73B88D"]


# Documentation Setup
DOCS_ENABLED = True
DOCS_BASE_URL = "https://amr-khaled-abdelfatach.github.io/NBE_ALM/"

PAGE_DOCS = {
    "Executive Dashboard": "",
    "Scenario Workspace": "scenarios/",
    "ALM Analytics & Risk": "analytics/",
    "Data & Audit": "database/",
    "System Settings": "getting-started/"
}

DOCS_LINKS = {
    "Market-rate assumption": "scenarios/#market-rate-assumption",
    "Pass-through assumptions": "scenarios/#pass-through-assumptions",
    "Scenario assumptions": "scenarios/#scenario-assumptions",
    "Live calculation preview": "scenarios/#live-calculation-preview",
    "ALM Analytics": "analytics/",
    "Calculation Audit": "calculation-engine/"
}