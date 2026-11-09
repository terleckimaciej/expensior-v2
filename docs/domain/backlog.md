# Feature backlog

> **Legacy — frozen.** No new items and no ticking: open work lives in GitHub issues
> ([ADR 0008](../decisions/0008-open-work-in-github-issues.md)). If an item here has an issue, the issue wins.
> This file is kept as a source of ideas until the owner deletes it.

Collected from `../expensior/expensior notatki.txt` and the v2 planning discussion. Unordered within sections.

## MVP

- [ ] Import PKO BP CSV (dry-run, conflict policy, import batch audit, undo a batch)
- [ ] Category tree management (view as tree, add/rename/move)
- [ ] Rules management (CRUD, regex validated on save, stats: how many transactions each rule classified)
- [ ] Run classification on unclassified transactions
- [ ] Transactions table: filter by any column and date range, manual (re)classification, **bulk edit of a selection**
- [ ] Dashboard: period filter (month/week/custom); tiles for income, expenses, net, transaction count;
      monthly cashflow line (expenses, income, savings); spend by category; spend by subcategory grouped by category colour

## Next

- [ ] Refunds and reimbursements: label and net them out (e.g. rent paid in full, flatmates transfer their share back)
- [ ] Category totals including related inflows (rent − reimbursements)
- [ ] Export any table to CSV; full DB export/backup
- [ ] Merchant dimension (category → subcategory → merchant)

## Later / learning

- [ ] Datastream → BigQuery analytics (ADR 0004)
- [ ] Terminal client (Textual) on top of `/api`
- [ ] Keyboard navigation (see [`../specs/keyboard-ux.md`](../specs/keyboard-ux.md)) — wanted, but dropped
      from MVP because building it meant writing a frontend by hand (ADR 0003). Revisit if the chosen
      framework makes it cheap
- [ ] Suggest rules from manually classified transactions
