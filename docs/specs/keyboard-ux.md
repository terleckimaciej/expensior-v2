# Keyboard UX spec (draft)

> **Stale as of 2026-09-12.** Keyboard-first was dropped as a hard goal in
> [ADR 0003](../decisions/0003-ui-keyboard-first-htmx.md): delivering it meant hand-writing a frontend,
> which is not a trade worth making here. Kept because it is a good record of the intent — if the chosen
> UI framework makes keyboard control cheap, start from this document rather than from a blank page.

Goal: everything doable without a mouse, Vim-flavoured, with view switching like Pop!_OS workspaces.
The mouse still works; the keyboard is the primary path.

## Principles

1. **Discoverable:** `?` shows all bindings for the current view; `:` opens a command palette listing every action.
2. **Modal only where needed:** Normal mode by default. Typing in an input switches to Insert; `Esc` always returns to Normal.
3. **One selection model everywhere:** a cursor row + an optional multi-selection.
4. **No browser conflicts:** avoid `Ctrl`/`Super` combos the browser or OS owns. `Super+N` is taken by the
   desktop, so views use bare digits (and `g`-prefixed mnemonics).

## Global

| Key | Action |
|---|---|
| `1`–`5` | Switch view: 1 Dashboard, 2 Transactions, 3 Rules, 4 Categories, 5 Imports |
| `g d` / `g t` / `g r` / `g c` / `g i` | Same as above, mnemonic |
| `:` | Command palette (fuzzy search over actions and views) |
| `/` | Search / filter in the current view |
| `?` | Keybinding help overlay |
| `Esc` | Close overlay, clear search, leave Insert mode |
| `[` / `]` | Previous / next period (month) on views with a period filter |

## Lists (Transactions, Rules, Categories, Imports)

| Key | Action |
|---|---|
| `j` / `k` | Cursor down / up |
| `g g` / `G` | First / last row |
| `Ctrl-d` / `Ctrl-u` | Half page down / up |
| `Enter` | Open detail of cursor row |
| `x` | Toggle selection of cursor row |
| `V` | Visual mode: extend selection with `j`/`k` |
| `e` | Edit field / classification of cursor row (or of the selection) |
| `c` | Set category (opens a fuzzy category picker) |
| `a` | Add new item |
| `d d` | Delete (confirm with `y`) |
| `u` | Undo last change (where supported) |

## Categories view

| Key | Action |
|---|---|
| `h` / `l` | Collapse / expand node |
| `>` / `<` | Indent (make child) / outdent |

## Open questions

- Command palette: build our own or use a tiny library?
- Does bulk edit happen in a modal or inline?
- Should Vim-style count prefixes (`5j`) be supported?
