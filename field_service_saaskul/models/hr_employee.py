from odoo import api, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    @api.model
    def _fsm_employee_picker_active(self):
        ctx = self.env.context
        return bool(
            ctx.get('fsm_mode')
            or ctx.get('fsm_employee_picker')
            or (ctx.get('default_task_id') and ctx.get('default_project_id'))
        )

    @api.model
    def search(self, args, offset=0, limit=None, order=None, count=False):
        if self._fsm_employee_picker_active():
            return super(HrEmployee, self.sudo()).search(
                args, offset=offset, limit=limit, order=order, count=count
            )
        return super().search(args, offset=offset, limit=limit, order=order, count=count)

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        if self._fsm_employee_picker_active():
            return super(HrEmployee, self.sudo()).name_search(
                name, args=args, operator=operator, limit=limit
            )
        return super().name_search(name, args=args, operator=operator, limit=limit)

    def read(self, fields=None, load='_classic_read'):
        if self._fsm_employee_picker_active():
            return super(HrEmployee, self.sudo()).read(fields, load=load)
        return super().read(fields, load=load)
