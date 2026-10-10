# -*- coding: utf-8 -*-
"""L1 Official print gate: show stuck checks, offer fix path or print anyway."""
from odoo import fields, models, _


class AuditedFinancialL1PrintWizard(models.TransientModel):
    _name = "audited.financial.l1.print.wizard"
    _description = "L1 Official print — validation gate"

    version_id = fields.Many2one(
        "audited.financial.version", required=True, ondelete="cascade"
    )
    export_pack = fields.Integer(required=True, default=1)
    export_kind = fields.Selection(
        [
            ("pdf", "PDF"),
            ("xlsx", "Excel"),
            ("docx", "Word"),
        ],
        required=True,
        default="pdf",
    )
    summary = fields.Text(string="Where it is stuck", readonly=True)
    tip = fields.Char(readonly=True)
    line_ids = fields.One2many(
        "audited.financial.l1.print.wizard.line",
        "wizard_id",
        string="Failed checks",
        readonly=True,
    )

    def action_no_cancel(self):
        """No — do not print."""
        return {"type": "ir.actions.act_window_close"}

    def action_yes_print_anyway(self):
        """Yes — complete print (acknowledge remaining gaps)."""
        self.ensure_one()
        ver = self.version_id.with_context(afg_l1_print_force=True)
        kind = self.export_kind or "pdf"
        pack = self.export_pack
        if kind == "xlsx":
            return ver.action_export_audit_xlsx(max_level=pack)
        if kind == "docx":
            return ver.action_export_audit_docx(max_level=pack)
        return ver.action_print_audit_report_pdf(max_level=pack)

    def action_open_fix_path(self):
        """Switch to L4 working papers so user can fix TB↔FS / mappings."""
        self.ensure_one()
        ver = self.version_id
        ver.afg_dashboard_set_print_max_level(4)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Fix path — L4 Working Papers"),
                "message": _(
                    "Report level set to L4. Open Validation and FS↔TB reconciliation, "
                    "fix the gaps listed in this wizard, then print L1 again.\n\nStuck:\n%s"
                ) % ((self.summary or "")[:1500]),
                "type": "warning",
                "sticky": True,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }


class AuditedFinancialL1PrintWizardLine(models.TransientModel):
    _name = "audited.financial.l1.print.wizard.line"
    _description = "L1 print gate — failed check line"
    _order = "id"

    wizard_id = fields.Many2one(
        "audited.financial.l1.print.wizard",
        required=True,
        ondelete="cascade",
    )
    name = fields.Char(string="Check", readonly=True)
    detail = fields.Text(string="Detail / where stuck", readonly=True)
    gap_hint = fields.Char(string="Gap type", readonly=True)
