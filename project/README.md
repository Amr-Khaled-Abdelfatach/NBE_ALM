# NBE ALM Simulation Center

## Structure

```text
NBE_ALM/
├── app.py
├── config.py
├── database.py
├── calculations.py
├── scenarios.py
├── analytics.py
└── ui.py
```

## Responsibility

- `app.py` — thin Streamlit entry point.
- `config.py` — global parameters, defaults, limits, database settings, AI settings, UI/theme settings.
- `database.py` — connection to the existing MySQL database, table validation, reads, and simulation persistence.
- `calculations.py` — deterministic ALM calculations, normalization, market curve, repricing, and scenario engine.
- `scenarios.py` — scenario templates, parameter mapping, saved-scenario mapping, Free Type parsing, and explanation-only Ollama integration.
- `analytics.py` — KPI comparison, risk summary, data quality, and independent calculation validation.
- `ui.py` — all Streamlit pages, navigation, controls, charts, tables, and dashboard rendering.

## Existing database

The application does **not** create the database or tables. It expects these existing tables:

- `Products`
- `Positions`
- `Cash_Flows`
- `Market_Data`
- `Scenarios`
- `Simulation_Runs`
- `Simulation_Results`

## Configuration

Database values are read from environment variables:

- `DB_HOST`
- `DB_PORT`
- `DB_NAME`
- `DB_USER`
- `DB_PASSWORD`
- `DB_DRIVER`

Defaults are defined in `config.py` and can also be edited there.

Ollama settings:

- `OLLAMA_HOST`
- `OLLAMA_MODEL`
- `OLLAMA_TIMEOUT`
- `OLLAMA_TEMPERATURE`

## Run

From inside the `NBE_ALM` directory:

```bash
streamlit run app.py
```

The financial calculation engine remains deterministic Python logic. Ollama/Phi-3 is used only for Free Type scenario interpretation/explanation and does not calculate or overwrite financial results.


## Database connection troubleshooting

The application connects to an existing MySQL database and does not create
the database or tables. If the connection fails, open **System Settings →
Database Connection**. The application displays the actual MySQL/SQLAlchemy
error so host, port, database name, credentials, missing tables, and service
issues can be distinguished.
