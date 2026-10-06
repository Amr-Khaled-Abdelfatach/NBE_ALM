# Design Decisions

| Decision | Why | Alternative considered |
|---|---|---|
| Deterministic Python engine | Results must be explainable, reproducible and auditable. | Letting an LLM compute figures (rejected: non-deterministic). |
| LLM explanation-only | Keeps numbers trustworthy while still giving natural-language access. | No AI at all. |
| Local Ollama / Phi-3 | Bank data stays on-premises. | Hosted LLM API. |
| Existing MySQL, no DDL | Schema belongs to the data owner. | App-managed migrations. |
| Rates as decimal fractions | One convention across tables avoids ×100 errors. | Percent values. |
| Event-based repricing driven by `Market_Data` | More realistic than a flat "repricing fraction" assumption. | Fixed repricing fraction × shock. |
| Parallel curve shock plus pass-through | Simple, transparent, easy to explain. | Twist/steepener shapes (see roadmap). |
| Schema-tolerant persistence | Tolerates schema versions that differ slightly. | Strict column mapping. |
| Independent validation table | Recomputes KPIs to catch engine regressions. | Trust the engine output. |
| Strict data domains (Positions vs Cash_Flows) | Prevents mixing interest and liquidity logic. | One merged dataset. |
| Streamlit | Fast to build an analyst UI around pandas. | Flask/React front end. |
