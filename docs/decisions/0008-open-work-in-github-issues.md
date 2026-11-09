# 0008: Open work lives in GitHub issues; a Project is the status view; docs carry no status

- **Status:** Accepted
- **Date:** 2026-11-09

## Context

Until now open work sat in `docs/domain/backlog.md` as a markdown checklist. Markdown checklists go stale:
they are ticked by hand, and a reader cannot tell a forgotten tick from unfinished work. They also say
nothing about *stage* — what is only an idea, what is ready to pick up, what is in progress.

The owner wants to see that at a glance, and wants work to be traceable to code: an issue, a pull request
that closes it, a squash commit on `master`. The sibling project `gcloud-web` already works this way
(its ADR 0021); this ADR adopts the same model and adds a GitHub Project, which that project deferred.

## Decision

- **Every piece of open work is a GitHub issue.** Its checklist of tasks lives in the issue, not in markdown.
- **Issue structure:** `feature` — Context, Plan, Tasks, Done when; `idea` — Context, Proposal, Open
  questions; `bug` — what happened, what was expected, environment. Templates in `.github/ISSUE_TEMPLATE/`.
- **Labels:** `enhancement` (planned work), `idea` (worth considering, not planned), `bug`, `research`.
  `research` marks a time-boxed investigation: a `feature` issue whose Done when is "the answer is recorded
  in an ADR or a research note". It is a kind of work, not a stage.
- **Milestone = a release** (`0.1.0` is the MVP). It holds the issues that must be closed before that release.
  Work without a release yet is an open issue without a milestone.
- **A GitHub Project is the status view,** with one `Status` field: **Backlog → Ready → In progress → Done**.
  *Ready* means the issue has Context, Plan, Tasks and Done when filled in, so it can be picked up without
  further questions. Built-in Project workflows set statuses where they can (item added → Backlog, item
  closed or PR merged → Done) so that little is maintained by hand.
- **A pull request that finishes an issue says `Closes #N`.** Merging is squash by default; the PR title is
  the commit message on `master` (details in `AGENTS.md`).
- **Docs carry no status:** no checklists, no "done" markers. Progress is visible only in issues, the Project,
  milestones and merged pull requests. An ADR's status describes a decision, not progress.
- **`docs/domain/backlog.md` is legacy:** frozen — no new items, no ticking. Issues are created as work is
  taken up, not by migrating the file; if an item has an issue, the issue wins. The owner deletes the file
  when it stops being useful (git history keeps it).
- **No `spike` issue template.** Investigations are rare (UI framework, analytics), and the `feature`
  template already fits them.

## Alternatives considered

| Option | Why not |
|---|---|
| Keep the checklist in `backlog.md` | Goes stale, has no stage, cannot be linked from a PR, and a closed PR does not tick it |
| Issues and milestones only, no Project | Milestones say *which release*, not *which stage*; "ready to pick up" and "in progress" would need hand-kept labels. The Project costs nothing to remove later because it only sits on top of issues |
| A `Research` column in the Project | Research is a kind of work, not a stage — a research issue goes through the same Backlog → Done columns, so a label fits better |
| A `spike` issue template | Recurs too rarely to earn a template; `feature` plus the `research` label is enough |
| Migrate the whole backlog at once | Not every item is something the owner is convinced about, and sorting them all now is effort without a payoff; issues are created as items are taken up, so the tracker holds only things the owner stands behind |

## Consequences

- Good: one place for status; no document can show stale progress; every change traces from issue to PR to
  commit; "what can I pick up next" is the *Ready* column.
- Bad / accepted risks:
  - Reading the plan needs network access and the GitHub repository (`gh issue list`).
  - Statuses still need some tending where the built-in Project workflows do not cover a transition
    (e.g. Backlog → Ready is a deliberate decision).
  - Writing to issues and the Project is done by the owner; agents only propose ready-to-paste `gh` commands
    (see `AGENTS.md`).
- Follow-ups:
  - Create the GitHub Project and the labels `idea` and `research`.
  - The first issue is the UI spike from [ADR 0003](0003-ui-keyboard-first-htmx.md).
  - Delete `docs/domain/backlog.md` when the owner decides, and fix the links that point to it.
