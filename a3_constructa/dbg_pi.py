import frappe
def run():
	wc = frappe.get_doc("Work Certificate", "WC-2026-0001"); print(wc.as_dict().get("items")[0])
	po = frappe.get_doc("Purchase Order", wc.subcontract_po)
	pi = frappe.new_doc("Purchase Invoice")
	pi.update({"supplier": wc.supplier, "company": po.company, "project": wc.project, "posting_date": frappe.utils.today()})
	pi.append("items", {"item_code": wc.items[0].item_code, "qty": 10, "rate": 7.5, "project": wc.project})
	pi.append("items", {"item_code": wc.items[0].item_code, "qty": 1, "rate": -20, "description": "Back-charge", "project": wc.project})
	pi.run_method("set_missing_values"); pi.items[1].rate = -20; pi.items[0].rate = 7.5
	pi.insert(ignore_permissions=True); pi.submit()
	print(pi.grand_total, [(i.qty, i.rate, i.amount, i.expense_account) for i in pi.items])
	frappe.db.rollback()
