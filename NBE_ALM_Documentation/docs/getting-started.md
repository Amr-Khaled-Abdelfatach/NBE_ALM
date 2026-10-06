# Getting Started

## Prerequisites

- Python 3.10+ (the code uses `tuple[bool, str]` annotations)
- MySQL 8.x with the `nbe_alm_simulation` database loaded
- (Optional) [Ollama](https://ollama.com) with the `phi3` model

Python packages, inferred from the imports: `streamlit`, `pandas`, `numpy`, `plotly`, `sqlalchemy`, `pymysql`, `requests`.

```bash
pip install streamlit pandas numpy plotly sqlalchemy pymysql requests
```

## 1. Load the database

The application does **not** create the schema. Import the provided dump once:

```bash
mysql -u root -p < NBE_Database.sql
```

## 2. Configure the connection

Settings are read from environment variables (defaults in `config.py`):

| Variable | Default | Purpose |
|---|---|---|
| `DB_HOST` | `localhost` | MySQL host |
| `DB_PORT` | `3306` | MySQL port |
| `DB_NAME` | `nbe_alm_simulation` | Database name |
| `DB_USER` | `root` | User |
| `DB_PASSWORD` | *(empty)* | Password |
| `DB_DRIVER` | `mysql+pymysql` | SQLAlchemy driver |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama endpoint |
| `OLLAMA_MODEL` | `phi3` | Model name |
| `OLLAMA_TIMEOUT` | `300` | Seconds |
| `AI_ENABLED` | `true` | Toggle AI features |

!!! warning
    The defaults (`root` with an empty password) are for local development only. Use a dedicated least-privilege user elsewhere. See [Security](security.md).

## 3. Run

```bash
streamlit run app.py
```

If the connection fails, the app stays usable: open **System Settings → Database Connection**, where the real MySQL/SQLAlchemy error is shown.

## 4. (Optional) Local AI

```bash
ollama pull phi3
ollama serve
```

Without Ollama, free-text scenarios fall back to regex parsing and AI explanations show an "unavailable" message.

## Project structure

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
