# -*- coding: utf-8 -*-
{
    "name": "Client Letter Generator - CRM, Quotation, Invoice & Project",
    "summary": "Generate client letters from CRM, quotations, estimations, invoices and projects. Print PDF, email or WhatsApp in one click.",
    "description": """
Client Letter Generator
=======================
One "Send Client Letter" button on CRM opportunities, quotations, estimations,
customer invoices and projects. Pick a letter type, the client, reference
numbers, amounts and scope are filled from the source document, and the
letter can be printed as PDF, emailed, shared on WhatsApp or saved as a
tracked letter record. Ships with 11 ready letter templates and lets users
save their own.
    """,
    "version": "14.0.1.0.0",
    "category": "Sales/CRM",
    "author": "Saaskul",
    "website": "https://saaskul.com",
    "live_test_url": "https://saaskul.com/contactus?name=Live%20Preview%20-%20Client%20Letter%20Generator",
    "support": "info.cpabooks@gmail.com",
    "license": "OPL-1",
    "price": 19.00,
    "currency": "USD",
    "images": [
        "static/description/banner.png",
    ],
    "depends": [
        "crm",
        "sale_management",
        "account",
        "project",
        "mail",
        "cost_estimate_customer_ld",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/client_letter_sequence.xml",
        "data/client_letter_template_data.xml",
        "views/client_letter_document_views.xml",
        "views/client_letter_template_views.xml",
        "wizard/client_letter_wizard_views.xml",
        "views/action_buttons_views.xml",
        "report/client_letter_report.xml",
    ],
    "installable": True,
    "auto_install": False,
    "application": False,
}
