# -*- coding: utf-8 -*-
"""Full Switchgear processing cycle (16 steps) for progress status UI."""

from odoo import _

# theme -> first color index in mixin _PROGRESS_COLORS
_CYCLE_THEME_OFFSET = {
    'customer': 0,
    'engineering': 1,
    'purchase': 4,
    'accounting': 5,
}

SWITCHGEAR_FULL_CYCLE_STEPS = [
    {
        'stage_key': 'enquiry',
        'title': _('1 — ENQUIRY (CRM)'),
        'theme': 'customer',
        'blocks': [(_('Requirements'), [
            ('cycle_enquiry_number', _('Enquiry / reference number')),
            ('cycle_partner', _('Customer')),
            ('cycle_subject', _('Subject / opportunity name')),
        ])],
    },
    {
        'stage_key': 'estimation',
        'title': _('2 — ESTIMATION'),
        'theme': 'customer',
        'blocks': [(_('Job estimate'), [
            ('cycle_estimate_created', _('Job estimate created')),
            ('cycle_estimate_confirmed', _('Estimate confirmed')),
            ('cycle_estimate_approved', _('Estimate approved')),
        ])],
    },
    {
        'stage_key': 'quotation',
        'title': _('3 — QUOTATION'),
        'theme': 'customer',
        'blocks': [(_('Sales quotation'), [
            ('cycle_quotation_created', _('Quotation created')),
            ('cycle_quotation_sent', _('Quotation sent to customer')),
            ('cycle_sale_confirmed', _('Sales order confirmed')),
        ])],
    },
    {
        'stage_key': 'design',
        'title': _('4 — DESIGN DOCUMENTS'),
        'theme': 'engineering',
        'blocks': [(_('Design register'), [
            ('cycle_design_register', _('Design document register')),
            ('cycle_design_sent', _('Documents sent (lines)')),
            ('cycle_design_received', _('Documents received (lines)')),
        ])],
    },
    {
        'stage_key': 'bom',
        'title': _('5 — BILL OF MATERIAL'),
        'theme': 'engineering',
        'blocks': [(_('Engineering'), [
            ('cycle_bom_created', _('Bill of materials created')),
        ])],
    },
    {
        'stage_key': 'mo',
        'title': _('6 — MANUF. ORDER (MO)'),
        'theme': 'engineering',
        'blocks': [(_('Production'), [
            ('cycle_mo_created', _('Manufacturing order created')),
            ('cycle_mo_confirmed', _('MO confirmed / released')),
            ('cycle_mo_progress', _('MO in progress')),
        ])],
    },
    {
        'stage_key': 'pr',
        'title': _('7 — PURCHASE REQUISITION'),
        'theme': 'engineering',
        'blocks': [(_('Requisition'), [
            ('cycle_pr_created', _('Purchase requisition raised')),
        ])],
    },
    {
        'stage_key': 'qc',
        'title': _('8 — QUALITY CONTROL'),
        'theme': 'engineering',
        'blocks': [(_('Quality'), [
            ('cycle_qc_created', _('Quality check / alert')),
            ('cycle_qc_passed', _('Quality passed')),
        ])],
    },
    {
        'stage_key': 'stock',
        'title': _('9 — STOCK CHECK'),
        'theme': 'purchase',
        'blocks': [(_('Inventory'), [
            ('cycle_stock_reserved', _('Components reserved for MO')),
        ])],
    },
    {
        'stage_key': 'lpo',
        'title': _('10 — LPO (PURCHASE)'),
        'theme': 'purchase',
        'blocks': [(_('Purchase'), [
            ('cycle_po_draft', _('Purchase RFQ / draft')),
            ('cycle_po_confirmed', _('Purchase order confirmed')),
        ])],
    },
    {
        'stage_key': 'grn',
        'title': _('11 — GRN'),
        'theme': 'purchase',
        'blocks': [(_('Receipt'), [
            ('cycle_grn_open', _('GRN pending receipt')),
            ('cycle_grn_done', _('GRN received')),
        ])],
    },
    {
        'stage_key': 'delivery',
        'title': _('12 — DELIVERY'),
        'theme': 'purchase',
        'blocks': [(_('Delivery order'), [
            ('cycle_delivery_open', _('Delivery pending')),
            ('cycle_delivery_done', _('Delivery completed')),
        ])],
    },
    {
        'stage_key': 'invoice',
        'title': _('13 — TAX INVOICE'),
        'theme': 'accounting',
        'blocks': [(_('Customer invoice'), [
            ('cycle_invoice_created', _('Customer invoice created')),
            ('cycle_invoice_posted', _('Invoice posted')),
        ])],
    },
    {
        'stage_key': 'receipt',
        'title': _('14 — CUSTOMER PAYMENT'),
        'theme': 'accounting',
        'blocks': [(_('Receipt voucher'), [
            ('cycle_payment_inbound', _('Customer receipt / payment voucher')),
        ])],
    },
    {
        'stage_key': 'bills',
        'title': _('15 — BILLS ENTRY'),
        'theme': 'accounting',
        'blocks': [(_('Vendor bill'), [
            ('cycle_vendor_bill', _('Vendor bill entered')),
        ])],
    },
    {
        'stage_key': 'vendor_pay',
        'title': _('16 — VENDOR PAYMENT'),
        'theme': 'accounting',
        'blocks': [(_('Payment voucher'), [
            ('cycle_payment_outbound', _('Vendor payment voucher')),
        ])],
    },
]

