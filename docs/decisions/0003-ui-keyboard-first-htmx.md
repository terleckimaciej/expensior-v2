# 0003: UI — a ready-made Python framework (NiceGUI) as the starting point

> The file keeps its original name (`…keyboard-first-htmx`) so that existing links stay valid; the
> keyboard-first HTMX design it first proposed is now an *alternative*, see below.

- **Status:** Proposed — default: NiceGUI, pending the spike below
- **Date:** 2026-09-11 (revised 2026-09-12, 2026-11-09)

## Context

The legacy Streamlit dashboard was clunky: full-script reruns, little control over layout, no real
keyboard control. Original goal: a **minimalist** UI you can drive entirely from the keyboard. Must stay
cheap to run (one Cloud Run container) and simple to build.

**2026-09-12 revision:** the owner does not want to write or learn real frontend (HTML/CSS/JS,
focus/state management) just to get keyboard control. Keyboard-first is **dropped as a hard goal**.
Remaining constraints:
- Minimize time spent on UI plumbing — as close to zero frontend work as possible.
- Visual result should look better than the legacy Streamlit app (its default look is disliked).
- Out of the box: editable tables (review/fix classification by hand), file upload/drag-drop
  (statement import), buttons, dashboard-style charts with filters.

**2026-11-09 revision:** the owner weighed writing (or heavily AI-generating) a Vue/Nuxt frontend for
flexibility, prompted by a Reddit thread critical of NiceGUI and by Reflex. Conclusion: the owner will not
use frontend skills outside this project and does not want to learn them, and code they cannot review
is a risk in an app that handles money. **A ready-made framework is the default for the start.** The
worry that remains — being boxed in by the framework — is handled by a boundary rule, a spike with
explicit exit criteria and a named plan B, not by committing to a frontend now.
Facts behind this: [`research/ui-frameworks-2026-11.md`](../research/ui-frameworks-2026-11.md).

## Decision

1. **Start with NiceGUI** (pure Python on FastAPI; Quasar/Vue underneath — nothing to author in
   HTML/CSS/JS). It provides `ui.aggrid` (editable grid for the classification-review table),
   `ui.upload` (statement import) and `ui.echart` / `ui.plotly` (dashboard charts).
2. **Boundary rule — the UI layer is thin.** No domain logic in UI code. Parsing and the rules engine are
   pure Python, aggregates are SQL views (ADR 0007), and the UI only calls those and renders the result.
   Replacing the UI then costs a rewrite of the UI, not of the project. This is the answer to lock-in.
3. **Spike before "Accepted"** (timebox 1–2 days, NiceGUI on Cloud Run — checklist in the research note):
   - the editable classification table works in `ui.aggrid` and edits can be persisted as new,
     superseding classification rows;
   - what an idle open tab costs under request-based billing (ADR 0002, target 0–5 PLN/month), whether
     the instance scales to zero once the tab is closed, and what an instance restart does to open sessions;
   - image size and cold start;
   - one dashboard chart with filters.
4. **Exit criteria — abandon NiceGUI if** an idle open tab pushes the projected cost over budget, or the
   editable table cannot be made usable, or cold start is unacceptable.
5. **Plan B — Vue 3 + Vite SPA (no Nuxt)**, built into static files and served by the same FastAPI
   container, over a thin JSON API on top of the SQL views. A SPA is the only model without a persistent
   WebSocket, so scale-to-zero works. Its price: a Node toolchain (dev and a Docker build stage), more code,
   and the owner must be able to review frontend code. Rules if it is ever used: TypeScript client generated
   from the OpenAPI schema; **money crosses the API as strings**, never JSON numbers (a `NUMERIC(12,2)` becomes
   a float in JS).

## Alternatives considered

| Option | Why not (for now) |
|---|---|
| **NiceGUI** | *The default — see Decision.* Trade-offs: callback-driven state instead of Streamlit's top-to-bottom rerun; editable-table ergonomics depend on `ui.aggrid` wiring (pull-style read-back, a grid rebuild drops in-progress edits); WebSocket per open tab; keyboard control minimal (acceptable now) |
| Streamlit (legacy) | Disliked visual style; full-script reruns, limited layout — though `st.data_editor` and `@st.fragment` are newer APIs that may address some of it. Fallback if the NiceGUI spike fails and Plan B looks too heavy |
| Reflex | Same WebSocket-per-client model and server-side state, so no gain on the main risk; compiles Python to a React frontend, so adds a JS toolchain to build and a two-part (frontend + backend) deploy that must fit one Cloud Run service; editable-table story not checked. Revisit if NiceGUI fails for reasons Reflex does not share |
| Vue 3 + Vite SPA + FastAPI JSON API | **Plan B.** Best fit for scale-to-zero and for flexibility, but needs frontend knowledge the owner does not want to acquire |
| Nuxt | SSR/SEO buys nothing behind IAP; adds a Node server or a static-generate step on top of Vue |
| Own / heavily AI-written frontend | Flexibility is hypothetical today (tables, forms, upload, charts are standard widgets), while the cost is concrete: code the owner cannot review or debug, and silent money bugs |
| FastAPI + Jinja2 + HTMX + hand-written JS keyboard layer (the original proposal) | Solves keyboard-first, but that goal is dropped (2026-09-12); would mean writing and owning real frontend code (focus/state management, accessibility) for a benefit no longer wanted |
| React/Svelte SPA | Full JS toolchain for a single-user app; same objections as Vue, with no advantage here |
| Textual TUI (terminal) | Excellent keyboard UX, pure Python, but terminal-only unless served via textual-serve. Still a candidate for a **second** client later, independent of the primary UI |

## Consequences

- Good: zero HTML/CSS/JS authored; better default look than Streamlit; one container, one language; the
  thin-UI rule keeps the exit open.
- Bad / accepted risks:
  - State is callback-driven, a small mental shift from Streamlit.
  - NiceGUI keeps per-client state on the server over a persistent WebSocket. On Cloud Run an open tab can
    keep an instance active and possibly billed, which cuts against scale-to-zero and the ~0 PLN target in
    [ADR 0002](0002-hosting-cloud-run-iap.md). Whether it does — and what restarts do to open sessions — is
    **not settled by the Google docs** and must be measured in the spike; this is the decisive risk, not a detail.
  - NiceGUI is a smaller project than the big JS ecosystems; if it stalls, the thin-UI rule limits the damage.
- Follow-ups:
  - Run the spike (tracked as a GitHub issue); then move this ADR to
    Accepted (NiceGUI) or Superseded (Plan B / Streamlit).
  - If NiceGUI is kept: decide the chart library and whether bulk edit uses a modal or inline mode.
  - [`specs/keyboard-ux.md`](../specs/keyboard-ux.md) stays stale until/unless keyboard navigation returns.
