# -*- coding: utf-8 -*-
from odoo import models, fields, _


class CpaCdConfirmWizard(models.TransientModel):
    _name = "cpa.cd.confirm.wizard"
    _description = "Confirm cancel/delete global action"

    res_model = fields.Char(required=True)
    res_ids = fields.Char(required=True)
    method_name = fields.Char(required=True)
    note = fields.Char()

    def action_run(self):
        self.ensure_one()
        ids = [int(x) for x in (self.res_ids or "").split(",") if x.strip().isdigit()]
        model = self.env[self.res_model]
        records = model.browse(ids).exists()
        if not records:
            return model._cpa_cd_leave_action()
        method = getattr(records, self.method_name)
        result = method()
        if isinstance(result, dict) and result.get("type"):
            return result
        if "delete" in (self.method_name or ""):
            return model._cpa_cd_leave_action()
        return model._cpa_cd_web_action()
