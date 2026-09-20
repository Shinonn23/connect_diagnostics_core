# Desk home icons (Frappe v16)

How `/app/desktop` is built, and what this app owns. Verified against Frappe 16.31.0 and
ERPNext 16.32.1 while adding the Inventory folder.

## Model

`Desktop Icon` — `frappe/desk/doctype/desktop_icon/`

- `autoname: field:label`, so `name == label`, and the label is globally unique across all
  icon types.
- `icon_type` is `Link | Folder | App`; `link_type` is `Workspace Sidebar | External`.
- `parent_icon` links to another Desktop Icon. There are exactly two levels: a child cannot
  have children.
- `link_to` points to a Workspace Sidebar title, not a Workspace. A Workspace Sidebar does
  not require a matching Workspace.

## Where icons live

App-level, not module-level: `<app>/desktop_icon/<frappe.scrub(label)>.json`. Frappe imports
these folders on every migrate (`desktop_icon`, `workspace_sidebar`, and `sidebar_item_group`).
This app owns `connect_diagnostics_core/desktop_icon/{regulatory,inventory,stock_counting}.json`.

Never create a standard icon in setup code. `frappe/model/sync.py` removes a standard Desktop
Icon whose owning app has no matching file before `after_migrate` hooks run.

## Rendering

- `prepare()` drops hidden icons and promotes children whose parent is hidden or missing.
- `validate_icon()` does not render a Folder with zero visible children.
- The grid sorts by `idx`, then `label`.
- `sync_layout()` means a per-user Desktop Layout overrides `boot.desktop_icons` entirely;
  users with a customized Desk may need to reset to default before shipped changes appear.

## Artwork

Artwork lives at `assets/<icon.app>/icons/desktop_icons/<subtle|solid>/<scrub(label)>.svg`
and falls back to a grey letter tile. The lookup uses the icon's `app`, so artwork must live
in the owning app. `desktop_icon.html` skips artwork for Folders and renders a thumbnail grid.

Use the shared 54×54 rounded-tile style: subtle icons use `fill="#7B808A" fill-opacity="0.19"`
with `#6B6F78` strokes; solid icons use `fill="#7B808A"` with white strokes and
`stroke-width="3"`.

## Server-side permission filter

`get_desktop_icons(user, bootinfo)` applies these rules:

- Folders are always permitted.
- Apps use `check_app_permission`.
- Links are permitted only when `bootinfo.workspace_sidebar_item[label.lower()]` exists and
  has items, so the icon label must equal the Workspace Sidebar title.
- The final filter drops icons whose parent is not a permitted top-level label. A dangling
  `parent_icon` therefore hides the icon completely; this app falls back to `ERPNext` when
  choosing the Stock desktop-icon parent.

## Editing an icon owned by another app

`DesktopIcon.on_update` → `export_desktop_icon()` writes the record back to
`<app>/desktop_icon/<label>.json` when the record is standard, has an app, is not being
imported, and developer mode is enabled. Save through `setup/workspace.py::_save_without_export`
(`in_import=True` around `save()`) so the ERPNext source tree is not dirtied.

ERPNext re-imports its own file whenever its hash changes, resetting `parent_icon`; regrouping
must therefore be re-applied idempotently from `after_migrate` (`ensure_desktop_icons`).

## Known wart

`_ensure_stock_count_sidebar()` creates the `Stock Counting` Workspace Sidebar with
`standard=1, app="connect_diagnostics_core"` but ships no
`workspace_sidebar/stock_counting.json`. Each migrate logs deletion during orphan cleanup and
`after_migrate` recreates it, discarding user customization. Regulatory avoids this by shipping
the JSON file. This is a known issue, not part of navigation changes unless explicitly scoped.

Related: the repository's current Regulatory documentation and the parent `SKILL.md`.
