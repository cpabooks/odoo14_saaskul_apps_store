# -*- coding: utf-8 -*-

from odoo import fields, models, api, _


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    # project_id = fields.Many2one('project.project', string='Job Order')

    def action_create_qc_from_picking(self):
        action = self.env["ir.actions.actions"]._for_xml_id("saaskul_switchgear.action_qc_from_picking")
        action['context'] = {
            'search_default_picking_id': self.id,
            'default_picking_id': self.id,
        }
        return action
