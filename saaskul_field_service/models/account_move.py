# -*- coding: utf-8 -*-

from odoo import api, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    @api.model_create_multi
    def create(self, vals_list):
        moves = super().create(vals_list)
        moves._cpabooks_refresh_linked_fsm_tasks()
        return moves

    def write(self, vals):
        res = super().write(vals)
        if {'state', 'name', 'move_type'} & set(vals):
            self._cpabooks_refresh_linked_fsm_tasks()
        return res

    def _cpabooks_refresh_linked_fsm_tasks(self):
        if not self.env.registry.get('sale.order'):
            return
        orders = self.env['sale.order'].search([
            ('invoice_ids', 'in', self.ids),
            ('task_id', '!=', False),
        ])
        tasks = orders.mapped('task_id').filtered('is_fsm')
        if tasks and hasattr(tasks, '_cpabooks_refresh_fsm_quotation_display'):
            tasks._cpabooks_refresh_fsm_quotation_display()
