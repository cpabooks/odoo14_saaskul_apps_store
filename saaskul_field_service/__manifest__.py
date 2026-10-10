# -*- coding: utf-8 -*-
{
    'name': "Saaskul Field Service",

    'summary': """
        Complaint Registration (CRN) for Odoo Field Service: 9-stage workflow
        from registration, site visit and quotation to job completion, invoice
        and approval, with material issue/return notes, job costing and dashboards.""",

    'description': """
        Saaskul Field Service turns Odoo Field Service tasks into Complaint
        Registration Numbers (CRNs). Every complaint follows a guided 9-stage
        flow (Registered, Site Visited, Quotation Issued, Quotation Approved,
        Work in Progress, Waiting Invoice, FOC Done, Invoiced, Approved) with a
        numbered form, a stage checklist and a progress bar.

        Store teams issue and return materials against a CRN with Material
        Issue / Return Notes, and every CRN collects material, timesheet,
        transport and other costs. A service dashboard, a processing cycle
        view, chart dashboards and Job Completion Reports (internal and
        customer copies) are included.
    """,

    'author': "Saaskul",
    'website': "https://saaskul.com",
    'support': "info.cpabooks@gmail.com",
    'category': 'Services/Field Service',
    'version': '14.0.1.0.0',
    'license': 'OPL-1',
    'images': ['static/description/banner.png'],

    'depends': [
        'base',
        'hr_timesheet',
        'industry_fsm',
        'industry_fsm_report',
        'industry_fsm_sale',
        'project_forecast',
        'sale_timesheet',
        'sale_stock',
        'timesheet_grid',
        'stock',
        'purchase',
    ],

    'data': [
        'security/ir.model.access.csv',
        'security/customer_part_access.xml',
        'data/invoice_type_data.xml',
        'data/project_project_data.xml',
        'data/project_task_data.xml',
        'views/report_project_task.xml',
        'reports/worksheet_customer_report_templates.xml',
        'views/complaint_detail_views.xml',
        'views/project_project_views_inherit.xml',
        'views/project_task_views.xml',
        'views/crn_task_bifurcation_views.xml',
        'views/fsm_task_form_statusbar_fix_views.xml',
        'views/fsm_task_form_next_action_duplicate_fix.xml',
        'views/fsm_action_navigation_views.xml',
        'views/fsm_crn_form_shell_views.xml',
        'views/fsm_workflow_ui_views.xml',
        'views/fsm_workflow_stage_controls_views.xml',
        'views/fsm_timesheet_employee_views.xml',
        'views/fsm_crn_cost_views.xml',
        'views/fsm_crn_create_views.xml',
        'views/res_partner_views.xml',
        'views/account_move_views.xml',
        'views/customer_parts_views.xml',
        'views/stock_issue_note_views.xml',
        'views/issue_note_views.xml',
        'views/stock_picking_delivery_views.xml',
        'views/material_return_views.xml',
        'views/timesheet_cost_views.xml',
        'views/fsm_task_cancel_actions.xml',
        'views/fsm_project_task.xml',
        'views/fsm_crn_labels_views.xml',
        'views/crn_service_assets.xml',
        'views/crn_service_menus.xml',
        'views/fsm_dashboard_views.xml',
        'views/fsm_material_consumption_views.xml',
        'views/fsm_store_views.xml',
        'views/fsm_store_inventory_menus.xml',
        'views/fsm_test_data_wizard_views.xml',
        'wizard/fsm_stage0_close_wizard_views.xml',
        'views/fsm_crn_ui_cleanup_views.xml',
        'views/sale_order_views.xml',
    ],
    'pre_init_hook': 'pre_init_hook',
    'post_init_hook': 'post_init_hook',
    'qweb': [
        'static/src/xml/crn_service_dashboard.xml',
        'static/src/xml/crn_processing_cycle.xml',
    ],
    'demo': [
        'demo/demo.xml',
    ],
    'application': True,
    'installable': True,
}
