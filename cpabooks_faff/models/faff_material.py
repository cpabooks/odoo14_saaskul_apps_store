# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class FaffMaterialPlan(models.Model):
    _name = "cpabooks.faff.material.plan"
    _description = "FAFF Material Requirement"
    _order = "id"

    job_id = fields.Many2one(
        "cpabooks.faff.job", required=True, ondelete="cascade", index=True
    )
    company_id = fields.Many2one(related="job_id.company_id", store=True)
    currency_id = fields.Many2one(related="job_id.currency_id")
    product_id = fields.Many2one("product.product", required=True)
    name = fields.Char(string="Description")
    product_uom_id = fields.Many2one("uom.uom", string="UOM")
    qty_required = fields.Float(string="Required", default=1.0)
    qty_available = fields.Float(
        string="Available", compute="_compute_stock", store=True
    )
    qty_reserved = fields.Float(string="Reserved", default=0.0)
    issue_qty = fields.Float(string="Issue From Store", default=0.0)
    purchase_qty = fields.Float(string="Purchase Qty", default=0.0)
    material_cost = fields.Monetary(string="Issued Cost", default=0.0)
    picking_ids = fields.Many2many(
        "stock.picking",
        "faff_material_picking_rel",
        "plan_id",
        "picking_id",
        string="Stock Issues",
    )
    purchase_order_ids = fields.Many2many(
        "purchase.order",
        "faff_material_purchase_rel",
        "plan_id",
        "purchase_id",
        string="Purchase Orders",
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("partial", "Partial"),
            ("done", "Done"),
        ],
        default="draft",
    )

    @api.onchange("product_id")
    def _onchange_product_id(self):
        if self.product_id:
            self.name = self.product_id.display_name
            self.product_uom_id = self.product_id.uom_id
            self._compute_stock()

    @api.depends("product_id", "job_id.company_id")
    def _compute_stock(self):
        for line in self:
            if not line.product_id:
                line.qty_available = 0.0
                continue
            wh = self.env["stock.warehouse"].search(
                [("company_id", "=", line.company_id.id)], limit=1
            )
            loc = wh.lot_stock_id if wh else False
            if loc:
                line.qty_available = line.product_id.with_context(
                    location=loc.id
                ).qty_available
            else:
                line.qty_available = line.product_id.qty_available

    def action_suggest_split(self):
        for line in self:
            avail = line.qty_available or 0.0
            req = line.qty_required or 0.0
            issue = min(avail, req)
            line.issue_qty = issue
            line.purchase_qty = max(req - issue, 0.0)

    def action_issue_from_store(self):
        self.ensure_one()
        if self.issue_qty <= 0:
            raise UserError(_("Set Issue From Store quantity first."))
        job = self.job_id
        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", job.company_id.id)], limit=1
        )
        if not warehouse:
            raise UserError(_("No warehouse found for this company."))
        picking_type = warehouse.out_type_id
        if not picking_type:
            raise UserError(_("Warehouse has no Delivery operation type."))
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": picking_type.id,
                "location_id": picking_type.default_location_src_id.id,
                "location_dest_id": picking_type.default_location_dest_id.id
                or self.env.ref("stock.stock_location_customers").id,
                "partner_id": job.partner_id.id,
                "origin": job.name,
                "faff_job_id": job.id,
                "move_ids_without_package": [
                    (
                        0,
                        0,
                        {
                            "name": self.name or self.product_id.display_name,
                            "product_id": self.product_id.id,
                            "product_uom_qty": self.issue_qty,
                            "product_uom": self.product_uom_id.id
                            or self.product_id.uom_id.id,
                            "location_id": picking_type.default_location_src_id.id,
                            "location_dest_id": picking_type.default_location_dest_id.id
                            or self.env.ref("stock.stock_location_customers").id,
                        },
                    )
                ],
            }
        )
        self.picking_ids = [(4, picking.id)]
        unit_cost = self.product_id.standard_price or 0.0
        self.material_cost = (self.material_cost or 0.0) + unit_cost * self.issue_qty
        self.state = "partial" if (self.purchase_qty or 0) > 0 else "done"
        return {
            "type": "ir.actions.act_window",
            "res_model": "stock.picking",
            "res_id": picking.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_create_purchase_rfq(self):
        self.ensure_one()
        if self.purchase_qty <= 0:
            raise UserError(_("Set Purchase Qty first."))
        job = self.job_id
        po = self.env["purchase.order"].create(
            {
                "partner_id": self.env["res.partner"]
                .search([("supplier_rank", ">", 0)], limit=1)
                .id
                or job.partner_id.id,
                "origin": job.name,
                "faff_job_id": job.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product_id.id,
                            "name": self.name or self.product_id.display_name,
                            "product_qty": self.purchase_qty,
                            "product_uom": self.product_uom_id.id
                            or self.product_id.uom_po_id.id,
                            "price_unit": self.product_id.standard_price,
                            "date_planned": fields.Datetime.now(),
                        },
                    )
                ],
            }
        )
        self.purchase_order_ids = [(4, po.id)]
        self.state = "partial"
        return {
            "type": "ir.actions.act_window",
            "res_model": "purchase.order",
            "res_id": po.id,
            "view_mode": "form",
            "target": "current",
        }
