# Print Format JSON fixtures

Each app-owned Print Format is self-contained in its `<format>/<format>.json`
fixture. Keep the complete Jinja template in `html` and all layout CSS in
`css`. Do not create companion `.html` or `.css` files, import a shared Print
Format stylesheet, or depend on an external component template.

## Editing

- Edit the JSON fixture directly and keep it valid JSON.
- Update the top-level `modified` value whenever `html` or `css` changes. Use
  the current Frappe system time with microseconds.
- Keep document-specific Jinja macros inside that Print Format's `html` field.
- Keep every CSS selector scoped under the format's root class and retain the
  minimal `.print-format`/`@page` rules required by Frappe.
- CSS is not rendered through Jinja. Never place `{{ ... }}` in `css`.
- Read optional action data defensively, for example
  `print_actions.get("received", {}).get("name", "")`.

## Pagination

- Use complete page groups from `get_print_item_pages`.
- Reserve the exact table, summary, and footer height in both the pagination
  call and CSS geometry.
- Move a whole row to the next page when it does not fit. Never clip it under
  totals or a footer.
- Keep normal totals visible; do not replace them with a redundant “Continued
  on next page” message.

## Apply and verify

1. Run `bench --site <site> migrate` to import the JSON fixtures.
2. Test the real Desk Print Preview and the PDF route with identical settings.
3. Render through Frappe's configured Chrome/Chromium PDF generator.
4. Verify one item, exact page capacity, one item over capacity, long Thai
   descriptions, missing action data, totals, signatures, and every copy.
