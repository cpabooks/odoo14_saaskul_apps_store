# -*- coding: utf-8 -*-
from odoo import fields, models


class FaffDefaultTask(models.Model):
    _name = "cpabooks.faff.default.task"
    _description = "FAFF Default Project Task Template"
    _order = "sequence, id"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    is_mandatory = fields.Boolean(
        string="Mandatory",
        help="Job cannot complete until this task is done (unless Manager override).",
    )
    description = fields.Text()
    company_id = fields.Many2one(
        "res.company", default=lambda self: self.env.company
    )
