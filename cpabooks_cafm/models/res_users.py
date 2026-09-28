# -*- coding: utf-8 -*-

import re
import uuid

from lxml import etree

from odoo import api, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model
    def _cpabooks_cafm_assign_manager_group(self):
        manager_group = self.env.ref('cpabooks_cafm.group_cafm_manager', raise_if_not_found=False)
        if manager_group:
            users = self.with_context(active_test=False).search([('share', '=', False)])
            manager_group.write({'users': [(4, user.id) for user in users]})

    @api.model
    def fields_get(self, allfields=None, attributes=None):
        res = super().fields_get(allfields=allfields, attributes=attributes)
        if self.env.context.get('cafm_quick_user') and 'login' in res:
            res['login']['required'] = False
        return res

    @api.model
    def fields_view_get(self, view_id=None, view_type='form', toolbar=False, submenu=False):
        res = super().fields_view_get(
            view_id=view_id, view_type=view_type, toolbar=toolbar, submenu=submenu
        )
        if self.env.context.get('cafm_quick_user') and view_type == 'form':
            if 'login' in res.get('fields', {}):
                res['fields']['login']['required'] = False
            try:
                doc = etree.XML(res['arch'])
            except etree.XMLSyntaxError:
                return res
            for node in doc.xpath("//field[@name='login']"):
                node.set('required', '0')
                modifiers = node.get('modifiers')
                if modifiers:
                    # Keep other modifiers; force required false for client validation.
                    import json
                    try:
                        mod = json.loads(modifiers)
                        mod['required'] = False
                        node.set('modifiers', json.dumps(mod))
                    except Exception:
                        node.set('modifiers', '{"required": false}')
                else:
                    node.set('modifiers', '{"required": false}')
            res['arch'] = etree.tostring(doc, encoding='unicode')
        return res

    def _cafm_generate_login(self, name):
        """Internal login only — not shown as email and not copied to email."""
        base = re.sub(r'[^a-z0-9]+', '.', (name or 'user').strip().lower()).strip('.')
        if not base:
            base = 'user'
        login = '%s.%s' % (base, uuid.uuid4().hex[:8])
        Users = self.sudo().with_context(active_test=False)
        while Users.search_count([('login', '=', login)]):
            login = '%s.%s' % (base, uuid.uuid4().hex[:8])
        return login

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.context.get('cafm_quick_user'):
            for vals in vals_list:
                login = (vals.get('login') or '').strip()
                email = (vals.get('email') or '').strip()
                if login:
                    vals['login'] = login
                    if not email and '@' in login:
                        vals['email'] = login
                else:
                    # Email left empty in UI: keep email empty; set technical login only.
                    vals['login'] = self._cafm_generate_login(vals.get('name') or 'user')
                    vals['email'] = email or False
        return super().create(vals_list)
