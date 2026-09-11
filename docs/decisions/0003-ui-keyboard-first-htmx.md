# 0003: UI — keyboard-first, server-rendered HTML (FastAPI + Jinja2 + HTMX)

- **Status:** Proposed — under reconsideration, see 2026-09-12 note below
- **Date:** 2026-09-11 (revised 2026-09-12)

## Context

The legacy Streamlit dashboard was clunky: full-script reruns, little control over layout, no real
keyboard control. Original goal: a **minimalist** UI you can drive entirely from the keyboard, like
Vim or Pop!_OS workspaces (switch views, move through lists, act on selection). Must stay cheap to
run (one Cloud Run container) and simple to build (no JS toolchain if avoidable).

**2026-09-12 revision:** the owner does not want to write or learn real frontend (HTML/CSS/JS,
focus/state management) just to get keyboard control — that trade is not worth it to them. Keyboard-first
is **dropped as a hard goal**. The remaining, higher-priority constraints are:
- Minimize time spent on UI plumbing — as close to zero frontend work as possible.
- Visual result should look better than the legacy Streamlit app (a specific complaint: Streamlit's
  default look is disliked, not just its rerun/layout limitations).
- Still need, out of the box: sensible editable tables (review/fix classification by hand), file
  upload/drag-drop (statement import), buttons, and dashboard-style charts with filters.

This reopens the decision: the HTMX + hand-written JS keyboard layer below was justified almost
entirely by the keyboard-first goal, which no longer holds.

## Decision (proposed, pre-2026-09-12 — see below)

- Server-rendered HTML with **Jinja2** templates from the same FastAPI app, partial page updates via
  **HTMX** (loaded from a pinned CDN or vendored file).
- A small, hand-written **vanilla JS keyboard layer** (single module, no framework) implementing the
  keymap in [`specs/keyboard-ux.md`](../specs/keyboard-ux.md). Every action is also reachable from a
  `:` command palette, so the keymap is discoverable.
- Minimal CSS (system font, one monospace font, light/dark via `prefers-color-scheme`). No component library.
- Charts: a small library that renders from JSON the server provides, or server-side SVG — pick when
  building the dashboard view.
- The JSON API (`/api/...`) stays, so a terminal client is possible later.

**Not re-decided yet as of 2026-09-12.** Leading candidate under discussion: **NiceGUI**
(pure Python, built on Quasar/Vue — no HTML/CSS/JS to write) as a like-for-like replacement for
Streamlit, rather than the HTMX approach above. Nothing is committed; this needs a follow-up
conversation before the status can move to Accepted.

## Alternatives considered

| Option | Why not (for now) |
|---|---|
| Streamlit (legacy) | Disliked visual style; full-script reruns and limited layout — though `st.data_editor` (editable tables) and `@st.fragment` (partial reruns) are newer APIs that may address some of this without switching frameworks at all |
| FastAPI + Jinja2 + HTMX + hand-written JS keyboard layer | Solves keyboard-first, but that goal is dropped (2026-09-12); would mean writing and owning real frontend code (focus/state management, accessibility) for a benefit no longer wanted |
| **NiceGUI** (pure Python, Quasar/Vue under the hood) | *Leading candidate, not decided.* No HTML/CSS/JS to write. Better default visuals (Material Design) than Streamlit. `ui.aggrid` gives a full editable-grid component (inline edit, per-column filters, sorting) for the classification-review table; `ui.upload` gives drag-drop file import; `ui.echart`/`ui.plotly` for dashboard charts. Trade-off: event/callback-driven state model (`on_click`, manual state) rather than Streamlit's simpler top-to-bottom rerun-per-script model — closer to writing a small GUI app than a notebook script. Keyboard control would be minimal/absent, which is now acceptable. |
| React/Svelte SPA (+ cmdk-style palette) | Full JS toolchain and build for a single-user app; more moving parts. Ruled out regardless of the keyboard question. |
| Textual TUI (terminal) | Excellent keyboard UX, pure Python, but only in a terminal unless served via textual-serve. Still a candidate for a **second** client on top of `/api` later, independent of what the primary UI ends up being. |

## Consequences

- Good (if HTMX path is kept): one language (Python) + tiny JS; one container; fast pages; the keyboard layer is fully ours.
- Bad (if HTMX path is kept): keyboard handling, focus management and accessibility are our
  responsibility; HTMX swaps must keep focus/selection state sane — effort the owner has said they
  do not want to spend.
- Good (if NiceGUI path is chosen): zero HTML/CSS/JS authored; better default visual polish than
  Streamlit; `/api` JSON layer from the HTMX plan is not needed since NiceGUI is the whole app, though
  it could still be exposed separately if a future client wants it.
- Bad (if NiceGUI path is chosen): state is callback-driven, not scripted top-to-bottom like Streamlit
  — a small mental shift; editable-table ergonomics depend on `ui.aggrid` wiring rather than a single
  turnkey call.
- Open / follow-ups:
  - **Verify the WebSocket cost model on Cloud Run before choosing NiceGUI.** NiceGUI (like Streamlit)
    keeps per-client state on the server and syncs over a persistent WebSocket. On Cloud Run that is a
    long-running request: an open browser tab can keep an instance alive and billed, which cuts against
    scale-to-zero and the ~0 PLN target in [ADR 0002](0002-hosting-cloud-run-iap.md). Also check what an
    instance restart does to open sessions, and whether session affinity is needed above one instance.
    A server-rendered page has no such connection — this is the main architectural price of the
    pure-Python UI frameworks, and it is decisive, not a detail.
  - Decide HTMX-keyboard-first vs. NiceGUI vs. "stay on Streamlit and try `data_editor`/`fragment`" —
    needs a short spike/comparison before this ADR can move to Accepted.
  - Chart library, whether bulk-edit uses a modal or inline mode — still open regardless of framework.
  - `specs/keyboard-ux.md` is now stale relative to the dropped keyboard-first goal; revisit once the
    framework choice is made.
