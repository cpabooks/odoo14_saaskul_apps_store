# -*- coding: utf-8 -*-
from odoo import api, models

_MONTH_SHORT = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}


class ReportCafmPpmDaily(models.AbstractModel):
    _name = "report.cpabooks_cafm.report_cafm_ppm_daily_list"
    _description = "Technician daily PPM list (PDF)"

    @api.model
    def _get_report_values(self, docids, data=None):
        wizard = self.env["cafm.ppm.daily.list.wizard"].browse(docids)
        wizard.ensure_one()
        y, m = wizard.report_date.year, wizard.report_date.month
        domain = [
            ("year", "=", y),
            ("month", "=", m),
            ("state", "=", "planned"),
        ]
        slots = self.env["cpabooks.cafm.ppm.slot"].search(domain, order="ppm_id, id")
        if wizard.supervisor_id:
            slots = slots.filtered(lambda s: s.ppm_id.supervisor_id == wizard.supervisor_id)
        lines = []
        for s in slots:
            ppm = s.ppm_id
            proj = ppm.project_id
            amc = proj.cafm_amc_ids[:1]
            client = ""
            if amc and amc.client_id:
                client = amc.client_id.name
            elif proj.partner_id:
                client = proj.partner_id.name or ""
            lines.append({
                "slot": s,
                "ppm": ppm,
                "project": proj,
                "unit_name": ppm.unit_id.name if ppm.unit_id else "",
                "client": client,
                "area": proj.cafm_location or "",
                "supervisor": ppm.supervisor_id.name if ppm.supervisor_id else "",
                "month_label": _MONTH_SHORT.get(s.month, str(s.month)),
            })
        return {
            "doc_ids": docids,
            "doc_model": "cafm.ppm.daily.list.wizard",
            "docs": wizard,
            "lines": lines,
        }