# Primary cycle step index (0–15) when viewing each document type
DOCUMENT_CYCLE_INDEX = {
    'crm.lead': 0,
    'switchgear.estimate': 1,
    'sale.order': 2,
    'switchgear.design.document': 3,
    'mrp.bom': 4,
    'mrp.production': 5,
    'switchgear.purchase.requisition': 6,
    'switchgear.quality.check': 7,
    'switchgear.quality.alert': 7,
    'stock.picking': 10,  # default GRN; outgoing resolved below
    'purchase.order': 9,
    'account.move': 12,
    'account.payment': 13,
    'quotation.job.order': 5,
}


_PROGRESS_COLORS = ('orange', 'green', 'blue', 'purple', 'teal', 'yellow', 'pink')

_MRP_DONE_STATES = frozenset(('confirmed', 'progress', 'to_close', 'done'))
_MRP_PROGRESS_STATES = frozenset(('progress', 'to_close', 'done'))


def mo_is_confirmed(mo):
    """True when MO exists beyond draft/cancel (handles falsy computed state)."""
    if not mo:
        return False
    state = mo.state
    if state in _MRP_DONE_STATES:
        return True
    if state in ('draft', 'cancel'):
        return False
    return bool(mo.move_raw_ids)


def mo_is_in_progress(mo):
    """True when production has started or finished."""
    if not mo:
        return False
    if mo.state in _MRP_PROGRESS_STATES:
        return True
    if mo.move_raw_ids.filtered(lambda m: m.state in ('assigned', 'partially_available', 'done')):
        return True
    if mo.move_raw_ids.filtered(lambda m: m.quantity_done):
        return True
    return False


def switchgear_cycle_sections():
    """Build section dicts for progress HTML renderer."""
    sections = []
    for index, step in enumerate(SWITCHGEAR_FULL_CYCLE_STEPS):
        theme = step.get('theme', 'customer')
        base = _CYCLE_THEME_OFFSET.get(theme, 0)
        sections.append({
            'stage_key': step['stage_key'],
            'stage_index': index,
            'title': step['title'],
            'css': 'cpabooks_fsm_side_%s' % _PROGRESS_COLORS[(base + index) % len(_PROGRESS_COLORS)],
            'blocks': step['blocks'],
        })
    return sections


