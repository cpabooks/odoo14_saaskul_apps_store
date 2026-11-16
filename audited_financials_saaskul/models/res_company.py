# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models
from odoo.tools import SQL

_logger = logging.getLogger(__name__)

AFG_MODULE = "audited_financials_saaskul"


class ResCompany(models.Model):
    _inherit = "res.company"

    afg_auditor_firm = fields.Char(
        string="Audit firm",
        help="Printed at the end of the Independent Auditor's Report, e.g. 'ABC & Co.'.",
    )
    afg_auditor_signatory = fields.Char(
        string="Signing partner",
        help="Name of the auditor who signs the report.",
    )
    afg_auditor_designation = fields.Char(
        string="Designation",
        default="Chartered Accountants",
        help="Printed after the firm name, e.g. 'Chartered Accountants'.",
    )
    afg_auditor_licence = fields.Char(
        string="Licence number",
        help="Audit licence / registration number. Leave empty to skip the line.",
    )

    def _register_hook(self):
        super()._register_hook()
        self._afg_add_missing_columns()

    @api.model
    def _afg_add_missing_columns(self):
        """Create columns for this module's fields that the database does not have yet.

        Odoo only adds a column when the module that defines the field is installed
        or upgraded. If newer code of this module runs on a database that was not
        upgraded, every read of res.company fails with UndefinedColumn, which breaks
        the whole web client. This runs on every registry load, before any request.
        """
        cr = self.env.cr
        if cr.readonly:
            return
        wanted = {}
        for model_name in self.env.registry:
            Model = self.env[model_name]
            if Model._abstract or not Model._auto or Model._table_query:
                continue
            for field in Model._fields.values():
                if (
                    field.store
                    and field.column_type
                    and not field.inherited
                    and AFG_MODULE in field._modules
                ):
                    wanted.setdefault(Model._table, (Model, []))[1].append(field)
        if not wanted:
            return
        cr.execute(
            """
            SELECT table_name, column_name
              FROM information_schema.columns
             WHERE table_schema = current_schema()
               AND table_name = ANY(%s)
            """,
            [list(wanted)],
        )
        existing = {}
        for table, column in cr.fetchall():
            existing.setdefault(table, set()).add(column)
        # res.company first: defaults of other models may read the current company.
        tables = sorted(wanted, key=lambda table: table != self._table)
        for table in tables:
            if table not in existing:
                continue
            Model, model_fields = wanted[table]
            for field in model_fields:
                if field.name in existing[table]:
                    continue
                try:
                    with cr.savepoint():
                        cr.execute(SQL(
                            "ALTER TABLE %s ADD COLUMN IF NOT EXISTS %s %s %s",
                            SQL.identifier(table),
                            SQL.identifier(field.name),
                            SQL(field.column_type[1]),
                            SQL("DEFAULT false" if field.column_type[1].upper() == "BOOLEAN" else ""),
                        ))
                        Model.with_context(prefetch_fields=False)._init_column(field.name)
                except Exception:
                    _logger.exception(
                        "audited_financials: could not add missing column %s.%s", table, field.name
                    )
                    continue
                existing[table].add(field.name)
                _logger.warning(
                    "audited_financials: added missing column %s.%s. Upgrade the module "
                    "from Apps to finish the update.", table, field.name,
                )

    def _afg_auditor_lines(self):
        """Sign-off lines of the auditor's report. Empty fields print nothing."""
        self.ensure_one()
        firm = (self.afg_auditor_firm or "").strip()
        signatory = (self.afg_auditor_signatory or "").strip()
        designation = (self.afg_auditor_designation or "").strip()
        licence = (self.afg_auditor_licence or "").strip()
        lines = []
        if firm:
            lines.append("For %s" % firm.upper())
        if signatory:
            lines.append(signatory)
        if firm:
            lines.append(", ".join(part for part in (firm, designation) if part))
        if licence:
            lines.append("LICENCE No. %s" % licence)
        return lines
