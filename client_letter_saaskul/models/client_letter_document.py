from odoo import api, fields, models


class ClientLetterDocument(models.Model):
    _name = "client.letter.document"
    _description = "Document / Letter"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(default="New", readonly=True, copy=False, tracking=True)
    source_ref = fields.Reference(
        selection="_selection_source_models",
        string="Source Document",
        tracking=True,
    )
    template_id = fields.Many2one("client.letter.template", string="Letter Type", tracking=True)
    partner_id = fields.Many2one("res.partner", string="Client", tracking=True)
    partner_email = fields.Char(string="Email")
    company_id = fields.Many2one("res.company", string="Company", default=lambda self: self.env.company, required=True)
    crm_number = fields.Char(string="CRM No.")
    quotation_number = fields.Char(string="Quotation No.")
    invoice_number = fields.Char(string="Invoice No.")
    estimation_number = fields.Char(string="Estimation Ref.")
    client_lpo_number = fields.Char(string="Client LPO/PO No.")
    project_name = fields.Char(string="Project Name")
    client_name = fields.Char(string="Client Name")
    attention_to = fields.Char(string="Attention")
    customer_address = fields.Text(string="Customer Address")
    customer_phone = fields.Char(string="Phone")
    customer_email = fields.Char(string="Customer Email")
    customer_website = fields.Char(string="Website")
    letter_date = fields.Date(string="Date")
    company_name = fields.Char(string="Company Name")
    subject = fields.Char(required=True, tracking=True)
    letter_body = fields.Html(string="Letter Body", sanitize=False)
    email_body = fields.Html(string="Email Body", sanitize=False)
    whatsapp_message = fields.Text(string="WhatsApp Message")
    attachment_ids = fields.Many2many(
        "ir.attachment",
        "client_letter_document_attachment_rel",
        "document_id",
        "attachment_id",
        string="Attachments",
    )

    @api.model
    def _selection_source_models(self):
        return self.env["client.letter.wizard"]._selection_source_models()

    @api.model
    def create(self, vals):
        if not vals.get("name") or vals.get("name") == "New":
            vals["name"] = self.env["ir.sequence"].next_by_code("client.letter.document") or "Msg-001"
        return super().create(vals)
