# ERPNext Docs Skill

Read and search ERPNext documentation from local Markdown files at `/home/frappe/ERPNext Docs Markdown/`.

## Usage

```
/erpnext-docs [topic or keyword]
```

## Doc Files Index

| File          | Topic                                      |
| ------------- | ------------------------------------------ |
| ERPNext_1.md  | Introduction / Full Documentation Overview |
| ERPNext_2.md  | Accounting Overview                        |
| ERPNext_3.md  | Sales Invoice                              |
| ERPNext_4.md  | Journal Entry                              |
| ERPNext_5.md  | Shareholder Management                     |
| ERPNext_6.md  | Financial Report Template                  |
| ERPNext_7.md  | Accounts Settings                          |
| ERPNext_8.md  | Manage Foreign Exchange Difference         |
| ERPNext_9.md  | Advance In Separate Party Account          |
| ERPNext_10.md | Asset Management Overview                  |
| ERPNext_11.md | Customer Portal                            |
| ERPNext_12.md | Sales Order                                |
| ERPNext_13.md | Sales Person                               |
| ERPNext_14.md | Stock Module Introduction                  |
| ERPNext_15.md | Purchase Receipt                           |
| ERPNext_16.md | Stock Inspection / Quality Inspection      |
| ERPNext_17.md | Track Purchases In Accounts                |
| ERPNext_18.md | Point of Sale (POS)                        |
| ERPNext_19.md | Quality Action                             |
| ERPNext_20.md | Subcontracting                             |
| ERPNext_21.md | Project Overview                           |
| ERPNext_22.md | Time Tracking                              |
| ERPNext_23.md | Time Based Payout                          |
| ERPNext_24.md | Salary Slip from Timesheet                 |
| ERPNext_25.md | Quality Management Introduction            |
| ERPNext_26.md | CRM Introduction                           |
| ERPNext_27.md | DocType (Frappe Framework)                 |
| ERPNext_28.md | Custom Field                               |
| ERPNext_29.md | Printing                                   |
| ERPNext_30.md | Making Custom Reports                      |
| ERPNext_31.md | Workflows                                  |
| ERPNext_32.md | Plaid Integration                          |
| ERPNext_33.md | E-commerce Setup                           |
| ERPNext_34.md | Website Setup                              |

## Behavior

When invoked with a topic or keyword:

1. Identify which doc file(s) are most relevant using the index above
2. Use `grep` to search across all files if the topic is unclear:
   ```bash
   grep -il "<keyword>" "/home/frappe/ERPNext Docs Markdown/"*.md
   ```
3. Read the relevant file(s) with the Read tool
4. Extract and present the relevant sections clearly

When invoked without arguments:

- Show the index above and ask the user what topic they want to explore

## Tips

- Always search the docs first before answering ERPNext-related questions
- If multiple files seem relevant, read the most specific one first
- The docs path has a space: `/home/frappe/ERPNext Docs Markdown/` — always quote it in shell commands
