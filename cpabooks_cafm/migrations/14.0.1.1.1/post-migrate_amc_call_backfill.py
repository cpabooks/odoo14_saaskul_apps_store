# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    Request = env['maintenance.request'].sudo()
    WorkType = env['cpabooks.cafm.work.type'].sudo()
    Problem = env['cpabooks.cafm.problem.reported'].sudo()

    work_types = {w.name.lower(): w.id for w in WorkType.search([])}
    problems = {p.name.lower(): p.id for p in Problem.search([])}

    for req in Request.search([('call_no', '=', False)]):
        vals = {}
        if req.ticket_no:
            vals['call_no'] = req.ticket_no
        else:
            vals['call_no'] = Request._generate_call_no()
        if not req.ticket_no:
            vals['ticket_no'] = vals['call_no']
        if not req.call_type:
            vals['call_type'] = 'amc'
        if not req.call_date and req.request_date:
            vals['call_date'] = req.request_date
        if req.work_type and not req.work_type_id:
            wt_id = work_types.get(req.work_type.lower())
            if wt_id:
                vals['work_type_id'] = wt_id
        if req.problem and not req.problem_reported_id:
            pr_id = problems.get(req.problem.lower())
            if pr_id:
                vals['problem_reported_id'] = pr_id
        if req.problem and not req.problem_description:
            vals['problem_description'] = req.problem
        if req.cafm_project_id and not req.l1_level_id:
            vals['l1_level_id'] = req.cafm_project_id.id
        if req.partner_id and not req.l2_level_id:
            contract = env['cpabooks.cafm.contract'].search([
                ('client_id', '=', req.partner_id.id),
            ], limit=1, order='contract_expiry desc')
            if contract and contract.customer_group_id:
                vals['l2_level_id'] = contract.customer_group_id.id
        if vals:
            req.write(vals)

    _logger.info('cpabooks_cafm %s: backfilled AMC call fields on maintenance.request', version)
