from odoo import api, fields, models

from . import res_partner_fsm  # noqa: F401,E402


class ProjectProject(models.Model):
    _inherit = 'project.project'

    is_internal_project = fields.Boolean(
        string='Internal Project',
        default=False,
        index=True,
        help='Tasks of internal projects (timesheets, time off) are never listed as CRNs.',
    )
    allow_quotations = fields.Boolean(
        string='Allow Quotations',
        compute='_compute_fsm_project_flags',
        store=True,
        readonly=False,
    )
    allow_worksheets = fields.Boolean(
        string='Worksheets',
        compute='_compute_fsm_project_flags',
        store=True,
        readonly=False,
    )

    @api.depends('is_fsm')
    def _compute_fsm_project_flags(self):
        for project in self:
            if not project._origin:
                project.allow_quotations = bool(project.is_fsm)
                project.allow_worksheets = bool(project.is_fsm)

    @api.model_create_multi
    def create(self, vals_list):
        prepared_vals_list = []
        for vals in vals_list:
            vals = dict(vals)
            vals.setdefault('is_fsm', True)
            if vals.get('is_fsm') and 'allow_quotations' not in vals:
                vals['allow_quotations'] = True
            if vals.get('is_fsm') and 'allow_timesheets' not in vals:
                vals['allow_timesheets'] = True
            prepared_vals_list.append(vals)
        return super().create(prepared_vals_list)

    @api.model
    def enable_fsm_for_all_projects(self):
        all_projects = self.with_context(active_test=False).sudo().search([])
        default_product = self.env.ref('sale_timesheet.time_product', False)
        all_projects.filtered(lambda project: project.is_fsm and not project.allow_quotations).write({
            'allow_quotations': True,
        })

        fsm_projects_missing_timesheets = all_projects.filtered(
            lambda project: project.is_fsm and not project.allow_timesheets
        )
        fsm_projects_missing_product = fsm_projects_missing_timesheets.filtered(
            lambda project: not project.timesheet_product_id
        )
        if default_product and fsm_projects_missing_product:
            fsm_projects_missing_product.write({
                'timesheet_product_id': default_product.id,
            })
        fsm_projects_missing_timesheets.write({
            'allow_timesheets': True,
        })

        projects = all_projects.filtered(lambda project: not project.is_fsm)
        if projects:
            vals = {
                'is_fsm': True,
                'allow_quotations': True,
                'allow_timesheets': True,
                'sale_line_id': False,
            }
            projects_needing_product = projects.filtered(
                lambda project: not project.timesheet_product_id
            )
            if default_product and projects_needing_product:
                projects_needing_product.write(dict(vals, timesheet_product_id=default_product.id))
            (projects - projects_needing_product).write(vals)
        return True
