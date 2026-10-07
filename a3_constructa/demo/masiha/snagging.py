# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""P-06H: snagging, handover and the defects liability period.

Bikoro primary school (handed over): the classroom block was snagged a week
before practical completion and every snag verified; practical completion was
issued on the award's date, with two months' defects liability (now ended). In
the DLP the school reported a leaking window (fixed) and a wobbling ceiling fan
(in hand). Four pails of paint are left in the Bikoro site store - End of DLP
lists them for return.

Administrative Centre: the finished ground-floor zones of block A have been
snagged - seven items, two verified, two fixed and waiting for the check, three
open (one overdue). Practical completion is refused while they're outstanding.
"""

import io

import frappe
from frappe.utils import add_days, add_months, getdate, today

from a3_constructa.demo.masiha.common import COMPANY, as_user, at, comment, insert, log, project, wh

BIKORO = "Bikoro primary school refurbishment"
BIKORO_STORE = "Bikoro Site Store"
# description, trade, location, responsible type, responsible, due (days from inspection), status
BIKORO_SNAGS = [
	("Paint runs on the corridor wall", "Painting", "Corridor, east wall", "Supplier", "Mbandaka Peinture et Finitions SARL", 3, "Verified"),
	("Cracked pane, classroom 2 window W3", "Glazing", "Classroom 2, W3", "Supplier", "Kinshasa Building Supplies SARL", 5, "Verified"),
	("Classroom 4 door does not latch", "Carpentry", "Classroom 4 door", "Crew", "General labour pool", 3, "Verified"),
	("Light switch loose, staff room", "Electrical", "Staff room, by the door", "Crew", "Electricians", 2, "Verified"),
	("Hand-basin tap drips, toilet block", "Plumbing", "Toilet block, basin 2", "Crew", "Plumbers", 2, "Verified"),
	("Rubble behind the classroom block", "Cleaning", "North side", "Crew", "General labour pool", 1, "Verified"),
]
ADMIN_SNAGS = [
	("Chipped tile edge at the doorway", "Tiling", "Office G04, door", "Crew", "Tiling gang A", 4, "Open", True),
	("Grout missing along the skirting", "Tiling", "Corridor, east wall", "Crew", "Tiling gang A", 3, "Fixed", False),
	("Lippage over 1 mm at the lift lobby", "Tiling", "Lift lobby", "Supplier", "Equateur Tiling Works SARL", 2, "Verified", False),
	("Paint splashes on the new floor tiles", "Painting", "Office G02", "Supplier", "Mbandaka Peinture et Finitions SARL", 2, "Open", False),
	("Socket cover missing", "Electrical", "Office G03, north wall", "Crew", "Electricians", 3, "Fixed", False),
	("Door G05 binds on the frame", "Carpentry", "Office G05", "Crew", "General labour pool", 6, "Open", False),
	("Mortar droppings in the corridor", "Cleaning", "Corridor", "Crew", "General labour pool", 1, "Verified", False),
]


def run():
	bikoro = frappe.db.get_value("Project", {"project_name": BIKORO, "company": COMPANY}, "name")
	if frappe.db.exists("Snag List", {"project": bikoro}):
		log("snag lists already present")
		return
	pc = getdate(frappe.db.get_value("Awarded Quotation", {"project": bikoro}, "practical_completion_date"))
	months = int(frappe.db.get_value("Awarded Quotation", {"project": bikoro}, "defects_liability_months") or 0)
	b = snag_list(bikoro, "BKS-W", add_days(pc, -8), "Classroom block", "Ground floor", "All rooms", BIKORO_SNAGS, verified_on=add_days(pc, -2))
	frappe.db.set_value("Project", bikoro, {"practical_completion_date": pc, "dlp_end_date": add_months(pc, months)}, update_modified=False)
	comment("Project", bikoro, f"Practical completion issued for {frappe.format(pc, {'fieldtype': 'Date'})}; defects liability period to "
	        f"{frappe.format(add_months(pc, months), {'fieldtype': 'Date'})}.", "pm", get_dt(pc, 16))
	claims(bikoro, pc)
	store(bikoro, pc)
	a = snag_list(project(), "MSS-W-FL-A", add_days(today(), -3), "Block A", "Ground floor", "Zones 1-3: corridor and offices G01-G05",
	              ADMIN_SNAGS)
	log(f"Handover: Bikoro {b} all verified, practical completion {pc}, 2 warranty claims, surplus in {wh(BIKORO_STORE)}; "
	    f"Administrative Centre {a}: 3 open, 2 fixed, 2 verified")


def get_dt(d, hour):
	return frappe.utils.get_datetime(f"{d} {hour:02d}:00:00")


def snag_list(p, wbs, when, building, floor, room, snags, verified_on=None):
	when = getdate(when)
	inspector = frappe.db.get_value("Employee", {"user_id": "patrick.lokwa@masiha.demo"})
	with as_user("requester"):
		doc = frappe.get_doc({"doctype": "Snag List", "project": p, "wbs": wbs, "inspection_date": when, "inspected_by": inspector,
		                      "building": building, "floor": floor, "room": room, "items": []})
		for desc, trade, where, rtype, who, due, status, *photo in snags:
			resp = frappe.db.get_value("Crew", {"crew_name": who}, "name") if rtype == "Crew" else who
			doc.append("items", {"description": desc, "trade": trade, "location_detail": where, "responsible_type": rtype, "responsible": resp,
			                     "due_date": add_days(when, due), "status": status})
		doc.flags.ignore_permissions = True
		doc.insert()
		for row, (*_, photo) in zip(doc.items, [s if len(s) == 8 else (*s, False) for s in snags]):
			if photo:
				row.photo = chipped_tile(doc.name)
		if verified_on:
			for row in doc.items:
				row.closed_on = verified_on
		doc.save()
	frappe.db.set_value("Snag List", doc.name, "creation", get_dt(when, 15), update_modified=False)
	return doc.name


def claims(p, pc):
	customer = frappe.db.get_value("Project", p, "customer")
	with as_user("pm"):
		for offset, text, status, resolution in (
			(20, "Classroom 3 window leaks at the sill in heavy rain.", "Closed",
			 "Sill re-sealed and the weep holes cleared; checked in the next storm."),
			(50, "Ceiling fan in classroom 1 wobbles at full speed.", "Work In Progress", None),
		):
			wc = frappe.get_doc({"doctype": "Warranty Claim", "company": COMPANY, "customer": customer, "project": p, "wbs": "BKS-W",
			                     "complaint_date": add_days(pc, offset), "complaint": text, "status": status,
			                     "complaint_raised_by": "Head teacher, Bikoro primary school",
			                     "resolution_date": get_dt(add_days(pc, offset + 6), 14) if resolution else None,
			                     "resolution_details": resolution})
			wc.flags.ignore_permissions = True
			wc.insert()
			frappe.db.set_value("Warranty Claim", wc.name, "creation", get_dt(add_days(pc, offset), 10), update_modified=False)


def store(p, pc):
	if not frappe.db.exists("Warehouse", wh(BIKORO_STORE)):
		parent = frappe.db.get_value("Warehouse", {"company": COMPANY, "is_group": 1}, "name")
		insert({"doctype": "Warehouse", "warehouse_name": BIKORO_STORE, "company": COMPANY, "parent_warehouse": parent,
		        "warehouse_type": "Site", "project": p})
	insert({"doctype": "Stock Entry", "company": COMPANY, "stock_entry_type": "Material Transfer", "purpose": "Material Transfer",
	        "posting_date": add_days(pc, -20), "set_posting_time": 1, "project": p,
	        "remarks": "Finishing materials sent to Bikoro; what was left stayed in the site store.",
	        "items": [{"item_code": "PNT-EMU-20", "qty": 4, "s_warehouse": wh("Central Store Kinshasa"), "t_warehouse": wh(BIKORO_STORE), "project": p}]},
	       submit=True)


def chipped_tile(snag_list):
	from PIL import Image, ImageDraw

	img = Image.new("RGB", (800, 600), (222, 218, 210))
	d = ImageDraw.Draw(img)
	for x in range(0, 800, 200):
		for y in range(0, 600, 200):
			d.rectangle([x + 3, y + 3, x + 197, y + 197], fill=(206, 200, 190), outline=(160, 155, 148), width=3)
	d.polygon([(397, 200), (440, 200), (420, 236), (397, 222)], fill=(120, 110, 100))  # the chip
	d.rectangle([0, 0, 120, 600], fill=(120, 84, 52))  # door frame
	buf = io.BytesIO()
	img.save(buf, format="JPEG", quality=82)
	f = frappe.get_doc({"doctype": "File", "file_name": "g04-chipped-tile.jpg", "attached_to_doctype": "Snag List", "attached_to_name": snag_list,
	                    "is_private": 0, "content": buf.getvalue()})
	f.flags.ignore_permissions = True
	f.insert()
	return f.file_url
