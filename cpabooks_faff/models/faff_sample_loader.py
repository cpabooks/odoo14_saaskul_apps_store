# -*- coding: utf-8 -*-
import logging
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

DEMO_TAG = "[FAFF-DEMO]"
DEMO_JOB_SPECS = [
    # (site_suffix, job_type_xml, stage, status, with_so, so_confirm, project, material, testing, completion, invoice)
    ("CRM Pipeline", "job_type_fire_alarm", "crm", "draft", False, False, False, False, False, False, False),
    ("Inspection Pending", "job_type_fire_fighting", "inspection", "in_progress", False, False, False, False, False, False, False),
    ("Estimation Draft", "job_type_sprinkler", "estimation", "in_progress", False, False, False, False, False, False, False),
    ("Quotation Out", "job_type_hydrant", "quotation", "in_progress", True, False, False, False, False, False, False),
    ("Confirmed Project", "job_type_modification", "project", "in_progress", True, True, True, True, False, False, False),
    ("Material / Execution", "job_type_installation", "execution", "in_progress", True, True, True, True, False, False, False),
    ("Testing Stage", "job_type_testing", "testing", "in_progress", True, True, True, True, True, False, False),
    ("Invoice Pending", "job_type_fire_pump", "invoice", "in_progress", True, True, True, True, True, True, True),
    ("Completed Paid", "job_type_amc", "done", "paid", True, True, True, True, True, True, True),
]


