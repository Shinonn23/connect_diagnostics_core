---
name: workspace-navigation
description: Plan and implement Desk navigation for a new Connect Diagnostics Module, DocType, or Report. Use when adding or changing a user-facing Frappe Workspace card or Workspace Sidebar item.
---

# Workspace Navigation Skill

Plan and implement Desk navigation for a new Connect Diagnostics Module, DocType,
or Report.

## Usage

```
$workspace-navigation <Module, DocType, or feature>
```

## Discovery

1. Classify the feature before changing navigation:
   - An extension of an existing ERPNext domain, such as Stock, Accounting,
     Selling, Buying, or Settings.
   - An independent, major Connect Diagnostics domain, such as Loan.
   - A child-table or technical DocType with no standalone Desk route.
2. Search `connect_diagnostics_core/setup/workspace.py` for existing Workspace
   cards, Sidebar placements, and the established save pattern.
3. Inspect the target standard Workspace Sidebar in installed ERPNext source and
   the target site. Confirm each section and anchor link exists before relying on it.
4. Search hooks, patches, API callers, client scripts, templates, and jobs for
   the feature so navigation does not duplicate an existing entry point.

Read [`references/desktop-icons.md`](references/desktop-icons.md) when the change adds,
regroups, or edits a Desk Desktop Icon.

## Placement Rules

- For an existing ERPNext domain, retain the Connect Diagnostics Workspace card
  and add the user-facing item to the relevant existing Workspace Sidebar section.
  Place important operational items in the primary navigation; place setup masters
  in Setup and reports in Reports or their contextual report section.
- Do not create a separate `Connect Diagnostics` Sidebar group for a feature that
  belongs in an existing ERPNext domain.
- For an independent, major domain, create a Connect Diagnostics Module and its
  own Workspace, then give its user-facing items intentional card and Sidebar
  navigation there.
- Use the standard ERPNext Workspace information architecture for every
  independent Workspace: start with Home, follow with the important operational
  DocTypes, then provide collapsible Reports and Setup sections, followed by
  Settings. This is a content and ordering requirement for the Workspace cards
  and Sidebar, not a requirement to copy a particular ERPNext module's files or
  business labels.
- Add a standard top-level Desktop Icon linked to the Workspace Sidebar so the
  independent module is visible in the Desk module grid.
- Ship app-owned Desktop Icons as `connect_diagnostics_core/desktop_icon/<scrub(label)>.json`
  with matching `public/icons/desktop_icons/{subtle,solid}/<scrub(label)>.svg` artwork.
  Never create them in setup code: migrate's orphan cleanup deletes any standard icon
  this app has no file for. Use an `icon_type: "Folder"` icon, with children carrying
  `parent_icon`, when two or more workspaces belong to one Desk group; a folder with
  no visible children is not rendered at all.
- Child-table and technical DocTypes with no standalone Desk route do not receive
  navigation. State the reason in the change proposal and PR.
- Do not modify ERPNext Workspace, Workspace Sidebar, or Desktop Icon source files.
  Keep site customization idempotent in the app's setup code, and save a document owned
  by another app through `_save_without_export` so the change is not written back into
  that app's source.

## Implementation and Verification

1. Propose every changed file, the intended Module/Workspace placement, and what
   will not change. Wait for explicit approval before changing more than one file.
2. Reuse and extend `connect_diagnostics_core/setup/workspace.py` when it exists.
   For the first navigation change, create that idempotent setup module and its
   required setup entry point only after the approved scope includes both files.
3. Add focused tests for placement, ordering, idempotency, and preservation of
   existing Workspace cards and links.
4. Run migration on the target site. Confirm the actual Sidebar order is Home,
   important DocTypes, Reports, Setup, and Settings; a module-grid icon alone is
   not sufficient. Confirm managed links resolve, no stale links remain, cards
   still render, and the Sidebar contains no duplicates.
5. Run the repository's required pre-commit checks and final review. Verify the
   expected user roles can see and open each user-facing entry after deployment.
