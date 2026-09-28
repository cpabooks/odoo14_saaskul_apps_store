# -*- coding: utf-8 -*-
from odoo import api, fields, models, _

from .cafm_process_steps import AMC_STEPS, VAR_STEPS


class CafmAmcLifecycleWizard(models.TransientModel):
    """Guided AMC / VAR wizard — Create + Open per confirmed process step."""

    _name = "cpabooks.cafm.amc.wizard"
    _description = "CAFM AMC / VAR Lifecycle Wizard"

    path_type = fields.Selection(
        [("amc", "AMC"), ("var", "VAR (no AMC)")],
        string="Process Path",
        default=False,
    )
    # Legacy column kept so old cached forms / defaults do not crash create()
    step = fields.Char(string="Legacy step", copy=False)
    step_index = fields.Integer(default=0)
    step_key = fields.Char(compute="_compute_step_display")
    step_title = fields.Char(compute="_compute_step_display")
    progress_label = fields.Char(compute="_compute_step_display")
    step_help = fields.Text(compute="_compute_step_display")
    total_steps = fields.Integer(compute="_compute_step_display")

    partner_id = fields.Many2one("res.partner", string="Client")
    project_id = fields.Many2one("project.project", string="Project")
    contract_id = fields.Many2one(
        "cpabooks.cafm.contract",
        string="AMC Contract",
        domain="[('amc_contract_type', '=', 'amc')]",
    )
    sale_order_id = fields.Many2one("sale.order", string="Quotation")
    priority_id = fields.Many2one("cpabooks.cafm.priority", string="SLA Priority")
    material_mode = fields.Selection(
        [("issue", "Stock Issue"), ("purchase", "Direct Purchase")],
        default="issue",
        string="Materials mode",
    )
    # Legacy optional fields from earlier wizard versions
    sla_response_hours = fields.Float()
    sla_resolution_hours = fields.Float()
    sla_notes = fields.Text()

    _LEGACY_STEP_TO_INDEX = {
        "choose": 0,
        "contract": 1,
        "sla": 2,
        "ppm_or_work": 3,
        "quotation": 0,
        "project": 1,
        "materials": 2,
        "invoice": 3,
        "done": 0,
    }

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            legacy = vals.pop("step", None)
            if legacy and "step_index" not in vals:
                vals["step_index"] = self._LEGACY_STEP_TO_INDEX.get(legacy, 0)
            # Do not persist legacy step label
            vals["step"] = False
        return super().create(vals_list)

    def write(self, vals):
        if "step" in vals and "step_index" not in vals:
            legacy = vals.get("step")
            if legacy:
                vals["step_index"] = self._LEGACY_STEP_TO_INDEX.get(legacy, self.step_index)
            vals["step"] = False
        return super().write(vals)

    def init(self):
        cr = self.env.cr
        cr.execute(
            """
            SELECT 1 FROM information_schema.tables
             WHERE table_schema = 'public'
               AND table_name = 'cpabooks_cafm_amc_wizard'
            """
        )
        if not cr.fetchone():
            return
        cr.execute(
            """
            SELECT column_name FROM information_schema.columns
             WHERE table_schema = 'public'
               AND table_name = 'cpabooks_cafm_amc_wizard'
            """
        )
        cols = {row[0] for row in cr.fetchall()}
        if "step_index" not in cols:
            cr.execute(
                "ALTER TABLE cpabooks_cafm_amc_wizard "
                "ADD COLUMN step_index INTEGER DEFAULT 0"
            )
        if "material_mode" not in cols:
            cr.execute(
                "ALTER TABLE cpabooks_cafm_amc_wizard "
                "ADD COLUMN material_mode VARCHAR DEFAULT 'issue'"
            )
        if "sale_order_id" not in cols:
            cr.execute(
                "ALTER TABLE cpabooks_cafm_amc_wizard "
                "ADD COLUMN sale_order_id INTEGER"
            )

    def _steps(self):
        self.ensure_one()
        if self.path_type == "var":
            return list(VAR_STEPS)
        if self.path_type == "amc":
            return list(AMC_STEPS)
        return []

    @api.depends("path_type", "step_index")
    def _compute_step_display(self):
        helps = {
            "project": "Create or open the CAFM project (and client).",
            "contract": "CREATE a new AMC contract, or open an existing one.",
            "sla": "Create / configure Priority SLA levels (response & resolution).",
            "ppm_setup": "Run PPM Setup for the AMC contract schedule.",
            "ppm_generate": "Generate PPM visits from the setup.",
            "amc_call": "Create an AMC Call for reactive work.",
            "stock_issue": "Create a stock issue for materials used.",
            "billing": "Create / open Contract Orders and billing.",
            "invoice": "Create / open customer invoices.",
            "soa": "Open Client Statement of Account.",
            "quotation": "CREATE a sales quotation (VAR has no AMC).",
            "purchase": "CREATE a purchase RFQ / PO for direct buy.",
        }
        for wiz in self:
            steps = wiz._steps() if wiz.path_type else []
            total = len(steps) or 1
            idx = max(0, min(wiz.step_index or 0, total - 1)) if steps else 0
            step = steps[idx] if steps else {}
            key = step.get("key") or ""
            wiz.total_steps = total
            wiz.step_key = key
            wiz.step_title = step.get("label") or _("Choose path")
            wiz.progress_label = (
                _("Step %s / %s — %s") % (idx + 1, total, step.get("label") or "")
                if steps
                else _("Choose AMC or VAR")
            )
            wiz.step_help = helps.get(key, "")

    def _reopen(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("AMC / VAR Wizard"),
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
            "context": dict(self.env.context, form_view_initial_mode="edit"),
        }

    def action_choose_amc(self):
        self.write({"path_type": "amc", "step_index": 0})
        return self._reopen()

    def action_choose_var(self):
        self.write({"path_type": "var", "step_index": 0})
        return self._reopen()

    @api.onchange("path_type")
    def _onchange_path_type(self):
        if self.path_type:
            self.step_index = 0

    def action_next(self):
        self.ensure_one()
        if not self.path_type:
            return self._reopen()
        steps = self._steps()
        idx = min((self.step_index or 0) + 1, len(steps) - 1)
        self.write({"step_index": idx})
        return self._reopen()

    def action_back(self):
        self.ensure_one()
        if not self.path_type or (self.step_index or 0) <= 0:
            self.write({"path_type": False, "step_index": 0})
            return self._reopen()
        self.write({"step_index": (self.step_index or 0) - 1})
        return self._reopen()

    def _current_step(self):
        self.ensure_one()
        steps = self._steps()
        if not steps:
            return {}
        idx = max(0, min(self.step_index or 0, len(steps) - 1))
        return steps[idx]

    def _resolve_xmlid(self, step):
        xmlid = step.get("xmlid")
        action = self.env.ref(xmlid, raise_if_not_found=False) if xmlid else False
        if not action and step.get("xmlid_fallback"):
            action = self.env.ref(step["xmlid_fallback"], raise_if_not_found=False)
        if step.get("optional_module") and step["optional_module"] not in self.env:
            # Fallback vendor bills if purchase not installed
            return {
                "type": "ir.actions.act_window",
                "name": _("Vendor Bills"),
                "res_model": "account.move",
                "view_mode": "tree,form",
                "domain": [("move_type", "=", "in_invoice")],
                "context": {"default_move_type": "in_invoice"},
                "target": "current",
            }
        if not action:
            return False
        result = action.read()[0]
        result["target"] = result.get("target") or "current"
        return result

    def _ctx_defaults(self, step):
        ctx = dict(self.env.context or {})
        ctx.update(step.get("defaults") or {})
        if self.partner_id:
            ctx.setdefault("default_partner_id", self.partner_id.id)
            ctx.setdefault("default_client_id", self.partner_id.id)
        if self.project_id:
            ctx.setdefault("default_project_id", self.project_id.id)
        if self.contract_id and step.get("key") != "contract":
            ctx.setdefault("default_contract_id", self.contract_id.id)
        return ctx

    def action_create_step(self):
        """Open form in create mode for the current step."""
        self.ensure_one()
        step = self._current_step()
        if not step:
            return self._reopen()
        action = self._resolve_xmlid(step)
        if not action:
            return self._reopen()
        ctx = self._ctx_defaults(step)
        ctx["form_view_initial_mode"] = "edit"
        action["context"] = ctx
        action["view_mode"] = "form"
        action["views"] = [(False, "form")]
        action.pop("res_id", None)
        # Clear domain so new record form opens cleanly
        if action.get("res_model") == "sale.order":
            action["domain"] = []
        return action

    def action_open_step(self):
        """Open list / existing record for the current step."""
        self.ensure_one()
        step = self._current_step()
        if not step:
            return self._reopen()
        action = self._resolve_xmlid(step)
        if not action:
            return self._reopen()
        ctx = self._ctx_defaults(step)
        action["context"] = ctx
        # Prefer linked record when available
        key = step.get("key")
        if key == "contract" and self.contract_id:
            action["res_id"] = self.contract_id.id
            action["view_mode"] = "form"
            action["views"] = [(False, "form")]
        elif key == "project" and self.project_id:
            action["res_id"] = self.project_id.id
            action["view_mode"] = "form"
            action["views"] = [(False, "form")]
        elif key == "quotation" and self.sale_order_id:
            action["res_id"] = self.sale_order_id.id
            action["view_mode"] = "form"
            action["views"] = [(False, "form")]
        return action
