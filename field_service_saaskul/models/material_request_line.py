from odoo import api, fields, models


class MaterialRequestLine(models.Model):
    _name = 'material.request.line'
    _description = 'Material Request Line'

    task_id = fields.Many2one('project.task', string='Task', ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Product', required=True)
    description = fields.Char(string='Description')
    quantity = fields.Float(string='Quantity', default=1.0)

    task_crn_number = fields.Char(
        string='CRN No',
        compute='_compute_task_crn_number',
        store=True,
        readonly=True,
    )

    @api.depends('task_id', 'task_id.task_seq')
    def _compute_task_crn_number(self):
        for line in self:
            task = line.sudo().task_id
            line.task_crn_number = task.task_seq if task else False
    issue_move_id = fields.Many2one(
        'stock.move',
        string='Issue Move',
        copy=False,
        ondelete='set null',
    )
    quantity_done = fields.Float(string='Done Quantity', compute='get_quantity_done')
    amount_done = fields.Float(string='Amount Done', compute='get_quantity_done')
    test_quantity_issued = fields.Float(string='Test Issued Quantity', copy=False)

    def init(self):
        self.env.cr.execute("""
            ALTER TABLE material_request_line
            ADD COLUMN IF NOT EXISTS test_quantity_issued numeric
        """)

    def _has_test_quantity_issued_column(self):
        self.env.cr.execute("""
            SELECT 1
              FROM information_schema.columns
             WHERE table_name = 'material_request_line'
               AND column_name = 'test_quantity_issued'
             LIMIT 1
        """)
        return bool(self.env.cr.fetchone())

    @api.depends('task_id', 'issue_move_id', 'issue_move_id.quantity_done', 'issue_move_id.state')
    def get_quantity_done(self):
        picking_model = self.env['stock.picking']
        has_issue_task_field = 'issue_project_task_id' in picking_model._fields
        has_test_quantity_column = self._has_test_quantity_issued_column()
        for rec in self:
            rec.quantity_done = 0.0
            rec.amount_done = 0.0
            if rec.issue_move_id:
                move = rec.issue_move_id
                if move.state != 'cancel':
                    rec.quantity_done = move.quantity_done
                    if 'amount' in move._fields:
                        rec.amount_done = move.amount
                    else:
                        rec.amount_done = move.quantity_done * rec.product_id.list_price
            elif rec.task_id and has_issue_task_field:
                pickings = self.env['stock.picking'].search([
                    ('issue_project_task_id', '=', rec.task_id.id),
                    ('state', '=', 'done'),
                ])
                moves = pickings.move_ids_without_package.filtered(
                    lambda move: move.product_id.id == rec.product_id.id and move.state != 'cancel'
                )
                rec.quantity_done = sum(moves.mapped('quantity_done'))
                if moves and 'amount' in moves._fields:
                    rec.amount_done = sum(moves.mapped('amount'))
                else:
                    rec.amount_done = rec.quantity_done * rec.product_id.list_price
            if has_test_quantity_column and not rec.quantity_done and rec.test_quantity_issued:
                rec.quantity_done = rec.test_quantity_issued
                rec.amount_done = rec.test_quantity_issued * rec.product_id.list_price

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id and not self.description:
            self.description = self.product_id.display_name
