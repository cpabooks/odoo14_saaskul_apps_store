# -*- coding: utf-8 -*-

from markupsafe import Markup

from odoo import _, api, models

from .cpabooks_switchgear_cycle import (
    compute_switchgear_cycle_checks,
    document_cycle_index,
    empty_switchgear_cycle_checks,
    switchgear_cycle_sections,
)

_PROGRESS_COLORS = (
    'orange', 'green', 'blue', 'purple', 'teal', 'yellow', 'pink',
)


class CpabooksDocumentProgressMixin(models.AbstractModel):
    """Shared progress-status popup (checklist sidebar like FSM complaint workflow)."""

    _name = 'cpabooks.document.progress.mixin'
    _description = 'CPABooks document progress status mixin'

    def action_cpabooks_open_progress_status(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Progress Status'),
            'res_model': 'cpabooks.progress.status.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_res_model': self._name,
                'default_res_id': self.id,
            },
        }

    # -------------------------------------------------------------------------
    # Override per document type
    # -------------------------------------------------------------------------

    def _cpabooks_progress_workflow_title(self):
        return _('Saaskul Switchgear processing cycle')

    def _cpabooks_progress_workflow_subtitle(self):
        return _(
            'Full process from CRM enquiry through accounting. '
            'The current document step and the next step are expanded; others are folded.',
        )

    def _cpabooks_progress_use_full_cycle(self):
        return True

    def _cpabooks_progress_sections(self):
        """List of {stage_key, title, css, blocks:[(block_title, [(key, label), ...])]}."""
        if self._cpabooks_progress_use_full_cycle():
            return switchgear_cycle_sections()
        return []

    def _cpabooks_progress_current_stage_index(self):
        self.ensure_one()
        if self._cpabooks_progress_use_full_cycle():
            return document_cycle_index(self)
        return 0

    def _cpabooks_switchgear_pipeline_lead(self):
        """CRM lead / opportunity linked to this document (may be empty)."""
        self.ensure_one()
        if self._name == 'crm.lead':
            return self
        if self._name == 'switchgear.estimate' and 'opportunity_id' in self._fields:
            return self.opportunity_id
        if self._name == 'sale.order' and 'opportunity_id' in self._fields:
            return self.opportunity_id
        if self._name == 'quotation.job.order' and self.quotation_no:
            return self.quotation_no.opportunity_id
        if self._name == 'mrp.bom':
            if self.estimate_id and self.estimate_id.opportunity_id:
                return self.estimate_id.opportunity_id
            if self.sale_order_id and self.sale_order_id.opportunity_id:
                return self.sale_order_id.opportunity_id
        if self._name == 'mrp.production':
            if self.bom_id and self.bom_id.estimate_id and self.bom_id.estimate_id.opportunity_id:
                return self.bom_id.estimate_id.opportunity_id
            sale = getattr(self, 'sale_order_id', False)
            if not sale and self.bom_id:
                sale = getattr(self.bom_id, 'sale_order_id', False)
            if sale and sale.opportunity_id:
                return sale.opportunity_id
            if self.project_id:
                estimate = self.env['switchgear.estimate'].sudo().search([
                    ('project_id', '=', self.project_id.id),
                    ('opportunity_id', '!=', False),
                ], limit=1, order='id desc')
                if estimate.opportunity_id:
                    return estimate.opportunity_id
            if self.partner_id:
                return self._cpabooks_find_opportunity_for_partner(
                    self.partner_id, self.company_id,
                )
        if self._name == 'purchase.order':
            if getattr(self, 'mo_id', False):
                return self.mo_id._cpabooks_switchgear_pipeline_lead()
            if self.origin:
                mo = self.env['mrp.production'].sudo().search([
                    ('name', '=', self.origin),
                    ('company_id', '=', self.company_id.id),
                ], limit=1)
                if mo:
                    return mo._cpabooks_switchgear_pipeline_lead()
        if self._name == 'stock.picking' and self.sale_id:
            return self.sale_id.opportunity_id
        if self._name == 'switchgear.quality.check' and self.production_id:
            return self.production_id._cpabooks_switchgear_pipeline_lead()
        if self._name == 'switchgear.purchase.requisition' and self.project_id:
            estimate = self.env['switchgear.estimate'].sudo().search([
                ('project_id', '=', self.project_id.id),
                ('opportunity_id', '!=', False),
            ], limit=1, order='id desc')
            if estimate.opportunity_id:
                return estimate.opportunity_id
        return self.env['crm.lead']

    @api.model
    def _cpabooks_find_opportunity_for_partner(self, partner, company):
        if not partner:
            return self.env['crm.lead']
        domain = [
            ('partner_id', '=', partner.id),
            ('type', '=', 'opportunity'),
        ]
        if company:
            domain = [
                '|', ('company_id', '=', False), ('company_id', '=', company.id),
            ] + domain
        return self.env['crm.lead'].sudo().search(domain, limit=1, order='id desc')

    def _cpabooks_progress_checks_from_record(self):
        """Flags that are true for the document currently open (merge over pipeline)."""
        self.ensure_one()
        checks = {}
        if self._name == 'switchgear.estimate':
            checks['cycle_estimate_created'] = True
            if self.state in ('confirmed', 'approved', 'done'):
                checks['cycle_estimate_confirmed'] = True
            if self.state in ('approved', 'done'):
                checks['cycle_estimate_approved'] = True
        elif self._name == 'sale.order':
            checks['cycle_quotation_created'] = True
            if self.state in ('sent', 'sale', 'done'):
                checks['cycle_quotation_sent'] = True
            if self.state in ('sale', 'done'):
                checks['cycle_sale_confirmed'] = True
        elif self._name == 'mrp.bom':
            checks['cycle_bom_created'] = True
        elif self._name == 'mrp.production':
            from .cpabooks_switchgear_cycle import mo_is_confirmed, mo_is_in_progress
            checks['cycle_mo_created'] = True
            if mo_is_confirmed(self):
                checks['cycle_mo_confirmed'] = True
            if mo_is_in_progress(self):
                checks['cycle_mo_progress'] = True
            if self.move_raw_ids.filtered(lambda m: m.state in ('assigned', 'done')):
                checks['cycle_stock_reserved'] = True
        elif self._name == 'purchase.order':
            if self.state in ('draft', 'sent', 'to approve'):
                checks['cycle_po_draft'] = True
            if self.state in ('purchase', 'done'):
                checks['cycle_po_confirmed'] = True
        elif self._name == 'switchgear.quality.check':
            checks['cycle_qc_created'] = True
            if self.quality_state == 'pass':
                checks['cycle_qc_passed'] = True
        elif self._name == 'switchgear.purchase.requisition':
            checks['cycle_pr_created'] = True
        elif self._name == 'stock.picking':
            if self.picking_type_code == 'incoming':
                if self.state not in ('done', 'cancel'):
                    checks['cycle_grn_open'] = True
                if self.state == 'done':
                    checks['cycle_grn_done'] = True
            elif self.picking_type_code == 'outgoing':
                if self.state not in ('done', 'cancel'):
                    checks['cycle_delivery_open'] = True
                if self.state == 'done':
                    checks['cycle_delivery_done'] = True
        elif self._name == 'crm.lead':
            enquiry = (getattr(self, 'enquiry_number', '') or '').strip()
            if enquiry and enquiry not in ('/', 'New'):
                checks['cycle_enquiry_number'] = True
            elif (self.name or '').strip():
                checks['cycle_enquiry_number'] = True
            checks['cycle_partner'] = bool(self.partner_id)
            checks['cycle_subject'] = bool((self.name or '').strip())
        return checks

    def _cpabooks_progress_checks(self):
        lead = self._cpabooks_switchgear_pipeline_lead()
        if lead:
            checks = compute_switchgear_cycle_checks(lead)
        else:
            checks = empty_switchgear_cycle_checks()
        checks.update(self._cpabooks_progress_checks_from_record())
        return checks

    # -------------------------------------------------------------------------
    # Rendering (FSM complaint workflow style)
    # -------------------------------------------------------------------------

    def _cpabooks_section_complete(self, section, checks):
        for _block_title, items in section.get('blocks', []):
            for item_key, _label in items:
                if item_key not in checks or checks[item_key] is None:
                    continue
                if not checks[item_key]:
                    return False
        return True

    def _cpabooks_progress_completion_percent(self):
        self.ensure_one()
        checks = self._cpabooks_progress_checks()
        sections = self._cpabooks_progress_sections()
        if not sections:
            return 0.0
        total = done = 0
        for section in sections:
            for _block_title, items in section.get('blocks', []):
                for item_key, _label in items:
                    if item_key not in checks or checks[item_key] is None:
                        continue
                    total += 1
                    if checks[item_key]:
                        done += 1
        if not total:
            return 0.0
        return round(100.0 * done / total, 1)

    def _cpabooks_progress_render_check_item(self, item_key, label, checks=None):
        if checks is None:
            checks = self._cpabooks_progress_checks()
        if item_key not in checks:
            return ''
        done = bool(checks[item_key])
        state = 'done' if done else 'pending'
        icon = 'fa-check-circle' if done else 'fa-circle-o'
        return (
            '<li class="cpabooks_fsm_check_item cpabooks_fsm_check_%s cpabooks_fsm_check_workflow">'
            '<i class="fa %s cpabooks_fsm_check_icon" aria-hidden="true"></i>'
            '<span class="cpabooks_fsm_check_label">%s</span></li>'
        ) % (state, icon, label)

    def _cpabooks_progress_render_html(self):
        self.ensure_one()
        ui_index = self._cpabooks_progress_current_stage_index()
        percent = self._cpabooks_progress_completion_percent()
        checks = self._cpabooks_progress_checks()
        parts = [
            '<div class="cpabooks_fsm_sidebar_inner">',
            '<div class="cpabooks_fsm_sidebar_title">',
            self._cpabooks_progress_workflow_title(),
            '</div>',
            '<div class="cpabooks_fsm_sidebar_sub">',
            self._cpabooks_progress_workflow_subtitle(),
            '</div>',
            '<div class="o_cpabooks_progress_summary">',
            _('Overall completion: <strong>%s%%</strong>') % percent,
            '</div>',
        ]
        for section in self._cpabooks_progress_sections():
            try:
                stage_index = int(section.get('stage_index', 0))
            except (TypeError, ValueError):
                stage_index = 0
            section_done = self._cpabooks_section_complete(section, checks)
            if section_done:
                stage_status = _('Done')
                stage_status_css = 'cpabooks_fsm_stage_done'
            elif stage_index == ui_index:
                stage_status = _('In Progress')
                stage_status_css = 'cpabooks_fsm_stage_current'
            elif stage_index == ui_index + 1:
                stage_status = _('Next')
                stage_status_css = 'cpabooks_fsm_stage_next'
            else:
                stage_status = _('Pending')
                stage_status_css = 'cpabooks_fsm_stage_pending'
            is_expanded = stage_index in (ui_index, ui_index + 1)
            open_attr = ' open' if is_expanded else ''
            fold_class = '' if is_expanded else ' cpabooks_fsm_stage_folded'
            head_extra = ''
            if stage_index == ui_index:
                head_extra = ' cpabooks_fsm_stage_current'
            elif stage_index == ui_index + 1:
                head_extra = ' cpabooks_fsm_stage_next'
            parts.append(
                '<details class="cpabooks_fsm_stage_accordion %s %s%s"%s>'
                '<summary class="cpabooks_fsm_stage_head %s%s">'
                '<span class="cpabooks_fsm_stage_head_title">%s</span>'
                '<span class="cpabooks_fsm_stage_head_status %s">%s</span>'
                '</summary><div class="cpabooks_fsm_stage_body">'
                % (
                    section.get('css', 'cpabooks_fsm_side_blue'),
                    stage_status_css,
                    fold_class,
                    open_attr,
                    section.get('css', 'cpabooks_fsm_side_blue'),
                    head_extra,
                    section.get('title', ''),
                    stage_status_css,
                    stage_status,
                )
            )
            for block_title, items in section.get('blocks', []):
                block_css = section.get('css', 'cpabooks_fsm_side_blue').replace(
                    'cpabooks_fsm_side_', 'cpabooks_fsm_block_',
                )
                parts.append(
                    '<div class="cpabooks_fsm_block_title cpabooks_fsm_block_roman %s">%s</div>'
                    '<ul class="cpabooks_fsm_check_list">' % (block_css, block_title)
                )
                for item_key, item_label in items:
                    parts.append(self._cpabooks_progress_render_check_item(
                        item_key, item_label, checks=checks,
                    ))
                parts.append('</ul>')
            parts.append('</div></details>')
        parts.append('</div>')
        return Markup(''.join(parts))

    @staticmethod
    def _cpabooks_progress_color_css(index):
        return 'cpabooks_fsm_side_%s' % _PROGRESS_COLORS[index % len(_PROGRESS_COLORS)]

    def _cpabooks_progress_truthy(self, value):
        if isinstance(value, models.BaseModel):
            return bool(value)
        if isinstance(value, (list, tuple)):
            return bool(value)
        if isinstance(value, str):
            return bool((value or '').strip())
        return bool(value)
