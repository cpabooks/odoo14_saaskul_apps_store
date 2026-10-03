# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class CafmVarWorkRemark(models.Model):
    _name = 'cpabooks.cafm.var.work.remark'
    _description = 'VAR Work Remark History'
    _order = 'sr asc, id desc'

    var_work_id = fields.Many2one(
        'cpabooks.cafm.var.work', string='VAR Work', required=True, ondelete='cascade', index=True,
    )
    sr = fields.Integer(string='Sr.', default=1, index=True)
    name = fields.Text(string='Remark', required=True)
    user_id = fields.Many2one(
        'res.users', string='Updated By', default=lambda self: self.env.user, required=True,
    )
    remark_date = fields.Datetime(
        string='Date', default=fields.Datetime.now, required=True,
    )
    source = fields.Selection([
        ('form', 'Form'),
        ('chatter', 'Chatter'),
    ], string='Source', default='form')
    company_id = fields.Many2one(
        related='var_work_id.company_id', store=True, readonly=True,
    )

    @api.model
    def create(self, vals):
        work_id = vals.get('var_work_id')
        if work_id:
            # Latest remark always Sr. 1 — shift older lines down
            older = self.search([('var_work_id', '=', work_id)])
            for line in older.sorted(key=lambda r: r.sr):
                line.sr = (line.sr or 0) + 1
            vals['sr'] = 1
        if not vals.get('user_id'):
            vals['user_id'] = self.env.uid
        if not vals.get('remark_date'):
            vals['remark_date'] = fields.Datetime.now()
        return super().create(vals)

    def unlink(self):
        works = self.mapped('var_work_id')
        res = super().unlink()
        for work in works:
            work._renumber_remarks()
        return res
