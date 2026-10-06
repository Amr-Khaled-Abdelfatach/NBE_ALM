# Security

## Controls in place

| Area | Control |
|---|---|
| SQL injection | Values are bound parameters (`:name`). Table and column names come from a fixed list or from `information_schema` and are back-ticked. |
| Schema safety | The application issues no DDL; it only reads, inserts and updates data rows. |
| Transactions | Each insert/update runs inside `engine.begin()` (commit or rollback). |
| Connection health | `pool_pre_ping=True` and `pool_recycle=1800` avoid stale connections. |
| Data locality | The LLM runs locally through Ollama; no bank data goes to an external API. |
| AI isolation | The LLM is explanation-only and cannot change financial results. |
| Failure handling | DB and AI failures are caught and shown without stopping the app. |

## Gaps to close before production

| Gap | Recommendation |
|---|---|
| No user authentication or roles | Put the app behind SSO or a reverse proxy; add role-based access. |
| `executed_by` is always `"Streamlit"` | Record the authenticated user for a real audit trail. |
| Password is concatenated into the connection URL | Build it with `sqlalchemy.engine.URL.create(...)` so special characters are escaped. |
| Defaults `root` / empty password | Use a dedicated least-privilege account (SELECT on source tables; INSERT/UPDATE on result tables). |
| Password kept in `st.session_state` | Prefer environment variables or a secrets manager. |
| Raw database errors shown in the UI | Show them only in an admin view. |
| Network | Use TLS for MySQL and keep Ollama on localhost. |
