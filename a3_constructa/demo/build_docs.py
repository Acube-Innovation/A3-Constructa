# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Turn docs/how_it_works.html into the client-facing PDF.

    bench --site <site> execute a3_constructa.demo.build_docs.build_pdf

The HTML is the source and the PDF is the deliverable, so the PDF is rebuilt
from it rather than edited. Rendering goes through wkhtmltopdf, which ships with
the bench image and is what Frappe uses for print formats.
"""

import os

import frappe

SOURCE = "docs/how_it_works.html"
OUTPUT = "docs/A3-Constructa-How-It-Works.pdf"

# wkhtmltopdf takes its page setup from arguments, not from @page rules, so the
# margins here have to match the ones in the stylesheet.
PDF_OPTIONS = {
	"page-size": "A4",
	"margin-top": "16mm",
	"margin-bottom": "18mm",
	"margin-left": "14mm",
	"margin-right": "14mm",
	"encoding": "UTF-8",
	"enable-local-file-access": None,
	"footer-font-size": "7",
	"footer-font-name": "Helvetica",
	"footer-left": "A3 Constructa - How the system works",
	"footer-right": "Page [page] of [topage]",
	"footer-spacing": "8",
}


def build_pdf(source: str | None = None, output: str | None = None) -> str:
	"""Render the guide and return the path it was written to."""
	from frappe.utils.pdf import get_pdf

	app_root = os.path.dirname(frappe.get_app_path("a3_constructa"))
	source_path = os.path.join(app_root, source or SOURCE)
	output_path = os.path.join(app_root, output or OUTPUT)

	if not os.path.exists(source_path):
		frappe.throw("Source not found: %s" % source_path)

	with open(source_path, encoding="utf-8") as handle:
		html = handle.read()

	pdf = get_pdf(html, options=dict(PDF_OPTIONS))

	os.makedirs(os.path.dirname(output_path), exist_ok=True)
	with open(output_path, "wb") as handle:
		handle.write(pdf)

	print("Wrote %s (%.0f KB)" % (output_path, len(pdf) / 1024.0))
	return output_path
