# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Approval Matrix - build sheet head 16, rows 74-76.

Why this exists alongside ERPNext's Authorization Rule
------------------------------------------------------
Authorization Rule gates a transaction by value against an approving role or
user, which is the same shape as this doctype, and it was reviewed before this
one was built. It covers one of the four things head 16 asks for:

    by category (Item Group)   Authorization Rule does this
    by amount band             it has a single `value` threshold, not from/to
    by project                 it has no project field
    by approval level          it has no notion of a chain

and its `transaction` field is a fixed list of seven doctypes - Sales Order,
Purchase Order, Quotation, Delivery Note, Sales Invoice, Purchase Invoice,
Purchase Receipt - so it cannot gate BOQ, Work Certificate or even Material
Request, which is where the construction approvals actually sit.

So both exist. Authorization Rule remains live for the standard sales and
purchase transactions it natively enforces; this one carries the project and
package dimensions and the custom doctypes. If an approval behaves unexpectedly
on a Purchase Order, check both.
"""

from frappe.model.document import Document


class ApprovalMatrix(Document):
	pass
