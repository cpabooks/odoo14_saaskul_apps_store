# -*- coding: utf-8 -*-
from odoo import api, models


class FaffDashboard(models.AbstractModel):
    _name = "cpabooks.faff.dashboard"
    _description = "FAFF Workflow Dashboard"

    @api.model
    def get_dashboard_data(self):
        company = self.env.company
        return {
            "title": "FAFF Dashboard",
            "subtitle": company.name,
            "kpis": self._dashboard_kpis(),
            "workflow": self._workflow_sections(),
        }

    def _company_domain(self, model_name):
        if model_name in self.env and "company_id" in self.env[model_name]._fields:
            return [("company_id", "in", [False, self.env.company.id])]
        return []

    @api.model
    def _item(self, label, count, action_xmlid, status):
        return {
            "label": label,
            "count": count,
            "action_xmlid": action_xmlid,
            "status": status,
        }

    @api.model
    def _dashboard_kpis(self):
        cd = self._company_domain
        Job = self.env["cpabooks.faff.job"].sudo()
        Visit = self.env["cpabooks.faff.visit"].sudo()
        Est = self.env["cpabooks.faff.estimate"].sudo()
        Mat = self.env["cpabooks.faff.material.plan"].sudo()
        Test = self.env["cpabooks.faff.testing"].sudo()
        Comp = self.env["cpabooks.faff.completion"].sudo()
        SO = self.env["sale.order"].sudo()
        Move = self.env["account.move"].sudo()

        return [
            {
                "label": "Open Jobs",
                "value": Job.search_count(
                    cd("cpabooks.faff.job")
                    + [("stage", "not in", ("done", "cancel")), ("active", "=", True)]
                ),
                "action_xmlid": "cpabooks_faff.action_faff_job",
                "icon": "fa-fire",
            },
            {
                "label": "Inspections",
                "value": Visit.search_count(cd("cpabooks.faff.visit")),
                "action_xmlid": "cpabooks_faff.action_faff_visit",
                "icon": "fa-map-marker",
            },
            {
                "label": "Estimations",
                "value": Est.search_count(cd("cpabooks.faff.estimate")),
                "action_xmlid": "cpabooks_faff.action_faff_estimate",
                "icon": "fa-calculator",
            },
            {
                "label": "Quotations",
                "value": SO.search_count(
                    cd("sale.order")
                    + [("faff_job_id", "!=", False), ("state", "in", ("draft", "sent"))]
                ),
                "action_xmlid": "sale.action_quotations_with_onboarding",
                "icon": "fa-file-text-o",
            },
            {
                "label": "Confirmed SO",
                "value": SO.search_count(
                    cd("sale.order")
                    + [("faff_job_id", "!=", False), ("state", "in", ("sale", "done"))]
                ),
                "action_xmlid": "sale.action_orders",
                "icon": "fa-shopping-cart",
            },
            {
                "label": "Material Plans",
                "value": Mat.search_count(cd("cpabooks.faff.material.plan")),
                "action_xmlid": "cpabooks_faff.action_faff_material",
                "icon": "fa-cubes",
            },
            {
                "label": "Testing Open",
                "value": Test.search_count(
                    cd("cpabooks.faff.testing")
                    + [("system_status", "in", ("failed", "rectification"))]
                ),
                "action_xmlid": "cpabooks_faff.action_faff_testing",
                "icon": "fa-check-circle",
            },
            {
                "label": "Invoices Unpaid",
                "value": Move.search_count(
                    cd("account.move")
                    + [
                        ("faff_job_id", "!=", False),
                        ("move_type", "=", "out_invoice"),
                        ("state", "=", "posted"),
                        ("payment_state", "in", ("not_paid", "partial")),
                    ]
                ),
                "action_xmlid": "account.action_move_out_invoice_type",
                "icon": "fa-money",
            },
            {
                "label": "Handovers",
                "value": Comp.search_count(cd("cpabooks.faff.completion")),
                "action_xmlid": "cpabooks_faff.action_faff_completion",
                "icon": "fa-handshake-o",
            },
        ]

    @api.model
    def _workflow_sections(self):
        cd = self._company_domain
        Job = self.env["cpabooks.faff.job"].sudo()
        Lead = self.env["crm.lead"].sudo()
        Visit = self.env["cpabooks.faff.visit"].sudo()
        Est = self.env["cpabooks.faff.estimate"].sudo()
        SO = self.env["sale.order"].sudo()
        Mat = self.env["cpabooks.faff.material.plan"].sudo()
        PO = self.env["purchase.order"].sudo()
        Pick = self.env["stock.picking"].sudo()
        Test = self.env["cpabooks.faff.testing"].sudo()
        Comp = self.env["cpabooks.faff.completion"].sudo()
        Move = self.env["account.move"].sudo()
        Pay = self.env["account.payment"].sudo()

        sections = [
            {
                "id": "crm",
                "title": "CRM / Enquiry",
                "theme": "customer",
                "items": [
                    self._item(
                        "FAFF-linked CRM opportunities",
                        Lead.search_count(
                            cd("crm.lead") + [("faff_job_id", "!=", False)]
                        ),
                        "crm.crm_lead_action_pipeline",
                        "progress",
                    ),
                    self._item(
                        "Jobs at CRM stage",
                        Job.search_count(cd("cpabooks.faff.job") + [("stage", "=", "crm")]),
                        "cpabooks_faff.action_faff_job",
                        "pending",
                    ),
                ],
            },
            {
                "id": "site_estimate",
                "title": "Inspection & Estimation",
                "theme": "engineering",
                "items": [
                    self._item(
                        "Site inspections",
                        Visit.search_count(cd("cpabooks.faff.visit")),
                        "cpabooks_faff.action_faff_visit",
                        "progress",
                    ),
                    self._item(
                        "Estimates — draft / saved",
                        Est.search_count(
                            cd("cpabooks.faff.estimate")
                            + [("state", "in", ("draft", "saved"))]
                        ),
                        "cpabooks_faff.action_faff_estimate",
                        "pending",
                    ),
                    self._item(
                        "Estimates — approved",
                        Est.search_count(
                            cd("cpabooks.faff.estimate")
                            + [("state", "in", ("approved", "done"))]
                        ),
                        "cpabooks_faff.action_faff_estimate",
                        "progress",
                    ),
                    self._item(
                        "Jobs at inspection / estimation",
                        Job.search_count(
                            cd("cpabooks.faff.job")
                            + [("stage", "in", ("inspection", "estimation"))]
                        ),
                        "cpabooks_faff.action_faff_job",
                        "pending",
                    ),
                ],
            },
            {
                "id": "sales",
                "title": "Quotation & Sales",
                "theme": "customer",
                "items": [
                    self._item(
                        "Quotations to confirm",
                        SO.search_count(
                            cd("sale.order")
                            + [
                                ("faff_job_id", "!=", False),
                                ("state", "in", ("draft", "sent")),
                            ]
                        ),
                        "sale.action_quotations_with_onboarding",
                        "pending",
                    ),
                    self._item(
                        "Confirmed sale orders",
                        SO.search_count(
                            cd("sale.order")
                            + [
                                ("faff_job_id", "!=", False),
                                ("state", "in", ("sale", "done")),
                            ]
                        ),
                        "sale.action_orders",
                        "progress",
                    ),
                    self._item(
                        "Jobs quotation / confirmed",
                        Job.search_count(
                            cd("cpabooks.faff.job")
                            + [("stage", "in", ("quotation", "confirmed"))]
                        ),
                        "cpabooks_faff.action_faff_job",
                        "progress",
                    ),
                ],
            },
            {
                "id": "ops",
                "title": "Project / Material / Execution",
                "theme": "purchase",
                "items": [
                    self._item(
                        "Jobs — project / material / execution",
                        Job.search_count(
                            cd("cpabooks.faff.job")
                            + [("stage", "in", ("project", "material", "execution"))]
                        ),
                        "cpabooks_faff.action_faff_job",
                        "progress",
                    ),
                    self._item(
                        "Material requirements",
                        Mat.search_count(cd("cpabooks.faff.material.plan")),
                        "cpabooks_faff.action_faff_material",
                        "pending",
                    ),
                    self._item(
                        "FAFF purchase RFQ / PO",
                        PO.search_count(cd("purchase.order") + [("faff_job_id", "!=", False)]),
                        "purchase.purchase_rfq",
                        "pending",
                    ),
                    self._item(
                        "FAFF stock issues / pickings",
                        Pick.search_count(
                            cd("stock.picking") + [("faff_job_id", "!=", False)]
                        ),
                        "stock.action_picking_tree_all",
                        "progress",
                    ),
                ],
            },
            {
                "id": "testing",
                "title": "Testing & Handover",
                "theme": "engineering",
                "items": [
                    self._item(
                        "Testing — passed",
                        Test.search_count(
                            cd("cpabooks.faff.testing")
                            + [("system_status", "in", ("passed", "passed_remarks"))]
                        ),
                        "cpabooks_faff.action_faff_testing",
                        "progress",
                    ),
                    self._item(
                        "Testing — failed / rectification",
                        Test.search_count(
                            cd("cpabooks.faff.testing")
                            + [("system_status", "in", ("failed", "rectification"))]
                        ),
                        "cpabooks_faff.action_faff_testing",
                        "pending",
                    ),
                    self._item(
                        "Completion notes — draft",
                        Comp.search_count(
                            cd("cpabooks.faff.completion") + [("state", "=", "draft")]
                        ),
                        "cpabooks_faff.action_faff_completion",
                        "pending",
                    ),
                    self._item(
                        "Completion notes — confirmed",
                        Comp.search_count(
                            cd("cpabooks.faff.completion") + [("state", "=", "confirmed")]
                        ),
                        "cpabooks_faff.action_faff_completion",
                        "progress",
                    ),
                ],
            },
            {
                "id": "accounting",
                "title": "Invoice & Payment",
                "theme": "accounting",
                "items": [
                    self._item(
                        "Customer invoices — draft",
                        Move.search_count(
                            cd("account.move")
                            + [
                                ("faff_job_id", "!=", False),
                                ("move_type", "=", "out_invoice"),
                                ("state", "=", "draft"),
                            ]
                        ),
                        "account.action_move_out_invoice_type",
                        "pending",
                    ),
                    self._item(
                        "Customer invoices — posted unpaid",
                        Move.search_count(
                            cd("account.move")
                            + [
                                ("faff_job_id", "!=", False),
                                ("move_type", "=", "out_invoice"),
                                ("state", "=", "posted"),
                                ("payment_state", "in", ("not_paid", "partial")),
                            ]
                        ),
                        "account.action_move_out_invoice_type",
                        "progress",
                    ),
                    self._item(
                        "Jobs — invoice / payment stage",
                        Job.search_count(
                            cd("cpabooks.faff.job")
                            + [("stage", "in", ("invoice", "payment"))]
                        ),
                        "cpabooks_faff.action_faff_job",
                        "pending",
                    ),
                    self._item(
                        "Jobs completed / paid",
                        Job.search_count(
                            cd("cpabooks.faff.job") + [("stage", "=", "done")]
                        ),
                        "cpabooks_faff.action_faff_job",
                        "progress",
                    ),
                    self._item(
                        "Inbound payments (draft)",
                        Pay.search_count(
                            cd("account.payment")
                            + [("payment_type", "=", "inbound"), ("state", "=", "draft")]
                        ),
                        "account.action_account_payments",
                        "pending",
                    ),
                ],
            },
        ]
        return sections