class FaffSampleLoader(models.TransientModel):
    _name = "cpabooks.faff.sample.loader"
    _description = "FAFF Sample / Demo Loader"

    note = fields.Html(readonly=True, compute="_compute_note")
    mode = fields.Selection(
        [("load", "Load"), ("clean", "Clean")],
        default="load",
        string="Mode",
    )

    @api.depends()
    def _compute_note(self):
        html = (
            "<div><h3>FAFF Demo Data</h3>"
            "<p>Creates <strong>%d demo jobs</strong> across the full FAFF cycle, tagged "
            "<code>%s</code>, so Dashboard KPIs and Reports show real counts:</p>"
            "<ul>"
            "<li>CRM opportunities + FAFF Jobs (all stages)</li>"
            "<li>Inspections, Estimations / BOQ, Quotations &amp; confirmed SO</li>"
            "<li>Projects + tasks, Material plans, Purchase RFQ, Stock issues</li>"
            "<li>Testing &amp; Commissioning, Completion / Handover notes</li>"
            "<li>Customer invoices (draft + posted)</li>"
            "</ul>"
            "<p>Sample customer: <strong>Test Fire Safety LLC</strong>. "
            "Use <strong>Clean Demo Data</strong> before reloading.</p></div>"
        ) % (len(DEMO_JOB_SPECS), DEMO_TAG)
        for rec in self:
            rec.note = html

    def _tag(self, label):
        return "%s %s" % (DEMO_TAG, label)

    def _get_product(self):
        product = self.env["product.product"].search(
            [("type", "in", ("consu", "product", "service"))], limit=1
        )
        if not product:
            product = self.env["product.product"].create(
                {
                    "name": self._tag("FAFF Demo Product"),
                    "type": "consu",
                    "list_price": 100.0,
                    "standard_price": 60.0,
                }
            )
        return product

    def _get_supplier(self, partner):
        supplier = self.env["res.partner"].search(
            [("supplier_rank", ">", 0)], limit=1
        )
        return supplier or partner

    def _job_type(self, xml_suffix):
        return self.env.ref(
            "cpabooks_faff.%s" % xml_suffix, raise_if_not_found=False
        ) or self.env["cpabooks.faff.job.type"].search([], limit=1)

    def _create_estimate(self, job, product, uom, approved=True):
        estimate = self.env["cpabooks.faff.estimate"].create(
            {
                "job_id": job.id,
                "notes": DEMO_TAG,
                "state": "approved" if approved else "draft",
            }
        )
        Line = self.env["cpabooks.faff.estimate.line"]
        lines_data = [
            ("Fire Alarm Panel", 1, 2500, 4000, True),
            ("Smoke Detectors", 40, 50, 80, True),
            ("Cabling & Accessories", 1, 1500, 2300, True),
            ("Labour Installation", 1, 2000, 2800, False),
            ("Programming & Testing", 1, 500, 700, False),
        ]
        for name, qty, unit_cost, unit_sell, is_mat in lines_data:
            Line.create(
                {
                    "estimate_id": estimate.id,
                    "product_id": product.id,
                    "name": self._tag(name),
                    "product_uom_qty": qty,
                    "product_uom_id": uom.id if uom else False,
                    "material_cost": unit_cost if is_mat else 0.0,
                    "labour_cost": unit_cost if not is_mat else 0.0,
                    "selling_price": unit_sell,
                    "margin_percent": (
                        ((unit_sell - unit_cost) / unit_sell * 100.0) if unit_sell else 0.0
                    ),
                }
            )
        return estimate

    def _create_sale_order(self, job, estimate, confirm=False):
        lines = []
        for line in estimate.line_ids:
            lines.append(
                (
                    0,
                    0,
                    {
                        "product_id": line.product_id.id,
                        "name": line.name,
                        "product_uom_qty": line.product_uom_qty,
                        "product_uom": line.product_uom_id.id or line.product_id.uom_id.id,
                        "price_unit": line.selling_price,
                    },
                )
            )
        so = self.env["sale.order"].create(
            {
                "partner_id": job.partner_id.id,
                "user_id": job.salesperson_id.id,
                "origin": job.name,
                "client_order_ref": job.name,
                "note": DEMO_TAG,
                "faff_job_id": job.id,
                "order_line": lines,
            }
        )
        job.sale_order_id = so.id
        if confirm and so.state in ("draft", "sent"):
            so.action_confirm()
        return so

    def _create_project(self, job):
        project = self.env["project.project"].create(
            {
                "name": "%s — %s" % (job.name, job.site_name or "Site"),
                "partner_id": job.partner_id.id,
                "user_id": job.salesperson_id.id,
                "faff_job_id": job.id,
            }
        )
        tasks = self.env["cpabooks.faff.default.task"].search([], limit=6)
        for tmpl in tasks:
            self.env["project.task"].create(
                {
                    "name": tmpl.name,
                    "project_id": project.id,
                    "faff_job_id": job.id,
                    "description": DEMO_TAG,
                }
            )
        job.project_id = project.id
        job.actual_start_date = fields.Date.context_today(self)
        return project

    def _create_materials(self, job, estimate, product, do_issue=False, do_po=False):
        Plan = self.env["cpabooks.faff.material.plan"]
        plans = self.env["cpabooks.faff.material.plan"]
        for line in estimate.line_ids.filtered("product_id")[:3]:
            plan = Plan.create(
                {
                    "job_id": job.id,
                    "product_id": line.product_id.id,
                    "name": line.name,
                    "product_uom_id": line.product_uom_id.id,
                    "qty_required": line.product_uom_qty,
                    "issue_qty": min(line.product_uom_qty, 1.0) if do_issue else 0.0,
                    "purchase_qty": max(line.product_uom_qty - 1.0, 0.0)
                    if do_po
                    else line.product_uom_qty,
                }
            )
            plans |= plan
        if do_issue and plans:
            try:
                plans[0].action_issue_from_store()
            except Exception:
                # Warehouse/picking may fail on empty stock — keep plan only
                pass
        if do_po and plans:
            supplier = self._get_supplier(job.partner_id)
            po = self.env["purchase.order"].create(
                {
                    "partner_id": supplier.id,
                    "origin": job.name,
                    "faff_job_id": job.id,
                    "order_line": [
                        (
                            0,
                            0,
                            {
                                "product_id": plans[0].product_id.id,
                                "name": plans[0].name,
                                "product_qty": plans[0].purchase_qty or 1.0,
                                "product_uom": plans[0].product_uom_id.id
                                or plans[0].product_id.uom_po_id.id,
                                "price_unit": plans[0].product_id.standard_price,
                                "date_planned": fields.Datetime.now(),
                            },
                        )
                    ],
                }
            )
            plans[0].purchase_order_ids = [(4, po.id)]
        return plans

    def _create_testing(self, job, passed=True):
        return self.env["cpabooks.faff.testing"].create(
            {
                "job_id": job.id,
                "name": self._tag("Testing & Commissioning"),
                "system_status": "passed" if passed else "rectification",
                "panel_tested": True,
                "devices_tested": True,
                "alarm_tested": True,
                "remarks": DEMO_TAG,
                "defects_found": "" if passed else self._tag("Detector fault zone 2"),
                "rectification_required": not passed,
            }
        )

    def _create_completion(self, job, confirmed=True):
        completion = self.env["cpabooks.faff.completion"].create(
            {
                "job_id": job.id,
                "work_completed": self._tag("Installation and commissioning completed"),
                "material_delivered": self._tag("Panel + detectors + accessories"),
                "testing_result": "Passed",
                "warranty": "12 months",
                "remarks": DEMO_TAG,
                "customer_name": "Demo Client Signatory",
                "customer_designation": "Facility Manager",
                "sign_date": fields.Date.context_today(self),
                "state": "confirmed" if confirmed else "draft",
            }
        )
        if confirmed:
            job.actual_end_date = fields.Date.context_today(self)
        return completion

    def _create_invoice(self, job, so, post=False):
        if not so or so.state not in ("sale", "done"):
            return self.env["account.move"]
        existing = so.invoice_ids.filtered(
            lambda m: m.move_type == "out_invoice" and m.state != "cancel"
        )
        if existing:
            inv = existing[0]
        else:
            try:
                moves = so._create_invoices()
            except Exception:
                return self.env["account.move"]
            inv = moves[:1]
        if inv:
            inv.faff_job_id = job.id
            inv.narration = DEMO_TAG
            if post and inv.state == "draft":
                try:
                    inv.action_post()
                except Exception:
                    pass
        return inv

    def action_load_demo_data(self):
        self.ensure_one()
        Job = self.env["cpabooks.faff.job"]
        if Job.search([("remarks", "ilike", DEMO_TAG)], limit=1):
            raise UserError(
                _("FAFF demo data already exists. Use Clean Demo Data first.")
            )

        Partner = self.env["res.partner"]
        partner = Partner.search([("email", "=", "demo@faff-demo.local")], limit=1)
        if not partner:
            partner = Partner.create(
                {
                    "name": "Test Fire Safety LLC",
                    "email": "demo@faff-demo.local",
                    "phone": "+971500000100",
                    "comment": self._tag("Customer"),
                }
            )

        product = self._get_product()
        uom = self.env.ref("uom.product_uom_unit", raise_if_not_found=False)
        today = fields.Date.context_today(self)
        created_jobs = self.env["cpabooks.faff.job"]

        for idx, spec in enumerate(DEMO_JOB_SPECS, start=1):
            (
                site_suffix,
                type_xml,
                stage,
                status,
                with_so,
                so_confirm,
                with_project,
                with_material,
                with_testing,
                with_completion,
                with_invoice,
            ) = spec
            job_type = self._job_type(type_xml)
            job = Job.create(
                {
                    "partner_id": partner.id,
                    "site_name": "Demo Tower — %s" % site_suffix,
                    "site_address": "Dubai, UAE",
                    "job_type_id": job_type.id if job_type else False,
                    "salesperson_id": self.env.user.id,
                    "description": self._tag(site_suffix),
                    "planned_start_date": today - timedelta(days=30 - idx),
                    "expected_end_date": today + timedelta(days=idx * 3),
                    "stage": stage,
                    "status": status,
                    "remarks": DEMO_TAG,
                    "wizard_step": min(idx, 10),
                }
            )
            lead = self.env["crm.lead"].create(
                {
                    "name": self._tag("Opp %s" % site_suffix),
                    "partner_id": partner.id,
                    "type": "opportunity",
                    "user_id": self.env.user.id,
                    "description": DEMO_TAG,
                    "faff_job_id": job.id,
                }
            )
            job.crm_lead_id = lead.id
            lead.faff_job_id = job.id

            if stage != "crm":
                self.env["cpabooks.faff.visit"].create(
                    {
                        "job_id": job.id,
                        "name": self._tag("Inspection %s" % idx),
                        "problem_requirement": site_suffix,
                        "observation": self._tag("Site survey completed"),
                        "technical_recommendation": self._tag("Proceed with BOQ"),
                        "scope_summary": site_suffix,
                        "inspection_remarks": DEMO_TAG,
                    }
                )

            estimate = False
            if stage not in ("crm", "inspection"):
                estimate = self._create_estimate(
                    job, product, uom, approved=(stage != "estimation")
                )

            so = False
            if with_so and estimate:
                so = self._create_sale_order(job, estimate, confirm=so_confirm)

            if with_project:
                self._create_project(job)

            if with_material and estimate:
                self._create_materials(
                    job,
                    estimate,
                    product,
                    do_issue=(stage in ("execution", "testing", "invoice", "done")),
                    do_po=(stage in ("project", "material", "execution", "testing", "invoice", "done")),
                )

            if with_testing:
                self._create_testing(job, passed=(stage != "testing" or idx % 2 == 0))

            if with_completion:
                self._create_completion(
                    job, confirmed=(stage in ("invoice", "payment", "done"))
                )

            if with_invoice and so:
                self._create_invoice(job, so, post=(stage == "done"))

            created_jobs |= job

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("FAFF Demo Loaded"),
                "message": _(
                    "Created %s jobs with CRM, inspections, estimates, quotations, "
                    "projects, materials, testing, handover and invoices. "
                    "Open FAFF Dashboard to see KPIs."
                )
                % len(created_jobs),
                "type": "success",
                "sticky": False,
                "next": {
                    "type": "ir.actions.client",
                    "tag": "faff_dashboard",
                },
            },
        }

    def _safe_call(self, records, method_name, *args, **kwargs):
        for rec in records:
            method = getattr(rec, method_name, None)
            if not method:
                continue
            try:
                method(*args, **kwargs)
            except Exception as exc:
                _logger.warning("FAFF demo clean: %s on %s failed: %s", method_name, rec, exc)

    def _force_unlink(self, records):
        if not records:
            return
        leftover = records.exists()
        for rec in leftover:
            try:
                rec.unlink()
            except Exception:
                try:
                    rec.sudo().unlink()
                except Exception as exc:
                    _logger.warning("FAFF demo clean: unlink %s failed: %s", rec, exc)
                    table = rec._table
                    if table and rec.id:
                        try:
                            rec.env.cr.execute(
                                "DELETE FROM %s WHERE id = %%s" % table, (rec.id,)
                            )
                        except Exception as sql_exc:
                            _logger.warning(
                                "FAFF demo clean: SQL delete %s/%s failed: %s",
                                table,
                                rec.id,
                                sql_exc,
                            )

    def _detach_and_unlink_pickings(self, pickings):
        """Cancel / detach SO+PO links then unlink — never block demo cleanup."""
        pickings = pickings.exists()
        if not pickings:
            return
        moves = pickings.mapped("move_lines") | pickings.mapped("move_ids_without_package")
        for picking in pickings:
            try:
                if picking.state not in ("done", "cancel"):
                    picking.action_cancel()
            except Exception:
                try:
                    picking.write({"state": "cancel"})
                except Exception:
                    pass
            try:
                picking.write({"sale_id": False, "faff_job_id": False})
            except Exception:
                pass
        if moves:
            self._force_unlink(moves.exists())
        self._force_unlink(pickings.exists())

    def _cancel_unlink_moves(self, moves):
        moves = moves.exists()
        if not moves:
            return
        for move in moves:
            try:
                if move.state == "posted":
                    # Unreconcile payments first
                    if hasattr(move, "_get_reconciled_payments"):
                        pays = move._get_reconciled_payments()
                        for pay in pays:
                            try:
                                if pay.state in ("posted", "reconciled"):
                                    if hasattr(pay, "action_draft"):
                                        pay.action_draft()
                                    elif hasattr(pay, "cancel"):
                                        pay.cancel()
                            except Exception:
                                pass
                    move.button_draft()
                if move.state == "draft":
                    move.button_cancel()
            except Exception:
                try:
                    move.write({"state": "cancel"})
                except Exception:
                    pass
        self._force_unlink(moves.exists())

    def action_clean_demo_data(self):
        self.ensure_one()
        counts = {}
        Job = self.env["cpabooks.faff.job"].sudo()
        jobs = Job.search(
            ["|", ("remarks", "ilike", DEMO_TAG), ("description", "ilike", DEMO_TAG)]
        )
        job_ids = jobs.ids

        sos = self.env["sale.order"].sudo().search(
            ["|", ("faff_job_id", "in", job_ids), ("note", "ilike", DEMO_TAG)]
        )
        pos = self.env["purchase.order"].sudo().search(
            [("faff_job_id", "in", job_ids)]
        )

        pickings = self.env["stock.picking"].sudo().search(
            [
                "|",
                "|",
                "|",
                ("faff_job_id", "in", job_ids),
                ("sale_id", "in", sos.ids),
                ("purchase_id", "in", pos.ids),
                ("origin", "ilike", "FAFF/"),
            ]
        )
        # Also every picking still linked on the demo SOs (dev_picking_cancel)
        pickings |= sos.mapped("picking_ids")
        pickings |= pos.mapped("picking_ids")
        counts["pickings"] = len(pickings)
        self._detach_and_unlink_pickings(pickings)

        moves = self.env["account.move"].sudo().search(
            [
                "|",
                "|",
                ("faff_job_id", "in", job_ids),
                ("narration", "ilike", DEMO_TAG),
                ("invoice_origin", "ilike", "FAFF/"),
            ]
        )
        moves |= sos.mapped("invoice_ids")
        moves |= pos.mapped("invoice_ids")
        counts["invoices"] = len(moves)
        self._cancel_unlink_moves(moves)

        # Detach leftovers so SO unlink cannot see picking_ids / invoice_ids
        leftover_so_pick = sos.mapped("picking_ids").exists()
        leftover_so_inv = sos.mapped("invoice_ids").exists()
        if leftover_so_pick:
            leftover_so_pick.write({"sale_id": False})
            self._force_unlink(leftover_so_pick)
        if leftover_so_inv:
            leftover_so_inv.write({"faff_job_id": False})
            self._force_unlink(leftover_so_inv)

        for so in sos.exists():
            try:
                so.with_context(disable_cancel_warning=True).write({"state": "cancel"})
            except Exception:
                pass
        counts["sale_orders"] = len(sos)
        self._force_unlink(sos.exists())

        for po in pos.exists():
            try:
                if po.state not in ("cancel",):
                    po.button_cancel()
            except Exception:
                try:
                    po.write({"state": "cancel"})
                except Exception:
                    pass
        counts["purchases"] = len(pos)
        self._force_unlink(pos.exists())

        tasks = self.env["project.task"].sudo().search([("faff_job_id", "in", job_ids)])
        self._force_unlink(tasks)
        projects = self.env["project.project"].sudo().search(
            [("faff_job_id", "in", job_ids)]
        )
        counts["projects"] = len(projects)
        self._force_unlink(projects)

        leads = self.env["crm.lead"].sudo().search(
            ["|", ("faff_job_id", "in", job_ids), ("description", "ilike", DEMO_TAG)]
        )
        counts["crm"] = len(leads)
        self._force_unlink(leads)

        counts["jobs"] = len(jobs)
        self._force_unlink(jobs.exists())

        partners = self.env["res.partner"].sudo().search(
            [("email", "=", "demo@faff-demo.local")]
        )
        products = self.env["product.product"].sudo().search(
            [("name", "ilike", DEMO_TAG)]
        )
        counts["partners"] = len(partners)
        counts["products"] = len(products)
        self._force_unlink(partners)
        self._force_unlink(products)

        parts = ["%s=%s" % (k, v) for k, v in counts.items() if v]
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("FAFF Demo Cleanup"),
                "message": ", ".join(parts) if parts else _("No demo records found."),
                "type": "success",
                "sticky": False,
            },
        }
