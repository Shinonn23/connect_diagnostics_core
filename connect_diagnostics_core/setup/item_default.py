"""Custom field / property setter definitions for Item Default."""

CUSTOM_FIELDS = {
    "Item Default": [
        {
            "fieldname": "column_break_deposit_account",
            "fieldtype": "Column Break",
            "insert_after": "sales_deposit_account",
            "is_system_generated": 1,
        },
        {
            "fieldname": "deposit_defaults",
            "label": "Deposit Defaults",
            "fieldtype": "Section Break",
            "insert_after": "deferred_revenue_account",
            "is_system_generated": 1,
        },
        {
            "fieldname": "purchase_deposit_account",
            "label": "Purchase Deposit Account",
            "fieldtype": "Link",
            "insert_after": "column_break_r6eft",
            "depends_on": "eval:parent.is_deposit_item",
            "is_system_generated": 1,
            "link_filters": '[["Account","root_type","=","Asset"]]',
            "options": "Account",
        },
        {
            "fieldname": "sales_deposit_account",
            "label": "Sales Deposit Account",
            "fieldtype": "Link",
            "insert_after": "deposit_defaults",
            "depends_on": "eval:parent.is_deposit_item",
            "is_system_generated": 1,
            "link_filters": '[["Account","root_type","=","Liability"]]',
            "options": "Account",
        },
    ],
}
