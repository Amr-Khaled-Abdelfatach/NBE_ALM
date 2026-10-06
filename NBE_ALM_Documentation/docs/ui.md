# User Interface (`ui.py`)

`ui.run_app()` configures the page, applies the NBE theme (`CUSTOM_CSS`), connects to the database, loads all seven tables, builds the baseline and routes to the selected page.

## Navigation (`config.PAGES`)

| Page | Purpose |
|---|---|
| **Executive Dashboard** | KPI cards, impact charts and AI insight for the active or a saved scenario. |
| **Scenario Workspace** | Choose a template, set parameters or free text, run, and save. |
| **ALM Analytics & Risk** | Before/after comparison, risk summary, history and comparison views. |
| **Data & Audit** | Raw data views and calculation audit (validation table). |
| **System Settings** | Database connection, Ollama, data quality, engine information. |

## Behaviour worth noting

- **Graceful degradation:** if the database is unreachable the app does not stop; System Settings stays available and shows the real error.
- **Run → save:** the Scenario Workspace calls `apply_scenario`, builds risk and validation tables, then `persist_simulation`.
- **Saved scenarios** can be reloaded onto the dashboard through `load_saved_scenario_for_dashboard`.
- **Charts** use Plotly and are styled by `style_nbe_figure` with the NBE palette.
- **Large numbers** are shortened by `format_large_number` (K / M / B).

## Helper functions

| Function | Purpose |
|---|---|
| `render_page_header` | Title bar with connection status |
| `scenario_kpi_cards` | KPI cards with change % |
| `impact_bar` | Before/after bar chart |
| `render_ai_scenario_panel` | Button and output for the AI explanation |
| `apply_template` / `start_custom_scenario` | Load template values into session state |
