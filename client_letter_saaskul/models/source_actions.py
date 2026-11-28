from odoo import models


def _client_letter_action(record):
    record.ensure_one()
    return {
        "name": "Client Letter",
        "type": "ir.actions.act_window",
        "res_model": "client.letter.wizard",
        "view_mode": "form",
        "target": "new",
        "context": {
            "default_source_ref": "%s,%s" % (record._name, record.id),
        },
    }


class CrmLead(models.Model):
    _inherit = "crm.lead"

    def action_open_client_letter_wizard(self):
        return _client_letter_action(self)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def action_open_client_letter_wizard(self):
        return _client_letter_action(self)


class AccountMove(models.Model):
    _inherit = "account.move"

    def action_open_client_letter_wizard(self):
        return _client_letter_action(self)


class ProjectProject(models.Model):
    _inherit = "project.project"

    def action_open_client_letter_wizard(self):
        return _client_letter_action(self)
