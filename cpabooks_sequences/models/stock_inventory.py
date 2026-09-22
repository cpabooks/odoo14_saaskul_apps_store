# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError


class StockInventory(models.Model):
    _inherit = 'stock.inventory'

    saj_number = fields.Char(
        string='SAJ Number',
        copy=False,
        index=True,
        readonly=True,
        help='Stock Adjustment Journal number (SAJ sequence).',
    )

    def _cpabooks_saj_sequence_date(self):
        self.ensure_one()
        if self.accounting_date:
            return self.accounting_date
        if self.date:
            return fields.Date.to_date(self.date)
        return fields.Date.context_today(self)

    def _cpabooks_ensure_saj_sequence(self):
        """Create/repair company SAJ ir.sequence (must have usable next number)."""
        self.ensure_one()
        company = self.company_id or self.env.company
        Sequence = self.env['ir.sequence'].sudo()
        existing = Sequence.search([
            ('sequence_for', '=', 'stock_adjustment'),
            ('company_id', '=', company.id),
        ], limit=1)
        if existing:
            self._cpabooks_repair_saj_sequence(existing)
            return existing
        Prefix = self.env['set.company.prefix']
        prefix = getattr(company, 'cpabooks_sequence_prefix', None) or ''
        granularity = getattr(company, 'cpabooks_sequence_granularity', None) or 'yearly'
        year_digits = getattr(company, 'cpabooks_sequence_year_digits', None) or '4'
        number_digits = getattr(company, 'cpabooks_sequence_number_digits', None) or '5'
        Prefix.apply_prefix_for_company(
            company,
            prefix,
            granularity=granularity,
            year_digits=year_digits,
            number_digits=number_digits,
            update_existing=False,
            create_missing=True,
        )
        existing = Sequence.search([
            ('sequence_for', '=', 'stock_adjustment'),
            ('company_id', '=', company.id),
        ], limit=1)
        if existing:
            self._cpabooks_repair_saj_sequence(existing)
        return existing

    def _cpabooks_repair_saj_sequence(self, seq):
        """SQL-created standard sequences may lack ir_sequence_<id> PG object."""
        if not seq or seq.implementation != 'standard':
            return seq
        cr = self.env.cr
        # Odoo create uses zero-padded name; predict uses unpadded — check both.
        names = {
            'ir_sequence_%s' % seq.id,
            'ir_sequence_%03d' % seq.id,
        }
        cr.execute(
            """
            SELECT c.relname
              FROM pg_class c
              JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE c.relkind = 'S'
               AND c.relname = ANY(%s)
            """,
            (list(names),),
        )
        found = {row[0] for row in cr.fetchall()}
        if names & found:
            return seq
        # Prefer no_gap: no PG dependency, safe after raw INSERT migrations.
        seq.with_context(cpabooks_sequence_force_write=True).write({
            'implementation': 'no_gap',
        })
        return seq

    def _cpabooks_assign_saj_number(self):
        for inventory in self:
            if inventory.saj_number:
                continue
            inv = inventory.with_company(inventory.company_id)
            inv._cpabooks_ensure_saj_sequence()
            saj = inv.env['ir.sequence'].next_by_sequence_for(
                'stock_adjustment',
                sequence_date=inv._cpabooks_saj_sequence_date(),
            )
            if not saj:
                raise UserError(_(
                    'No SAJ (Stock Adjustment Journal) sequence found for company %s.\n'
                    'Open CPABooks Re-Sequences → Set Company Prefix and Apply once.'
                ) % (inventory.company_id.display_name,))
            inventory.saj_number = saj

    def action_validate(self):
        for inventory in self:
            if inventory.state == 'confirm' and not inventory.saj_number:
                inventory._cpabooks_assign_saj_number()
        return super().action_validate()
