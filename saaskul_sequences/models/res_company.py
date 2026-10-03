# -*- coding: utf-8 -*-
from odoo import fields, models
from odoo.tools.sql import column_exists, create_column


class ResCompany(models.Model):
    _inherit = "res.company"

    # Owned here so Sequences works without saaskul_settings_company_setup.
    # company_setup may redefine the same Char (compatible inherit).
    saaskul_sequence_prefix = fields.Char(
        string="Document Sequence Prefix",
        help="Company code used in Saaskul document sequences (e.g. CRM/CPA/2026/00001).",
    )
    saaskul_sequence_granularity = fields.Selection(
        [
            ("yearly", "Yearly (resets each year)"),
            ("monthly", "Monthly (resets each month)"),
        ],
        string="Document Sequence Period",
        default="yearly",
        help="Yearly: DOC/PREFIX/YEAR/00001. Monthly: DOC/PREFIX/YEAR/MONTH/00001.",
    )
    saaskul_sequence_year_digits = fields.Selection(
        [
            ("4", "4-digit year (2026)"),
            ("2", "2-digit year (26)"),
        ],
        string="Year Format in Sequences",
        default="4",
    )
    saaskul_sequence_number_digits = fields.Selection(
        [
            ("4", "4-digit number (0001)"),
            ("5", "5-digit number (00001)"),
        ],
        string="Sequence Number Length",
        default="5",
    )

    def _ensure_sequence_columns(self):
        """Create columns even when module is already 'installed' but schema is stale."""
        cr = self.env.cr
        for col, coltype in (
            ("saaskul_sequence_prefix", "varchar"),
            ("saaskul_sequence_granularity", "varchar"),
            ("saaskul_sequence_year_digits", "varchar"),
            ("saaskul_sequence_number_digits", "varchar"),
        ):
            if not column_exists(cr, "res_company", col):
                create_column(cr, "res_company", col, coltype)
        cr.execute(
            "UPDATE res_company SET saaskul_sequence_number_digits = '5' "
            "WHERE saaskul_sequence_number_digits IS NULL"
        )

    def _auto_init(self):
        self._ensure_sequence_columns()
        return super()._auto_init()

    def _register_hook(self):
        # Harden: missing columns must not take down the whole DB UI.
        try:
            self._ensure_sequence_columns()
        except Exception:
            pass
        return super()._register_hook()
