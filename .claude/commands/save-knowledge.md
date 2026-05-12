Save codebase knowledge discovered during the current task to `.claude/knowledge/` for future reference.

## Steps

1. **Determine topic** — derive from the current task context (e.g., "employee-autoname", "product-registration-hooks"). If ambiguous, ask the user for a topic name (lowercase, hyphen-separated, no spaces).

2. **Check for existing file** — read `.claude/knowledge/<topic>.md` if it exists; append or update rather than overwrite unrelated sections.

3. **Compile findings** — from the current session, collect:
   - **Key files**: paths and their role (one line each)
   - **Entry points**: hooks registered in `hooks.py`, whitelisted methods, doc_events
   - **Patterns discovered**: naming conventions, data flow, business rules, Thai-specific logic
   - **Non-obvious constraints**: immutability rules, race conditions, backward-compat limitations
   - **What was NOT found**: searches that returned nothing (to avoid repeating them in future)

4. **Write the file** — create or update `.claude/knowledge/<topic>.md` with this structure:

   ```markdown
   # Knowledge: <Topic Title>

   _Last updated: <today's date>_

   ## Key Files
   - `path/to/file.py` — purpose in one line

   ## Entry Points
   - Hook: `doc_events["DocType"]["event"]` → `module.function`
   - Whitelisted: `@frappe.whitelist()` at `path/to/api.py:line`

   ## Patterns & Business Rules
   - <bullet per pattern>

   ## Constraints
   - <bullet per non-obvious constraint>

   ## Dead Ends (searches that found nothing)
   - <what you searched for and where>
   ```

5. **Confirm** — report the file path written and a one-line summary of what was saved. Do not display the full file contents unless asked.

## Do NOT
- Save obvious facts derivable from the directory structure alone
- Include code snippets longer than 3 lines — link to the file:line instead
- Create files for trivial tasks (single-line changes, typo fixes)
