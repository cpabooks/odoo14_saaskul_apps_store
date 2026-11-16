from odoo import fields, models


class ClientLetterTemplate(models.Model):
    _name = "client.letter.template"
    _description = "Client Letter Template"
    _order = "sequence, id"

    name = fields.Char(required=True)
    code = fields.Char(required=True, index=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    subject_template = fields.Char()
    body_template = fields.Html(sanitize=False)
    email_template = fields.Html(sanitize=False)
    whatsapp_template = fields.Text()
