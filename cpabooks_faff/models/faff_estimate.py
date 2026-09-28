# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class FaffEstimate(models.Model):
    _name = "cpabooks.faff.estimate"
    _description = "FAFF Estimation / BOQ"
    _order = "id desc"

    name = fields.Char(required=True, default="New")
    job_id = fields.Many2one(
        "cpabooks.faff.job", required=True, ondelete="cascade", index=True
    )
    company_id = fields.Many2one(related="job_id.company_id", store=True)
    currency_id = fields.Many2one(related="job_id.currency_id", store=True)
    partner_id = fields.Many2one(related="job_id.partner_id", store=True)
    date = fields.Date(default=fields.Date.context_today)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("saved", "Saved"),
            ("approved", "Approved"),
            ("done", "Done"),
            ("cancel", "Cancelled"),
        ],
        default="draft",
    )
    line_ids = fields.One2many(
        "cpabooks.faff.estimate.line", "estimate_id", string="BOQ Lines"
    )
    notes = fields.Text()

    total_material_cost = fields.Monetary(compute="_compute_totals", store=True)
    total_labour_cost = fields.Monetary(compute="_compute_totals", store=True)
    total_equipment_cost = fields.Monetary(compute="_compute_totals", store=True)
    total_subcontract_cost = fields.Monetary(compute="_compute_totals", store=True)
    total_other_cost = fields.Monetary(compute="_compute_totals", store=True)
    total_cost = fields.Monetary(
        string="Total Estimated Cost", compute="_compute_totals", store=True
    )
    selling_amount = fields.Monetary(
        string="Selling Price", compute="_compute_totals", store=True
    )
    expected_profit = fields.Monetary(compute="_compute_totals", store=True)
    margin_percent = fields.Float(string="Margin %", compute="_compute_totals", store=True)

    @api.model
    def create(self, vals):
        if vals.get("name", "New") == "New":
            vals["name"] = (
                self.env["ir.sequence"].next_by_code("cpabooks.faff.estimate")
                or "EST/00001"
            )
        return super().create(vals)

    @api.depends(
        "line_ids.material_cost",
        "line_ids.labour_cost",
        "line_ids.equipment_cost",
        "line_ids.subcontract_cost",
        "line_ids.other_cost",
        "line_ids.total_cost",
        "line_ids.total_selling_price",
    )
    def _compute_totals(self):
        for est in self:
            lines = est.line_ids
            est.total_material_cost = sum(lines.mapped("material_cost"))
            est.total_labour_cost = sum(lines.mapped("labour_cost"))
            est.total_equipment_cost = sum(lines.mapped("equipment_cost"))
            est.total_subcontract_cost = sum(lines.mapped("subcontract_cost"))
            est.total_other_cost = sum(lines.mapped("other_cost"))
            est.total_cost = sum(lines.mapped("total_cost"))
            est.selling_amount = sum(lines.mapped("total_selling_price"))
            est.expected_profit = est.selling_amount - est.total_cost
            est.margin_percent = (
                (est.expected_profit / est.selling_amount * 100.0)
                if est.selling_amount
                else 0.0
            )

    def action_save_estimation(self):
        self.write({"state": "saved"})

    def action_approve_estimation(self):
        for est in self:
            if not est.line_ids:
                raise UserError(_("Add at least one BOQ line before approval."))
            est.state = "approved"
            if est.job_id.stage in ("crm", "inspection", "estimation"):
                est.job_id.stage = "estimation"
                est.job_id.status = "in_progress"


class FaffEstimateLine(models.Model):
    _name = "cpabooks.faff.estimate.line"
    _description = "FAFF Estimation Line"

    estimate_id = fields.Many2one(
        "cpabooks.faff.estimate", required=True, ondelete="cascade"
    )
    job_id = fields.Many2one(
        related="estimate_id.job_id", store=True, index=True, string="FAFF Job"
    )
    partner_id = fields.Many2one(
        related="estimate_id.partner_id", store=True, string="Customer"
    )
    company_id = fields.Many2one(related="estimate_id.company_id", store=True)
    currency_id = fields.Many2one(related="estimate_id.currency_id")
    product_id = fields.Many2one("product.product", string="Product")
    name = fields.Char(string="Description", required=True)
    category = fields.Char()
    product_uom_qty = fields.Float(string="Qty", default=1.0)
    product_uom_id = fields.Many2one(
        "uom.uom", string="UOM", default=lambda self: self.env.ref("uom.product_uom_unit", raise_if_not_found=False)
    )
    material_cost = fields.Monetary(default=0.0)
    labour_cost = fields.Monetary(default=0.0)
    equipment_cost = fields.Monetary(default=0.0)
    subcontract_cost = fields.Monetary(default=0.0)
    other_cost = fields.Monetary(default=0.0)
    total_cost = fields.Monetary(compute="_compute_line_amounts", store=True)
    margin_percent = fields.Float(string="Margin %", default=30.0)
    selling_price = fields.Monetary(string="Unit Selling Price", default=0.0)
    tax_ids = fields.Many2many("account.tax", string="Taxes")
    total_selling_price = fields.Monetary(
        string="Total Selling Price", compute="_compute_line_amounts", store=True
    )

    @api.onchange("product_id")
    def _onchange_product_id(self):
        if self.product_id:
            self.name = self.product_id.display_name
            self.product_uom_id = self.product_id.uom_id
            self.material_cost = self.product_id.standard_price
            self._onchange_costs_margin()

    @api.onchange(
        "material_cost",
        "labour_cost",
        "equipment_cost",
        "subcontract_cost",
        "other_cost",
        "margin_percent",
        "product_uom_qty",
    )
    def _onchange_costs_margin(self):
        unit_cost = (
            (self.material_cost or 0.0)
            + (self.labour_cost or 0.0)
            + (self.equipment_cost or 0.0)
            + (self.subcontract_cost or 0.0)
            + (self.other_cost or 0.0)
        )
        margin = self.margin_percent or 0.0
        self.selling_price = unit_cost * (1.0 + margin / 100.0)

    @api.depends(
        "product_uom_qty",
        "material_cost",
        "labour_cost",
        "equipment_cost",
        "subcontract_cost",
        "other_cost",
        "selling_price",
    )
    def _compute_line_amounts(self):
        for line in self:
            unit_cost = (
                (line.material_cost or 0.0)
                + (line.labour_cost or 0.0)
                + (line.equipment_cost or 0.0)
                + (line.subcontract_cost or 0.0)
                + (line.other_cost or 0.0)
            )
            qty = line.product_uom_qty or 0.0
            line.total_cost = unit_cost * qty
            line.total_selling_price = (line.selling_price or 0.0) * qty
