# -*- coding: utf-8 -*-
from odoo import fields, models


class CrmLead(models.Model):
    _inherit = "crm.lead"

    faff_job_id = fields.Many2one("cpabooks.faff.job", string="FAFF Job", copy=False)
    faff_job_count = fields.Integer(compute="_compute_faff_job_count")

    def _compute_faff_job_count(self):
        for lead in self:
            lead.faff_job_count = self.env["cpabooks.faff.job"].search_count(
                [("crm_lead_id", "=", lead.id)]
            )

    def action_start_faff_process(self):
        self.ensure_one()
        Job = self.env["cpabooks.faff.job"]
        job = self.faff_job_id or Job.search([("crm_lead_id", "=", self.id)], limit=1)
        if not job:
            partner = self.partner_id
            if not partner and self.partner_name:
                partner = self.env["res.partner"].create(
                    {
                        "name": self.partner_name,
                        "email": self.email_from,
                        "phone": self.phone or self.mobile,
                    }
                )
                self.partner_id = partner
            job = Job.create(
                {
                    "crm_lead_id": self.id,
                    "partner_id": partner.id if partner else self.env.user.partner_id.id,
                    "contact_id": self.partner_id.id if self.partner_id else False,
                    "mobile": self.mobile or self.phone,
                    "email": self.email_from,
                    "site_name": self.name,
                    "salesperson_id": self.user_id.id or self.env.user.id,
                    "description": self.description,
                    "stage": "crm",
                    "wizard_step": 0,
                }
            )
            self.faff_job_id = job.id
        # Always start/resume from saved step — step 0 is CRM, then Site Visit.
        wizard = self.env["cpabooks.faff.job.wizard"].create(
            {"job_id": job.id, "step_index": job.wizard_step or 0}
        )
        wizard._load_from_job()
        return wizard._reopen()
