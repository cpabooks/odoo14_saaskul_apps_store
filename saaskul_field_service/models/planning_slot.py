from odoo import api, models


class PlanningSlot(models.Model):
    _inherit = 'planning.slot'

    @api.model
    def default_get(self, fields_list):
        result = super().default_get(fields_list)
        task_id = result.get('task_id') or self.env.context.get('default_task_id')
        if task_id and 'project_id' in fields_list and not result.get('project_id'):
            result['project_id'] = self.env['project.task'].browse(task_id).project_id.id
        return result

    @api.model_create_multi
    def create(self, vals_list):
        task_ids = {vals.get('task_id') for vals in vals_list if vals.get('task_id')}
        task_project_map = {
            task.id: task.project_id.id
            for task in self.env['project.task'].browse(task_ids).exists()
        }
        for vals in vals_list:
            task_id = vals.get('task_id')
            if task_id:
                vals['project_id'] = task_project_map.get(task_id)
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('task_id'):
            vals = dict(vals)
            vals['project_id'] = self.env['project.task'].browse(vals['task_id']).project_id.id
            return super().write(vals)

        if 'project_id' not in vals:
            return super().write(vals)

        slots_with_task = self.filtered('task_id')
        slots_without_task = self - slots_with_task
        result = True

        if slots_without_task:
            result = super(PlanningSlot, slots_without_task).write(vals)

        for slot in slots_with_task:
            slot_vals = dict(vals)
            slot_vals['project_id'] = slot.task_id.project_id.id
            result = super(PlanningSlot, slot).write(slot_vals) and result

        return result

    @api.constrains('task_id', 'project_id')
    def _check_task_in_project(self):
        for slot in self.filtered('task_id'):
            expected_project = slot.task_id.project_id
            if slot.project_id != expected_project:
                slot.project_id = expected_project
    @api.onchange('employee_id', 'task_id', 'project_id')
    def _onchange_keep_project_task_synced(self):
        if self.task_id and self.project_id != self.task_id.project_id:
            self.project_id = self.task_id.project_id
