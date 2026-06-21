"""Custom field / property setter definitions for Contact."""

CUSTOM_FIELDS = {
    'Contact': [
        {
            'fieldname': 'other_contacts',
            'label': 'Other Contacts',
            'fieldtype': 'Small Text',
            'insert_after': 'phone_nos',
            'translatable': 1,
        },
        {
            'fieldname': 'is_billing_contact',
            'label': 'Is Billing Contact',
            'fieldtype': 'Check',
            'insert_after': 'is_primary_contact',
        },
    ],
}
