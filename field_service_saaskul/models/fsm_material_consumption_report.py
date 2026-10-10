from odoo import fields, models, tools


class FsmMaterialConsumptionReport(models.Model):
    _name = 'fsm.material.consumption.report'
    _description = 'FSM Material Consumption Analysis'
    _auto = False
    _rec_name = 'product_id'
    _order = 'quantity_issued desc, id desc'

    material_line_id = fields.Many2one('material.request.line', string='Material Request Line', readonly=True)
    task_id = fields.Many2one('project.task', string='CRN No', readonly=True)
    project_id = fields.Many2one('project.project', string='Project', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Customer', readonly=True)
    site_location = fields.Many2one('site.location', string='Location', readonly=True)
    complaint_type = fields.Selection([
        ('amc', 'AMC'),
        ('others', 'Others'),
        ('warranty', 'Warranty'),
        ('service', 'Service'),
        ('new_installation', 'New Installation'),
        ('new_inquiry', 'New Inquiry'),
        ('site_visit', 'Site Visit'),
    ], string='Complaint Type', readonly=True)
    fsm_stage_group = fields.Selection([
        ('registered', '1. Registered'),
        ('site_visited', '2. Site Visited (i)'),
        ('qty_issued', '3. Qtn Issued and waiting for Approval'),
        ('qty_approved', '4. QTN Approved'),
        ('in_progress', '5. Work in Progress'),
        ('waiting_for_invoice', '6. Job Complete Waiting for Invoice'),
        ('job_completed', '7. Job Completed-FOC'),
        ('job_completed_invoiced', '8. Job Completed & Invoiced'),
        ('approved', '9. Approved'),
    ], string='Stage', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True)
    product_id = fields.Many2one('product.product', string='Material', readonly=True)
    product_categ_id = fields.Many2one('product.category', string='Material Category', readonly=True)
    quantity_requested = fields.Float(string='Requested Quantity', readonly=True)
    quantity_issued = fields.Float(string='Issued Quantity', readonly=True)
    remaining_qty = fields.Float(string='Remaining Quantity', readonly=True)
    issued_value = fields.Float(string='Issued Value', readonly=True)
    line_count = fields.Integer(string='Lines', readonly=True)

    def init(self):
        self.env.cr.execute("""
            ALTER TABLE material_request_line
            ADD COLUMN IF NOT EXISTS test_quantity_issued numeric
        """)
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    mrl.id AS id,
                    mrl.id AS material_line_id,
                    mrl.task_id AS task_id,
                    task.project_id AS project_id,
                    COALESCE(task.partner_id, project.partner_id) AS partner_id,
                    task.site_location AS site_location,
                    task.complaint_type AS complaint_type,
                    task.fsm_stage_group AS fsm_stage_group,
                    task.company_id AS company_id,
                    mrl.product_id AS product_id,
                    template.categ_id AS product_categ_id,
                    COALESCE(mrl.quantity, 0.0) AS quantity_requested,
                    COALESCE(issued.quantity_issued, mrl.test_quantity_issued, 0.0) AS quantity_issued,
                    GREATEST(COALESCE(mrl.quantity, 0.0) - COALESCE(issued.quantity_issued, mrl.test_quantity_issued, 0.0), 0.0) AS remaining_qty,
                    COALESCE(issued.quantity_issued, mrl.test_quantity_issued, 0.0) * COALESCE(template.list_price, 0.0) AS issued_value,
                    1 AS line_count
                FROM material_request_line mrl
                LEFT JOIN project_task task ON task.id = mrl.task_id
                LEFT JOIN project_project project ON project.id = task.project_id
                LEFT JOIN product_product product ON product.id = mrl.product_id
                LEFT JOIN product_template template ON template.id = product.product_tmpl_id
                LEFT JOIN (
                    SELECT
                        picking.issue_project_task_id AS task_id,
                        move.product_id AS product_id,
                        SUM(COALESCE(move_line.qty_done, 0.0)) AS quantity_issued
                    FROM stock_move move
                    JOIN stock_move_line move_line ON move_line.move_id = move.id
                    JOIN stock_picking picking ON picking.id = move.picking_id
                    WHERE picking.state = 'done'
                      AND move.state != 'cancel'
                      AND picking.issue_project_task_id IS NOT NULL
                    GROUP BY picking.issue_project_task_id, move.product_id
                ) issued ON issued.task_id = mrl.task_id AND issued.product_id = mrl.product_id
                WHERE mrl.task_id IS NOT NULL
            )
        """ % self._table)