def compute_switchgear_cycle_checks(lead):
    """Pipeline checklist for all 16 cycle steps from a CRM lead / opportunity."""
    lead = lead.sudo()
    env = lead.env
    company = lead.company_id or env.company

    orders = lead.order_ids.filtered(lambda o: o.state not in ('cancel',))
    partner = lead.partner_id

    estimates = env['switchgear.estimate'].search([
        ('opportunity_id', '=', lead.id),
    ]) if 'opportunity_id' in env['switchgear.estimate']._fields else env['switchgear.estimate']

    boms = env['mrp.bom']
    mos = env['mrp.production']
    if estimates:
        if 'sale_quotation_id' in estimates._fields:
            orders = orders | estimates.mapped('sale_quotation_id').filtered(
                lambda o: o and o.state not in ('cancel',),
            )
        boms = boms.search([('estimate_id', 'in', estimates.ids)])
        mos = mos.search([('bom_id', 'in', boms.ids)])
        if boms and 'sale_order_id' in boms._fields:
            orders = orders | boms.mapped('sale_order_id').filtered(
                lambda o: o and o.state not in ('cancel',),
            )

    designs = env['switchgear.design.document']
    if partner:
        designs = designs.search([
            ('partner_id', '=', partner.id),
            '|', ('company_id', '=', False), ('company_id', '=', company.id),
        ], limit=5)

    requisitions = env['switchgear.purchase.requisition']
    if 'switchgear.purchase.requisition' in env:
        projects = orders.mapped('project_id').filtered(lambda p: p)
        if not projects and estimates:
            projects = estimates.mapped('project_id').filtered(lambda p: p)
        if projects:
            requisitions = requisitions.search([
                ('project_id', 'in', projects.ids),
            ])
        else:
            requisitions = env['switchgear.purchase.requisition']

    qc_checks = env['switchgear.quality.check'] if 'switchgear.quality.check' in env else env['ir.model']
    if 'switchgear.quality.check' in env and mos:
        qc_checks = env['switchgear.quality.check'].search([('production_id', 'in', mos.ids)])
    elif 'switchgear.quality.check' not in env:
        qc_checks = env['ir.model'].browse()

    pos = env['purchase.order']
    if mos and 'mo_id' in env['purchase.order']._fields:
        pos = pos.search([('mo_id', 'in', mos.ids)])
    elif orders:
        pos = pos.search([
            ('company_id', '=', company.id),
            ('origin', 'in', orders.mapped('name')),
            ('state', 'not in', ('cancel',)),
        ])
    else:
        pos = env['purchase.order']

    pickings = env['stock.picking']
    invoices = env['account.move']
    payments = env['account.payment']
    if orders:
        pickings = orders.mapped('picking_ids')
        invoices = orders.mapped('invoice_ids').filtered(
            lambda m: m.move_type == 'out_invoice' and m.state != 'cancel',
        )
    if partner:
        payments = env['account.payment'].search([
            ('partner_id', '=', partner.id),
            ('company_id', '=', company.id),
            ('state', '!=', 'cancel'),
        ], limit=20)
        vendor_bills = env['account.move'].search([
            ('partner_id', '=', partner.id),
            ('move_type', '=', 'in_invoice'),
            ('company_id', '=', company.id),
            ('state', '!=', 'cancel'),
        ], limit=10)
    else:
        vendor_bills = env['account.move']

    enquiry = (getattr(lead, 'enquiry_number', '') or '').strip()
    enquiry_ok = bool(
        enquiry and enquiry not in ('/', 'New') and enquiry != _('New'),
    ) or bool((lead.name or '').strip())
    sent_lines = sum(designs.mapped('sent_count')) if designs else 0
    received_lines = sum(designs.mapped('received_count')) if designs else 0
    incoming = pickings.filtered(lambda p: p.picking_type_code == 'incoming')
    outgoing = pickings.filtered(lambda p: p.picking_type_code == 'outgoing')

    return {
        'cycle_enquiry_number': enquiry_ok,
        'cycle_partner': bool(partner),
        'cycle_subject': bool((lead.name or '').strip()),
        'cycle_estimate_created': bool(estimates),
        'cycle_estimate_confirmed': bool(estimates.filtered(
            lambda e: e.state in ('confirmed', 'approved', 'done'),
        )) or bool(orders),
        'cycle_estimate_approved': bool(estimates.filtered(
            lambda e: e.state in ('approved', 'done'),
        )) or bool(orders.filtered(lambda o: o.state in ('sale', 'done'))),
        'cycle_quotation_created': bool(orders),
        'cycle_quotation_sent': bool(orders.filtered(lambda o: o.state in ('sent', 'sale', 'done'))),
        'cycle_sale_confirmed': bool(orders.filtered(lambda o: o.state in ('sale', 'done'))),
        'cycle_design_register': bool(designs),
        'cycle_design_sent': sent_lines > 0,
        'cycle_design_received': received_lines > 0,
        'cycle_bom_created': bool(boms),
        'cycle_mo_created': bool(mos),
        'cycle_mo_confirmed': bool(mos.filtered(mo_is_confirmed)),
        'cycle_mo_progress': bool(mos.filtered(mo_is_in_progress)),
        'cycle_pr_created': bool(requisitions),
        'cycle_qc_created': bool(qc_checks),
        'cycle_qc_passed': bool(qc_checks.filtered(lambda c: c.quality_state == 'pass')),
        'cycle_stock_reserved': bool(mos.mapped('move_raw_ids').filtered(
            lambda m: m.state in ('assigned', 'done'),
        )),
        'cycle_po_draft': bool(pos.filtered(lambda p: p.state in ('draft', 'sent', 'to approve'))),
        'cycle_po_confirmed': bool(pos.filtered(lambda p: p.state in ('purchase', 'done'))),
        'cycle_grn_open': bool(incoming.filtered(lambda p: p.state not in ('done', 'cancel'))),
        'cycle_grn_done': bool(incoming.filtered(lambda p: p.state == 'done')),
        'cycle_delivery_open': bool(outgoing.filtered(lambda p: p.state not in ('done', 'cancel'))),
        'cycle_delivery_done': bool(outgoing.filtered(lambda p: p.state == 'done')),
        'cycle_invoice_created': bool(invoices),
        'cycle_invoice_posted': bool(invoices.filtered(lambda m: m.state == 'posted')),
        'cycle_payment_inbound': bool(payments.filtered(
            lambda p: p.payment_type == 'inbound' and p.state in ('posted', 'reconciled'),
        )),
        'cycle_vendor_bill': bool(vendor_bills),
        'cycle_payment_outbound': bool(payments.filtered(
            lambda p: p.payment_type == 'outbound' and p.state in ('posted', 'reconciled'),
        )),
    }


def document_cycle_index(record):
    """Map the open document to its step index on the 16-step cycle."""
    model = record._name
    if model == 'stock.picking':
        return 11 if record.picking_type_code == 'outgoing' else 10
    if model == 'account.move':
        return 14 if record.move_type == 'in_invoice' else 12
    if model == 'account.payment':
        return 13 if record.payment_type == 'inbound' else 15
    if model == 'sale.order' and record.state in ('sale', 'done'):
        return 2
    return DOCUMENT_CYCLE_INDEX.get(model, 0)


def empty_switchgear_cycle_checks():
    """All cycle keys False when no CRM lead is linked."""
    checks = {}
    for step in SWITCHGEAR_FULL_CYCLE_STEPS:
        for _block_title, items in step['blocks']:
            for item_key, _label in items:
                checks[item_key] = False
    return checks
