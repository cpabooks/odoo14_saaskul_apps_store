# -*- coding: utf-8 -*-
from odoo import _, api, models


class BaseImport(models.TransientModel):
    _inherit = 'base_import.import'

    # Many2one fields created by name on VAR Work Import (after user confirms).
    VAR_CREATE_FIELDS = {
        'cpabooks.cafm.var.work': {
            'l2_level_id': 'cpabooks.cafm.customer.group',
            'l3_level_id': 'project.project',
            'partner_id': 'res.partner',
            'work_type_id': 'cpabooks.cafm.work.type',
            'technician_id': 'cpabooks.cafm.technician',
            'cafm_unit_id': 'cpabooks.cafm.unit',
        },
    }

    def do(self, fields, columns, options, dryrun=False):
        options = dict(options or {})
        enabled = dict(options.get('name_create_enabled_fields') or {})
        for fname in (self.VAR_CREATE_FIELDS.get(self.res_model) or {}):
            enabled[fname] = True
        options['name_create_enabled_fields'] = enabled
        return super().do(fields, columns, options, dryrun=dryrun)

    @api.model
    def var_preview_missing_related(self, import_id, fields, columns, options):
        """List related names missing in DB — confirm dialog before Import."""
        wizard = self.browse(import_id)
        if not wizard.exists():
            return {'message': False, 'details': {}}
        mapping = wizard.VAR_CREATE_FIELDS.get(wizard.res_model)
        if not mapping:
            return {'message': False, 'details': {}}

        options = dict(options or {})
        try:
            data, import_fields = wizard._convert_import_data(fields, options)
            data = wizard._parse_import_data(data, import_fields, options)
        except Exception:
            return {'message': False, 'details': {}}

        details = {}
        for fname, model_name in mapping.items():
            col_idx = None
            for i, f in enumerate(import_fields):
                if not f:
                    continue
                if f.endswith('/id') or f.endswith('/.id'):
                    continue
                if f == fname or f.startswith(fname + '/'):
                    col_idx = i
                    break
            if col_idx is None:
                continue

            names = set()
            for row in data:
                if col_idx >= len(row):
                    continue
                val = row[col_idx]
                if val is None or val is False:
                    continue
                val = str(val).strip()
                if val:
                    names.add(val)
            if not names:
                continue

            Model = wizard.env[model_name]
            missing = []
            for name in sorted(names, key=lambda n: n.lower()):
                found = Model.name_search(name=name, operator='=', limit=1)
                if not found:
                    # also try ilike exact for casing
                    found = Model.search([('name', '=ilike', name)], limit=1)
                if not found:
                    missing.append(name)
            if missing:
                details[Model._description or model_name] = missing

        if not details:
            return {'message': False, 'details': {}}

        blocks = []
        for label, names in details.items():
            shown = names[:40]
            block = '%s (%d):\n- %s' % (label, len(names), '\n- '.join(shown))
            if len(names) > 40:
                block += '\n- ... (+%d more)' % (len(names) - 40)
            blocks.append(block)

        message = _(
            "These records were not found and need to be created to continue import:\n\n%s\n\n"
            "Should we create them and proceed?"
        ) % '\n\n'.join(blocks)
        return {'message': message, 'details': details}
