from odoo import models, fields, api,_
from odoo.exceptions import ValidationError


class ProjectInheritance(models.Model):
    _inherit = 'project.project'

    name = fields.Char("Name", index=True, required=True, tracking=True,default=lambda self:self.env['ir.sequence'].next_by_sequence_for('project'))

    # @api.model
    # def create(self, vals_list):
    #     print(vals_list)
    #     res = super(ProjectInheritance, self).create(vals_list)
    #     get_sequence = self.env['ir.sequence'].next_by_sequence_for('project')
    #     if not get_sequence:
    #         raise ValidationError(_("Sequence is not set for Project"))
    #     res.name = get_sequence or _('/')
    #     return res