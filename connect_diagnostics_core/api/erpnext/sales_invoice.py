from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice
from pythainlp.util import bahttext


class CustomSalesInvoice(SalesInvoice):
    custom_in_words_thai: str | None


def before_save(doc: CustomSalesInvoice, method):
    if doc.custom_in_words_thai:
        doc.custom_in_words_thai = bahttext(doc.rounded_total)
