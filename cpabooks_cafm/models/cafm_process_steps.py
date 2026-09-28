# -*- coding: utf-8 -*-
"""Confirmed CAFM AMC / VAR process steps (shared by cycle, flowchart, wizard)."""

# Themes for round cycle colouring (Switchgear-style)
# contract | ops | materials | billing

AMC_STEPS = [
    {
        "key": "project",
        "label": "Client / Project",
        "theme": "contract",
        "xmlid": "cpabooks_cafm.action_cpabooks_cafm_projects",
        "create": True,
    },
    {
        "key": "contract",
        "label": "Create AMC Contract",
        "theme": "contract",
        "xmlid": "cpabooks_cafm.action_cpabooks_cafm_amc",
        "create": True,
        "defaults": {"default_amc_contract_type": "amc"},
    },
    {
        "key": "sla",
        "label": "Setup SLA",
        "theme": "ops",
        "xmlid": "cpabooks_cafm.action_cpabooks_cafm_priority",
        "create": True,
    },
    {
        "key": "ppm_setup",
        "label": "PPM Setup",
        "theme": "ops",
        "xmlid": "cpabooks_cafm.action_cafm_ppm_setup_wizard",
        "create": True,
    },
    {
        "key": "ppm_generate",
        "label": "Generate PPM",
        "theme": "ops",
        "xmlid": "cpabooks_cafm.action_cafm_ppm_generate_wizard",
        "create": True,
    },
    {
        "key": "amc_call",
        "label": "AMC Call",
        "theme": "ops",
        "xmlid": "cpabooks_cafm.action_cafm_amc_call_form",
        "create": True,
    },
    {
        "key": "stock_issue",
        "label": "Stock Issue",
        "theme": "materials",
        "xmlid": "cpabooks_cafm.action_cafm_stock_issue_amc",
        "create": True,
    },
    {
        "key": "billing",
        "label": "Cont. Order / Billing",
        "theme": "billing",
        "xmlid": "cpabooks_cafm.action_cpabooks_cafm_contract_orders",
        "create": True,
    },
    {
        "key": "invoice",
        "label": "Invoice",
        "theme": "billing",
        "xmlid": "cpabooks_cafm.action_cpabooks_cafm_amc_invoices",
        "create": True,
    },
    {
        "key": "soa",
        "label": "Client SOA",
        "theme": "billing",
        "xmlid": "cpabooks_cafm.action_cafm_client_soa_single_project",
        "create": False,
    },
]

VAR_STEPS = [
    {
        "key": "quotation",
        "label": "Create Quotation",
        "theme": "contract",
        "xmlid": "sale.action_quotations_with_onboarding",
        "xmlid_fallback": "sale.action_quotations",
        "create": True,
    },
    {
        "key": "project",
        "label": "Create Project",
        "theme": "contract",
        "xmlid": "cpabooks_cafm.action_cpabooks_cafm_projects",
        "create": True,
    },
    {
        "key": "stock_issue",
        "label": "Stock Issue",
        "theme": "materials",
        "xmlid": "cpabooks_cafm.action_cafm_stock_issue_var",
        "create": True,
    },
    {
        "key": "purchase",
        "label": "Direct Purchase",
        "theme": "materials",
        "xmlid": "purchase.purchase_rfq",
        "optional_module": "purchase",
        "create": True,
    },
    {
        "key": "invoice",
        "label": "Invoice",
        "theme": "billing",
        "xmlid": "account.action_move_out_invoice_type",
        "create": True,
    },
]

AMC_FLOW_HIERARCHY = [
    ("CAFM AMC", [
        ("1. Client / Project", []),
        ("2. AMC Contract", [
            ("3. Setup SLA", []),
            ("4–5. PPM Setup → Generate", []),
            ("6. AMC Call", []),
        ]),
        ("7. Stock Issue", []),
        ("8. Cont. Order / Billing", []),
        ("9. Invoice", []),
        ("10. Client SOA", []),
    ]),
]

VAR_FLOW_HIERARCHY = [
    ("CAFM VAR (no AMC)", [
        ("1. Quotation", []),
        ("2. Project", []),
        ("3. Materials", [
            ("3a. Stock Issue", []),
            ("3b. Direct Purchase", []),
        ]),
        ("4. Invoice", []),
    ]),
]
