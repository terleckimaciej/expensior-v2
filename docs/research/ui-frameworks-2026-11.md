# UI frameworks — what was checked for ADR 0003

- **Checked:** 2026-11-09. Re-verify at the linked sources if older than ~3 months.
- **Used by:** [ADR 0003](../decisions/0003-ui-keyboard-first-htmx.md)
- **Legend:** ✅ verified at the source on the date above · ⚠️ not confirmed by the source — to be measured
  in the spike · 🧠 reasoning / prior knowledge, not looked up.

## Three ways a web UI can work

| Model | How it works | Examples | Cost to this project |
|---|---|---|---|
| Server-rendered HTML | The server returns finished HTML; the browser only displays it | Jinja + HTMX | Owner writes real frontend (focus, state, a11y) for keyboard UX — dropped, see ADR 0003 |
| SPA | The browser downloads a JS app and runs it; talks to the server in JSON. Needs a build step (Vite, Node) | Vue, React | Frontend to learn and *review*; but static files + short API calls → scale-to-zero works |
| Python UI framework | UI state lives on the server; the browser is a thin client on a persistent WebSocket | NiceGUI, Reflex, Streamlit | Zero frontend to write; a WebSocket per open tab (see Cloud Run below) |

Nuxt is Vue plus routing plus server-side rendering (SSR). 🧠 SSR serves SEO and first paint of public
pages; behind IAP it adds a Node server (or a static-generate step) for nothing. If Vue is ever needed:
Vue 3 + Vite, no Nuxt.

## Comparison against the ADR 0003 criteria

| Criterion | NiceGUI | Reflex | Vue 3 + Vite SPA (plan B) |
|---|---|---|---|
| Frontend code to write | none | none | yes (or AI-written, which the owner must still be able to review) |
| JS toolchain | none authored 🧠 | compiles Python to a React frontend ✅; Node/bun is not mentioned in the install docs, a third-party guide says Reflex fetches its own toolchain on export ⚠️ | Node + npm + Vite in dev and in a Docker build stage 🧠 |
| Editable table | `ui.aggrid`: `'editable': True` per column, per-column filters (`agTextColumnFilter`, `floatingFilter`) ✅; community edition by default ✅; sorting is not demonstrated on the docs page ⚠️ | not checked ⚠️ | any grid library 🧠 |
| Reading edits back into Python | pull model: `get_client_data()` / `load_client_data()`; row data is not updated until the cell leaves edit mode (`stopEditingWhenCellsLoseFocus` helps); mutating `rowData` rebuilds the grid and drops in-progress edits ✅ | not checked ⚠️ | explicit API calls 🧠 |
| One container | yes — runs on FastAPI/uvicorn 🧠 | frontend (port 3000) + FastAPI backend (port 8000) in dev ✅; production needs the static frontend and the WebSocket backend behind one URL — a third-party guide uses Caddy in one container and warns that a misrouted WebSocket gives a dead UI with no error ⚠️ | FastAPI serves the built static files 🧠 |
| Python | 3.9+ 🧠 | 3.11+ ✅ | backend as today |
| State on the server | per client, in memory 🧠; disconnected client deleted if it does not reconnect, the delay is not stated on the docs page ✅/⚠️ | per client token, in-memory dict by default; docs say production uses Redis ✅ | none (stateless API) |
| WebSocket vs scale-to-zero | **yes, problem applies** | **yes, same problem** | **no WebSocket** |

Streamlit (legacy app): 🧠 not re-checked in this note; ADR 0003 keeps `st.data_editor` / `@st.fragment`
as an option to try.

## Cloud Run and WebSockets (decisive for ADR 0002 budget)

Source: [Cloud Run — Using WebSockets](https://docs.cloud.google.com/run/docs/triggering/websockets),
[billing settings](https://docs.cloud.google.com/run/docs/configuring/billing-settings).

- ✅ A WebSocket stream is an HTTP request, so it is subject to the service's request timeout: default
  5 minutes, up to 60 minutes. Longer connections are dropped; the client must reconnect.
- ✅ Within one connection the client stays on the same instance. Across connections, session affinity is
  best effort; syncing state between instances needs external storage.
- ✅ The WebSockets page says an instance with an open WebSocket is treated as active (CPU allocated).
- ⚠️ The billing-settings page does not say whether an open WebSocket is billed as "request processing" under
  request-based billing (it only states: billed while processing requests, idle instances stay at most
  15 minutes). Cost of an idle open tab is therefore **unknown — measure it**.
- ⚠️ What happens to open connections on scale-down / instance shutdown is not described by either page.
  Third-party blog posts contradict each other; do not rely on them.
- 🧠 Bounded worst case: with a 60-minute timeout, one forgotten tab holds an instance for at most an hour
  per connection — but an auto-reconnecting client can start the cycle again while the tab stays open.

## Spike checklist (what ADR 0003 asks to measure)

1. Deploy a minimal NiceGUI app to Cloud Run (`min-instances=0`, request-based billing, IAP on).
2. Open one tab, leave it idle; read instance-time metrics for an hour and project a monthly cost.
3. Close the tab; confirm the instance scales to zero.
4. Redeploy / force an instance restart with a tab open; note what the user sees and whether state is lost.
5. Edit a few cells in `ui.aggrid`, read them back, persist as a new classification row (append-only).
6. Record image size and cold start (time to first byte after idle).

## The Reddit thread that prompted the re-check

Owner-pasted r/Python thread "Implementing dashboard as a webpage in an enterprise setting" (about two years
old). One commenter says he would "never recommend NiceGUI" without giving reasons, suggests Reflex, and ends
up recommending FastAPI + HTMX + Tailwind. Other commenters recommend NiceGUI or Dash. Context there is a
multi-user enterprise dashboard, not a single-user app behind IAP. Recorded as colour, not as evidence.

## Sources

- [How Reflex Works](https://reflex.dev/docs/advanced-onboarding/how-reflex-works) — React frontend + FastAPI
  backend, WebSocket events and dirty-var updates, state manager (checked 2026-11-09)
- [Reflex installation](https://reflex.dev/docs/getting-started/installation/) — Python 3.11+ (checked 2026-11-09)
- [NiceGUI — ui.aggrid](https://nicegui.io/documentation/aggrid) — editable cells, filters, edition,
  edit read-back (checked 2026-11-09)
- [NiceGUI — events/lifecycle](https://nicegui.io/documentation/section_action_events) — `on_disconnect`,
  `on_delete` (checked 2026-11-09)
- [Cloud Run — Using WebSockets](https://docs.cloud.google.com/run/docs/triggering/websockets) (checked 2026-11-09)
- [Cloud Run — billing settings](https://docs.cloud.google.com/run/docs/configuring/billing-settings)
  (checked 2026-11-09)
