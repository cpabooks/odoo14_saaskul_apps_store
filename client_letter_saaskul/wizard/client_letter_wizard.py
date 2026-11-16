from odoo import api, fields, models, _


class ClientLetterWizard(models.TransientModel):
    _name = "client.letter.wizard"
    _description = "Client Letter Wizard"

    source_ref = fields.Reference(
        selection="_selection_source_models",
        string="Source Document",
        required=True,
    )
    template_id = fields.Many2one(
        "client.letter.template",
        string="Letter Type",
        required=True,
    )
    use_source_defaults = fields.Boolean(string="Use Source Defaults", default=True)
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        default=lambda self: self.env.company,
        required=True,
    )
    partner_id = fields.Many2one("res.partner", string="Client")
    partner_email = fields.Char(string="Email")
    source_model = fields.Char(compute="_compute_source_meta")
    source_name = fields.Char(compute="_compute_source_meta")
    is_blank_template = fields.Boolean(compute="_compute_is_blank_template")
    company_stamp = fields.Binary(compute="_compute_sign_assets")
    user_signature = fields.Binary(compute="_compute_sign_assets")
    user_stamp = fields.Binary(compute="_compute_sign_assets")

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
    letter_date = fields.Date(string="Date", default=fields.Date.context_today, required=True)
    company_name = fields.Char(string="Company Name")

    subject = fields.Char(required=True)
    letter_body = fields.Html(string="Letter Body", sanitize=False)
    email_body = fields.Html(string="Email Body", sanitize=False)
    whatsapp_message = fields.Text()
    save_template_name = fields.Char(string="Save Template As")
    attachment_ids = fields.Many2many(
        "ir.attachment",
        "client_letter_wizard_attachment_rel",
        "wizard_id",
        "attachment_id",
        string="Attachments",
    )

    amount_text = fields.Char(string="Amount")
    payment_terms = fields.Char(string="Payment Terms")
    source_scope = fields.Text(string="Source Scope")
    assumptions = fields.Text(string="Assumptions / Notes")
    due_amount_text = fields.Char(string="Due Amount")
    payment_status = fields.Char(string="Payment Status")
    next_action = fields.Char(string="Next Action")

    @api.model
    def default_get(self, field_list):
        res = super().default_get(field_list)
        if not res.get("template_id"):
            template = self.env["client.letter.template"].search([], order="sequence, id", limit=1)
            if template:
                res["template_id"] = template.id
        if not res.get("company_name"):
            res["company_name"] = self.env.company.name or "CPA Books"
        return res

    @api.model
    def _selection_source_models(self):
        return [
            ("crm.lead", "CRM / Opportunity"),
            ("sale.order", "Quotation"),
            ("job.estimate", "Estimation"),
            ("account.move", "Customer Invoice"),
            ("project.project", "Project"),
        ]

    @api.depends("source_ref")
    def _compute_source_meta(self):
        for wizard in self:
            wizard.source_model = wizard.source_ref._name if wizard.source_ref else False
            wizard.source_name = wizard.source_ref.display_name if wizard.source_ref else False

    @api.depends("template_id")
    def _compute_is_blank_template(self):
        for wizard in self:
            wizard.is_blank_template = bool(wizard.template_id and wizard.template_id.code == "blank_letter")

    @api.depends("company_id")
    def _compute_sign_assets(self):
        user = self.env.user
        for wizard in self:
            company = wizard.company_id or self.env.company
            wizard.company_stamp = company.stamp if "stamp" in company._fields else False
            wizard.user_signature = user.user_signature if "user_signature" in user._fields else False
            wizard.user_stamp = user.user_stamp if "user_stamp" in user._fields else False

    @api.onchange("source_ref")
    def _onchange_source_ref(self):
        if self.use_source_defaults:
            self._populate_from_source()
        else:
            self._clear_source_defaults()
        self._apply_template_content()

    @api.onchange("template_id")
    def _onchange_template_id(self):
        for wizard in self:
            if wizard.is_blank_template:
                wizard.use_source_defaults = False
            elif not wizard.use_source_defaults:
                wizard.use_source_defaults = True
        self._apply_template_content()

    @api.onchange("use_source_defaults")
    def _onchange_use_source_defaults(self):
        for wizard in self:
            if wizard.use_source_defaults:
                wizard._populate_from_source()
                wizard._apply_template_content()
            else:
                wizard._clear_source_defaults()
                if wizard.is_blank_template:
                    wizard.subject = False
                    wizard.letter_body = False
                    wizard.email_body = False
                    wizard.whatsapp_message = False

    @api.onchange("subject")
    def _onchange_subject(self):
        for wizard in self:
            if wizard.subject and (not wizard.save_template_name or wizard.save_template_name.startswith("Template ")):
                wizard.save_template_name = wizard._default_template_name()

    def action_regenerate(self):
        self.ensure_one()
        if self.use_source_defaults:
            self._populate_from_source()
        else:
            self._clear_source_defaults()
        self._apply_template_content()
        return {
            "type": "ir.actions.act_window",
            "res_model": "client.letter.wizard",
            "view_mode": "form",
            "res_id": self.id,
            "target": "new",
        }

    def action_print_pdf(self):
        self.ensure_one()
        return self.env.ref("client_letter_saaskul.action_report_client_letter").report_action(self)

    def action_send_email(self):
        self.ensure_one()
        compose_form = self.env.ref("mail.email_compose_message_wizard_form")
        partner_ids = [self.partner_id.id] if self.partner_id else []
        return {
            "name": _("Send Email"),
            "type": "ir.actions.act_window",
            "res_model": "mail.compose.message",
            "view_mode": "form",
            "views": [(compose_form.id, "form")],
            "target": "new",
            "context": {
                "default_model": self.source_ref._name,
                "default_res_id": self.source_ref.id,
                "default_composition_mode": "comment",
                "default_subject": self.subject,
                "default_body": self.email_body or "",
                "default_partner_ids": [(6, 0, partner_ids)],
                "default_email_to": self.partner_email,
                "force_email": True,
            },
        }

    def action_save_to_chatter(self):
        self.ensure_one()
        document = self._create_document_record()
        return {
            "type": "ir.actions.act_window",
            "res_model": "client.letter.document",
            "view_mode": "form",
            "res_id": document.id,
            "target": "current",
        }

    def action_save_as_template(self):
        self.ensure_one()
        template_name = self.save_template_name or self._default_template_name()
        template = self.env["client.letter.template"].create({
            "name": template_name,
            "code": self._next_template_code(),
            "sequence": 999,
            "subject_template": self.subject or "",
            "body_template": self.letter_body or "",
            "email_template": self.email_body or "",
            "whatsapp_template": self.whatsapp_message or "",
        })
        self.template_id = template.id
        self.save_template_name = template.name
        return {
            "type": "ir.actions.act_window",
            "res_model": "client.letter.wizard",
            "view_mode": "form",
            "res_id": self.id,
            "target": "new",
        }

    def _populate_from_source(self):
        for wizard in self:
            source = wizard.source_ref
            if not source:
                continue
            wizard.company_id = getattr(source, "company_id", False) or self.env.company
            wizard.company_name = wizard.company_id.name or "CPA Books"
            partner = wizard._get_source_partner(source)
            commercial_partner = partner.commercial_partner_id if partner else False
            wizard.partner_id = partner
            wizard.partner_email = (partner.email or commercial_partner.email) if partner else False
            wizard.client_name = (commercial_partner.name or partner.name) if partner else source.display_name
            wizard.customer_address = wizard._format_partner_address(partner)
            wizard.customer_phone = (partner.phone or partner.mobile or commercial_partner.phone or commercial_partner.mobile) if partner else False
            wizard.customer_email = (partner.email or commercial_partner.email) if partner else False
            wizard.customer_website = (partner.website or commercial_partner.website) if partner else False
            wizard.attention_to = False
            wizard.letter_date = fields.Date.context_today(wizard)
            wizard.crm_number = False
            wizard.quotation_number = False
            wizard.invoice_number = False
            wizard.estimation_number = False
            wizard.client_lpo_number = False
            wizard.project_name = False
            wizard.amount_text = False
            wizard.payment_terms = False
            wizard.source_scope = False
            wizard.assumptions = False
            wizard.due_amount_text = False
            wizard.payment_status = False
            wizard.next_action = False

            if source._name == "crm.lead":
                wizard.crm_number = wizard._read_first(source, ["enquiry_number", "name"])
                wizard.project_name = wizard._get_related_project_name(source)
                wizard.source_scope = source.name or False
                wizard.next_action = getattr(source, "next_action", False)
                wizard.assumptions = getattr(source, "summary_note", False)
            elif source._name == "sale.order":
                wizard.quotation_number = source.name
                wizard.project_name = wizard._get_related_project_name(source) or source.name
                wizard.crm_number = wizard._read_sale_order_crm(source)
                wizard.amount_text = wizard._format_amount(source.amount_total, source.currency_id)
                wizard.payment_terms = source.payment_term_id.name if source.payment_term_id else False
                wizard.client_lpo_number = wizard._read_first(source, ["po_no", "lpo_no", "lpo_number", "client_order_ref"])
                wizard.attention_to = wizard._read_first(source, ["attention"])
                wizard.source_scope = wizard._join_lines(source.order_line.mapped("name"))
                wizard.assumptions = source.note
            elif source._name == "job.estimate":
                wizard.estimation_number = source.name
                wizard.project_name = wizard._get_related_project_name(source)
                wizard.amount_text = wizard._format_amount(source.total_job_estimate, source.currency_id)
                wizard.payment_terms = source.payment_term_id.name if source.payment_term_id else False
                wizard.source_scope = source.description
                wizard.assumptions = wizard._build_estimation_breakdown(source)
            elif source._name == "account.move":
                wizard.invoice_number = source.name
                wizard.project_name = wizard._get_related_project_name(source)
                wizard.crm_number = wizard._read_invoice_crm(source)
                wizard.quotation_number = source.invoice_origin or False
                wizard.client_lpo_number = wizard._read_first(source, ["po_no", "lpo_no", "lpo_number", "client_order_ref"])
                wizard.amount_text = wizard._format_amount(source.amount_total, source.currency_id)
                wizard.due_amount_text = wizard._format_amount(source.amount_residual, source.currency_id)
                wizard.payment_status = dict(source._fields["payment_state"].selection).get(source.payment_state)
                wizard.source_scope = source.invoice_payment_term_id.name if source.invoice_payment_term_id else False
                wizard.assumptions = getattr(source, "narration", False) or getattr(source, "ref", False)
            elif source._name == "project.project":
                wizard.project_name = source.name
                wizard.crm_number = wizard._read_related(source, "crm_id", ["enquiry_number", "name"])
                wizard.amount_text = wizard._format_amount(
                    getattr(source, "contract_amount", 0.0),
                    wizard.company_id.currency_id,
                )
                wizard.source_scope = getattr(source, "description", False)
                wizard.assumptions = wizard._join_lines(source.task_ids.mapped("name")[:10]) if "task_ids" in source._fields else False

    def _clear_source_defaults(self):
        for wizard in self:
            wizard.partner_id = False
            wizard.partner_email = False
            wizard.crm_number = False
            wizard.quotation_number = False
            wizard.invoice_number = False
            wizard.estimation_number = False
            wizard.client_lpo_number = False
            wizard.project_name = False
            wizard.client_name = False
            wizard.attention_to = False
            wizard.customer_address = False
            wizard.customer_phone = False
            wizard.customer_email = False
            wizard.customer_website = False
            wizard.amount_text = False
            wizard.payment_terms = False
            wizard.source_scope = False
            wizard.assumptions = False
            wizard.due_amount_text = False
            wizard.payment_status = False
            wizard.next_action = False

    def _apply_template_content(self):
        for wizard in self:
            if not wizard.template_id:
                continue
            if wizard.is_blank_template:
                wizard.subject = False
                wizard.letter_body = False
                wizard.email_body = False
                wizard.whatsapp_message = False
                wizard.save_template_name = wizard._default_template_name()
                continue
            values = wizard._template_values()
            wizard.subject = wizard._render_template_string(wizard.template_id.subject_template, values)
            wizard.letter_body = wizard._render_template_string(wizard.template_id.body_template, values)
            wizard.email_body = wizard._render_template_string(wizard.template_id.email_template, values)
            wizard.whatsapp_message = wizard._render_template_string(wizard.template_id.whatsapp_template, values)
            wizard.save_template_name = wizard._default_template_name()

    def _template_values(self):
        self.ensure_one()
        return {
            "crm_number": self.crm_number or "",
            "quotation_number": self.quotation_number or "",
            "invoice_number": self.invoice_number or "",
            "estimation_number": self.estimation_number or "",
            "client_lpo_number": self.client_lpo_number or "",
            "project_name": self.project_name or "",
            "client_name": self.client_name or "",
            "attention_to": self.attention_to or "",
            "letter_date": fields.Date.to_string(self.letter_date) if self.letter_date else "",
            "company_name": self.company_name or "CPA Books",
            "amount_text": self.amount_text or "",
            "payment_terms": self.payment_terms or "",
            "source_scope": self.source_scope or "",
            "assumptions": self.assumptions or "",
            "due_amount_text": self.due_amount_text or "",
            "payment_status": self.payment_status or "",
            "next_action": self.next_action or "",
        }

    def _render_template_string(self, text, values):
        rendered = text or ""
        for key, value in values.items():
            rendered = rendered.replace("{{%s}}" % key, value or "")
        return rendered

    def _get_source_partner(self, source):
        if "partner_id" in source._fields and source.partner_id:
            return source.partner_id
        if source._name == "crm.lead":
            for field_name in ["client_company_name", "partner_id"]:
                if field_name in source._fields and source[field_name]:
                    return source[field_name]
        return False

    def _get_related_project_name(self, source):
        for field_name in ["project_id"]:
            if field_name in source._fields and source[field_name]:
                return source[field_name].name
        if source._name == "account.move" and "invoice_line_ids" in source._fields:
            project = source.invoice_line_ids.mapped("analytic_account_id")
            if project:
                return project[0].name
        return False

    def _read_related(self, record, relation_field, fields_list):
        relation = getattr(record, relation_field, False)
        if not relation:
            return False
        return self._read_first(relation, fields_list)

    def _read_first(self, record, fields_list):
        for field_name in fields_list:
            if field_name in record._fields and record[field_name]:
                value = record[field_name]
                return value.display_name if hasattr(value, "display_name") else value
        return False

    def _read_invoice_crm(self, move):
        if "project_id" in move._fields and move.project_id and "crm_id" in move.project_id._fields and move.project_id.crm_id:
            return self._read_first(move.project_id.crm_id, ["enquiry_number", "name"])
        if move.invoice_origin:
            order = self.env["sale.order"].search([("name", "=", move.invoice_origin)], limit=1)
            if order:
                return self._read_sale_order_crm(order)
        return False

    def _read_sale_order_crm(self, order):
        crm_number = self._read_related(order, "crm_id", ["enquiry_number", "name"])
        if crm_number:
            return crm_number
        return self._read_related(order, "opportunity_id", ["enquiry_number", "name"])

    def _build_estimation_breakdown(self, estimate):
        lines = []
        if estimate.total_material_estimate:
            lines.append("Materials: %s" % self._format_amount(estimate.total_material_estimate, estimate.currency_id))
        if estimate.total_labour_estimate:
            lines.append("Labour: %s" % self._format_amount(estimate.total_labour_estimate, estimate.currency_id))
        if estimate.total_overhead_estimate:
            lines.append("Overheads: %s" % self._format_amount(estimate.total_overhead_estimate, estimate.currency_id))
        return "\n".join(lines)

    def _join_lines(self, values):
        clean_values = [value for value in values if value]
        return "\n".join(clean_values)

    def _format_amount(self, amount, currency):
        if currency:
            return "%s %.2f" % (currency.symbol or currency.name or "", amount or 0.0)
        return "%.2f" % (amount or 0.0)

    def _format_partner_address(self, partner):
        if not partner:
            return False
        commercial_partner = partner.commercial_partner_id
        parts = [
            partner.street,
            partner.street2,
            partner.city,
            partner.state_id.name if partner.state_id else False,
            partner.zip,
            partner.country_id.name if partner.country_id else False,
            commercial_partner.street if commercial_partner and commercial_partner != partner and not partner.street else False,
            commercial_partner.street2 if commercial_partner and commercial_partner != partner and not partner.street2 else False,
            commercial_partner.city if commercial_partner and commercial_partner != partner and not partner.city else False,
            commercial_partner.state_id.name if commercial_partner and commercial_partner != partner and not partner.state_id and commercial_partner.state_id else False,
            commercial_partner.zip if commercial_partner and commercial_partner != partner and not partner.zip else False,
            commercial_partner.country_id.name if commercial_partner and commercial_partner != partner and not partner.country_id and commercial_partner.country_id else False,
        ]
        return "\n".join([part for part in parts if part])

    def _create_document_record(self):
        self.ensure_one()
        return self.env["client.letter.document"].create({
            "source_ref": "%s,%s" % (self.source_ref._name, self.source_ref.id) if self.source_ref else False,
            "template_id": self.template_id.id,
            "partner_id": self.partner_id.id,
            "partner_email": self.partner_email,
            "company_id": self.company_id.id,
            "crm_number": self.crm_number,
            "quotation_number": self.quotation_number,
            "invoice_number": self.invoice_number,
            "estimation_number": self.estimation_number,
            "client_lpo_number": self.client_lpo_number,
            "project_name": self.project_name,
            "client_name": self.client_name,
            "attention_to": self.attention_to,
            "customer_address": self.customer_address,
            "customer_phone": self.customer_phone,
            "customer_email": self.customer_email,
            "customer_website": self.customer_website,
            "letter_date": self.letter_date,
            "company_name": self.company_name,
            "subject": self.subject,
            "letter_body": self.letter_body,
            "email_body": self.email_body,
            "whatsapp_message": self.whatsapp_message,
            "attachment_ids": [(6, 0, self.attachment_ids.ids)],
        })

    def _default_template_name(self):
        self.ensure_one()
        base = (self.subject or "").strip() or "Template"
        existing_count = self.env["client.letter.template"].search_count([])
        return "Template %s - %s" % (existing_count + 1, base)

    def _next_template_code(self):
        existing_count = self.env["client.letter.template"].search_count([])
        return "user_template_%s" % (existing_count + 1)
