# -*- coding: utf-8 -*-
from odoo import fields, models, _


class AuditedFinancialPrintSetupWizard(models.TransientModel):
    _name = "audited.financial.print.setup.wizard"
    _description = "AFG Print Setup"

    version_id = fields.Many2one(
        "audited.financial.version", required=True, ondelete="cascade"
    )
    print_company_name = fields.Char(string="Company print name")
    print_show_page_numbers = fields.Boolean(
        string="Add page numbers",
        default=False,
        help="Off by default. Turn on to print page numbers on PDF.",
    )
    line_ids = fields.One2many(
        "audited.financial.print.setup.wizard.line",
        "wizard_id",
        string="Pages",
    )

    def _reload_page_lines(self):
        self.ensure_one()
        ver = self.version_id
        excl = ver._afg_print_exclude_key_set()
        doc = ver.with_context(afg_print_setup_catalog=True)._afg_build_print_chapters() or {}
        Line = self.env["audited.financial.print.setup.wizard.line"]
        self.line_ids.unlink()
        seq = 10
        for ch in doc.get("chapters") or []:
            if not isinstance(ch, dict):
                continue
            key = (ch.get("key") or "").strip() or "page"
            Line.create({
                "wizard_id": self.id,
                "sequence": seq,
                "page_key": key,
                "name": ch.get("title") or key,
                "include_page": key not in excl,
                "preview_text": ver._afg_chapter_preview_text(ch),
            })
            seq += 10

    def _apply_to_version(self):
        self.ensure_one()
        ver = self.version_id
        excl = [
            ln.page_key
            for ln in self.line_ids
            if ln.page_key and not ln.include_page
        ]
        ver.write({
            "print_company_name": (self.print_company_name or "").strip() or False,
            "print_show_page_numbers": bool(self.print_show_page_numbers),
            "print_exclude_keys": ",".join(excl),
        })
        self.env["ir.config_parameter"].sudo().set_param(
            "cpabooks_afg.print_show_page_numbers",
            "1" if self.print_show_page_numbers else "0",
        )
        return ver

    def action_save_setup(self):
        self._apply_to_version()
        return {"type": "ir.actions.act_window_close"}

    def action_preview_pdf(self):
        ver = self._apply_to_version()
        return ver.action_print_audit_report_pdf()

    def action_preview_xlsx(self):
        ver = self._apply_to_version()
        return ver.action_export_audit_xlsx()

    def action_preview_docx(self):
        ver = self._apply_to_version()
        return ver.action_export_audit_docx()

    def action_include_all(self):
        self.line_ids.write({"include_page": True})
        return self._reopen()

    def action_exclude_fta(self):
        self.line_ids.filtered(lambda l: l.page_key == "fta").write({
            "include_page": False,
        })
        return self._reopen()

    def _reopen(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Print Setup"),
            "res_model": "audited.financial.print.setup.wizard",
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }


class AuditedFinancialPrintSetupWizardLine(models.TransientModel):
    _name = "audited.financial.print.setup.wizard.line"
    _description = "AFG Print Setup page"
    _order = "sequence, id"

    wizard_id = fields.Many2one(
        "audited.financial.print.setup.wizard",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(default=10)
    page_key = fields.Char(required=True)
    name = fields.Char(string="Page", readonly=True)
    include_page = fields.Boolean(string="Include", default=True)
    preview_text = fields.Text(string="Preview", readonly=True)
