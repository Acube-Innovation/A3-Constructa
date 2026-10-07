# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""P-06F: daily site reports on the Administrative Centre.

Filed by the site engineer, Patrick Lokwa:
- two days ago, rain: the blockwork gang and the labour pool lost the first two
  hours; the mixer stood idle three; 30 m² of blockwork, 18 bags of cement; the
  tiling subcontractor's three tilers inside;
- yesterday, sunny: the blockwork gang worked two hours' overtime to catch up
  after the blocks arrived late; 46 m² of blockwork, 25 bags; the client's
  engineer walked level 1 (with a photo);
- today: a draft, waiting for the evening meter reading.

Each submitted report has booked its timesheets (one per worker), the mixer's
equipment log, the blockwork measurement and a material issue note.
"""

import io

import frappe
from frappe.utils import add_days, today

from a3_constructa.demo.masiha.common import COMPANY, as_user, at, comment, insert, log, project

MIXER_ITEM = "EQ-MIX-350"
TILER = "Equateur Tiling Works SARL"


def run():
	p = project()
	if frappe.db.exists("Daily Site Report", {"project": p}):
		log("site reports already present")
		return
	mixer = make_mixer(p)
	task = lambda s: frappe.db.get_value("Task", {"project": p, "subject": s})  # noqa: E731
	blockwork, frame = task("Blockwork"), task("Concrete frame")
	crew = lambda n: frappe.db.get_value("Crew", {"crew_name": n}, "name")  # noqa: E731
	gang, pool = crew("Blockwork gang"), crew("General labour pool")
	days = [
		dict(offset=-2, weather="Rain", temperature_c=24, submit=True,
		     labour=[{"crew": gang, "task": blockwork, "hours": 6}, {"crew": pool, "task": frame, "hours": 6}],
		     subcontractors=[{"supplier": TILER, "trade": "Tiling", "headcount": 3, "hours": 6}],
		     equipment=[{"asset": mixer, "task": blockwork, "meter_end": 416, "worked_hours": 4, "idle_hours": 3}],
		     progress=[{"task": blockwork, "qty_done": 30}],
		     materials=[{"item_code": "CEM-425-50", "qty": 18, "wbs": "MSS-W-AR", "cost_code": "MSS-CC-STR-M"}],
		     delays=[{"cause": "Weather", "hours_lost": 2, "description": "Heavy rain 07:00-09:00: no blockwork outside, mixer stood."}]),
		dict(offset=-1, weather="Sunny", temperature_c=31, submit=True,
		     labour=[{"crew": gang, "task": blockwork, "hours": 8, "overtime_hours": 2}, {"crew": pool, "task": frame, "hours": 8}],
		     subcontractors=[{"supplier": TILER, "trade": "Tiling", "headcount": 3, "hours": 8}],
		     equipment=[{"asset": mixer, "task": blockwork, "meter_end": 424, "worked_hours": 8}],
		     progress=[{"task": blockwork, "qty_done": 46}],
		     materials=[{"item_code": "CEM-425-50", "qty": 25, "wbs": "MSS-W-AR", "cost_code": "MSS-CC-STR-M"}],
		     delays=[{"cause": "Material", "hours_lost": 1.5, "description": "Block delivery arrived at 10:30 instead of 07:00; the gang stayed on to 17:00."}],
		     visitors="Ir. Jean Bolamba, the client's engineer: walked the level 1 blockwork; asked for the lintel schedule by Friday.",
		     photo="Level 1 blockwork, grid C-D, after the client's walk-round"),
		dict(offset=0, weather="Cloudy", temperature_c=28, submit=False,
		     labour=[{"crew": gang, "task": blockwork, "hours": 8}, {"crew": pool, "task": frame, "hours": 8}],
		     equipment=[{"asset": mixer, "task": blockwork, "worked_hours": 7}]),
	]
	made = []
	with as_user("requester"):
		for d in days:
			photo = d.pop("photo", None)
			offset, submit = d.pop("offset"), d.pop("submit")
			doc = frappe.get_doc({"doctype": "Daily Site Report", "project": p, "report_date": add_days(today(), offset), **d})
			doc.flags.ignore_permissions = True
			doc.insert()
			if photo:
				doc.append("photos", {"image": site_photo(doc.name), "caption": photo})
				doc.save()
			if submit:
				doc.submit()
			for field in ("creation", "modified"):
				frappe.db.set_value("Daily Site Report", doc.name, field, at(offset, 17, 30), update_modified=False)
			made.append(f"{doc.name} ({'submitted' if submit else 'draft'})")
	comment("Daily Site Report", frappe.db.get_value("Daily Site Report", {"project": p, "report_date": add_days(today(), -1)}),
	        "Overtime approved: the gang made up the morning lost to the late delivery.", "pm", at(-1, 18))
	log("Site reports: " + ", ".join(made))


def make_mixer(p):
	name = frappe.db.get_value("Asset", {"item_code": MIXER_ITEM, "project": p}, "name")
	if name:
		return name
	if not frappe.db.exists("Item", MIXER_ITEM):
		insert({"doctype": "Item", "item_code": MIXER_ITEM, "item_name": "Concrete mixer 350 L", "item_group": "Heavy Equipment Items",
		        "stock_uom": "Nos", "is_stock_item": 0, "is_fixed_asset": 1, "asset_category": "Small Machinery",
		        "include_item_in_manufacturing": 0})
	with as_user("pm"):
		a = frappe.get_doc({"doctype": "Asset", "asset_name": "Concrete mixer 350 L (hired)", "item_code": MIXER_ITEM, "company": COMPANY,
		                    "asset_category": "Small Machinery", "location": frappe.db.get_value("Project", p, "location"), "is_existing_asset": 1,
		                    "available_for_use_date": add_days(today(), -45), "purchase_date": add_days(today(), -45),
		                    "calculate_depreciation": 0, "gross_purchase_amount": 6_500, "is_hired": 1, "meter_type": "Hours",
		                    "current_meter": 412, "project": p, "wbs": "MSS-W-AR", "make": "Altrad Belle", "model": "Premier 350"})
		a.flags.ignore_permissions = True
		a.insert()
	comment("Asset", a.name, "Hired by the month for the blockwork mortar. Hours read off its meter.", "pm", at(-45, 9))
	return a.name


def site_photo(report):
	"""A drawn stand-in for the engineer's phone photo: a block wall going up."""
	from PIL import Image, ImageDraw

	img = Image.new("RGB", (960, 640), (176, 206, 230))
	d = ImageDraw.Draw(img)
	d.rectangle([0, 470, 960, 640], fill=(150, 122, 92))
	for row in range(9):
		y = 470 - (row + 1) * 40
		shift = 0 if row % 2 else 60
		for x in range(-60 + shift, 900, 120):
			d.rectangle([x + 2, y + 2, x + 118, y + 38], fill=(196, 196, 188), outline=(140, 140, 132))
	d.rectangle([380, 230, 520, 470], fill=(176, 206, 230))  # a door opening
	d.rectangle([370, 210, 530, 230], fill=(120, 120, 120))  # its lintel
	buf = io.BytesIO()
	img.save(buf, format="JPEG", quality=82)
	f = frappe.get_doc({"doctype": "File", "file_name": "level-1-blockwork.jpg", "attached_to_doctype": "Daily Site Report",
	                    "attached_to_name": report, "attached_to_field": "photos", "is_private": 0, "content": buf.getvalue()})
	f.flags.ignore_permissions = True
	f.insert()
	return f.file_url
