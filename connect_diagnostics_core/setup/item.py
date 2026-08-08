"""Custom field / property setter definitions for Item."""

CUSTOM_FIELDS = {
    "Item": [
        {
            "fieldname": "column_break_lhwzh",
            "fieldtype": "Column Break",
            "insert_after": "withholding_tax_type",
            "is_system_generated": 1,
        },
        {
            "fieldname": "height",
            "label": "Height",
            "fieldtype": "Float",
            "insert_after": "width",
        },
        {
            "fieldname": "alternative_names",
            "label": "Alternative Names",
            "fieldtype": "Table",
            "insert_after": "item_name",
            "options": "Item Alternative Name",
        },
        {
            "fieldname": "length",
            "label": "Length",
            "fieldtype": "Float",
            "insert_after": "height",
        },
        {
            "fieldname": "max_storage_days",
            "label": "Max Storage Days",
            "fieldtype": "Int",
            "insert_after": "min_remaining_shelf_life",
        },
        {
            "fieldname": "min_remaining_shelf_life",
            "label": "Min Remaining Shelf Life",
            "fieldtype": "Int",
            "insert_after": "shelf_life_in_days",
        },
        {
            "fieldname": "model",
            "label": "Model",
            "fieldtype": "Data",
            "insert_after": "stock_uom",
        },
        {
            "fieldname": "product_group",
            "label": "Product Group",
            "fieldtype": "Link",
            "insert_after": "item_group",
            "options": "Product Group",
        },
        {
            "fieldname": "regulation_class",
            "label": "Regulation Class",
            "fieldtype": "Link",
            "insert_after": "image",
            "options": "Regulation Class",
        },
        {
            "fieldname": "storage_condition",
            "label": "Storage Condition",
            "fieldtype": "Link",
            "insert_after": "valuation_method",
            "options": "Storage Condition",
        },
        {
            "fieldname": "width",
            "label": "Width",
            "fieldtype": "Float",
            "insert_after": "weight_per_unit",
        },
        {
            "fieldname": "is_deposit_item",
            "label": "Is Deposit Item",
            "fieldtype": "Check",
            "insert_after": "is_stock_item",
            "depends_on": "eval:!doc.is_stock_item",
            "is_system_generated": 1,
        },
        {
            "fieldname": "section_break_6buh1",
            "label": "Thai Tax",
            "fieldtype": "Section Break",
            "insert_after": "item_tax_section_break",
            "is_system_generated": 1,
        },
        {
            "fieldname": "withholding_tax_type",
            "label": "Withholding Tax Type (Customer)",
            "fieldtype": "Link",
            "insert_after": "section_break_6buh1",
            "description": "Select withholding tax type for service amount withheld when recevice from customer.",
            "is_system_generated": 1,
            "options": "Withholding Tax Type",
        },
        {
            "fieldname": "withholding_tax_type_pay_individual",
            "label": "Withholding Tax Type (Individual)",
            "fieldtype": "Link",
            "insert_after": "withholding_tax_type_pay_supplier",
            "description": "Select withholding tax type for service amount to be withheld when pay to individual.",
            "is_system_generated": 1,
            "options": "Withholding Tax Type",
        },
        {
            "fieldname": "withholding_tax_type_pay_supplier",
            "label": "Withholding Tax Type (Supplier)",
            "fieldtype": "Link",
            "insert_after": "column_break_lhwzh",
            "description": "Select withholding tax type for service amount to be withheld when pay to supplier.",
            "is_system_generated": 1,
            "options": "Withholding Tax Type",
        },
    ],
}

# (fieldname or None for DocType-level, property, value, property_type)
PROPERTY_SETTERS = {
    "Item": [
        ("barcodes", "hidden", "0", "Check"),
        ("item_code", "hidden", "0", "Check"),
        ("item_code", "reqd", "1", "Check"),
    ],
}
