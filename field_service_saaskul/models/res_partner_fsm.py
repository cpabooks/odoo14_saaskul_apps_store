# -*- coding: utf-8 -*-
"""Partner fields for FSM; loaded from project_project.py (first models import) so fields
exist before XML views in this module are validated."""
from odoo import fields, models


class ResPartnerFsm(models.Model):
    _inherit = 'res.partner'

    customer_invoice_type_id = fields.Many2one(
        'invoice.type',
        string='Invoice Type',
        help='Used for Field Service tasks: automatic Ref. Invoice is suggested only when '
        'this is set to AMC on the commercial customer.',
    )
