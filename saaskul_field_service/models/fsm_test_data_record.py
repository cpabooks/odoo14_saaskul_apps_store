from odoo import fields, models


class FsmTestDataRecord(models.Model):
    _name = 'cpabooks.fsm.test.data.record'
    _description = 'FSM Test Data Record'
    _order = 'id desc'

    model_name = fields.Char(required=True, index=True)
    res_id = fields.Integer(required=True, index=True)
    display_name = fields.Char()

