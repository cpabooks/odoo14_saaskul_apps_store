# -*- coding: utf-8 -*-
from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    faff_job_id = fields.Many2one(
        "cpabooks.faff.job", string="FAFF Job", copy=False, index=True
    )
