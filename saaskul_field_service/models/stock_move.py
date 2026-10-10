from odoo import api, fields, models


class StockMove(models.Model):
    _inherit = 'stock.move'

    picking_issue_crn_number = fields.Char(
        related='picking_id.issue_crn_number',
        string='CRN No',
        readonly=True,
        store=True,
    )
    picking_issue_task_id = fields.Many2one(
        related='picking_id.issue_project_task_id',
        string='CRN No',
        readonly=True,
        store=True,
        index=True,
    )
    picking_issue_customer_id = fields.Many2one(
        related='picking_id.issue_customer_id',
        string='Customer',
        readonly=True,
        store=True,
        index=True,
    )
    picking_issue_source_document = fields.Char(
        related='picking_id.issue_source_document',
        string='Source Document',
        readonly=True,
        store=True,
    )
    use_fsm_issue_operations_ui = fields.Boolean(
        related='picking_id.use_fsm_issue_operations_ui',
        readonly=True,
    )

    @api.depends(
        'has_tracking',
        'picking_id',
        'picking_id.issue_project_task_id',
        'picking_id.picking_type_id',
        'picking_id.picking_type_id.show_operations',
        'state',
    )
    def _compute_show_details_visible(self):
        super()._compute_show_details_visible()
        for move in self:
            if move.picking_id.issue_project_task_id:
                move.show_details_visible = True
