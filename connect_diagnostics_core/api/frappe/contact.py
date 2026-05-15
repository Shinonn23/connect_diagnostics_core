import frappe
from frappe import _
from frappe.contacts.doctype.contact.contact import Contact
from frappe.model.naming import append_number_if_name_exists
from frappe.utils import cstr


def autoname(doc: Contact, method: str):
	doc.name = doc._get_full_name()

	# concat party name if reqd
	if doc.links:
		for link in doc.links:
			if link.link_name:
				if doc.name:
					doc.name = f"{doc.name}-{link.link_name.strip()}"
				else:
					doc.name = link.link_name.strip()
			break

	if not doc.name:
		frappe.throw(
			_(
				"Please provide a First Name, Last Name, Company Name, or a Linked Document to create a Contact."
			)
		)

	if frappe.db.exists("Contact", doc.name):
		doc.name = append_number_if_name_exists("Contact", doc.name)
