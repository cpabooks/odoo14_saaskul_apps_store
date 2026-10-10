# -*- coding: utf-8 -*-
import logging

from odoo import api, models
from odoo.tools.template_inheritance import locate_node

_logger = logging.getLogger(__name__)


class IrUiView(models.Model):
    _inherit = 'ir.ui.view'

    def _cpabooks_drop_optional_missing_xpaths(self, source, specs_tree):
        """Odoo 16-style optional='True' xpath: skip specs whose target is absent."""
        specs = [specs_tree]
        while specs:
            spec = specs.pop(0)
            if spec.tag == 'data':
                specs.extend(list(spec))
                continue
            if spec.tag != 'xpath':
                continue
            optional = (spec.get('optional') or '').strip().lower()
            if optional not in ('1', 'true', 'optional'):
                continue
            if spec.get('expr') and locate_node(source, spec) is None:
                parent = spec.getparent()
                if parent is not None:
                    parent.remove(spec)
                    _logger.info(
                        'Saaskul Field Service: skipped optional xpath %s on view %s',
                        spec.get('expr'),
                        self.name or self.id,
                    )

    def apply_inheritance_specs(self, source, specs_tree, pre_locate=lambda s: True):
        try:
            self._cpabooks_drop_optional_missing_xpaths(source, specs_tree)
        except Exception:
            _logger.exception(
                'Saaskul Field Service: optional xpath cleanup failed on view %s',
                self.name or self.id,
            )
        try:
            return super().apply_inheritance_specs(
                source, specs_tree, pre_locate=pre_locate,
            )
        except TypeError:
            return super().apply_inheritance_specs(source, specs_tree)

    @api.model
    def cpabooks_unlink_views_by_xmlid(self, *xmlids):
        """Delete stale inherited views without logging missing XML IDs.

        Odoo's XML <delete> tag logs a traceback when the XML ID is absent.
        These cleanup calls are intentionally idempotent during upgrades.
        """
        if len(xmlids) == 1 and isinstance(xmlids[0], (list, tuple, set)):
            xmlids = xmlids[0]

        module = 'saaskul_field_service'
        names = [
            xmlid.split('.', 1)[1] if '.' in xmlid else xmlid
            for xmlid in (xmlids or [])
        ]
        if not names:
            return True

        data_records = self.env['ir.model.data'].sudo().search([
            ('module', '=', module),
            ('name', 'in', names),
            ('model', '=', 'ir.ui.view'),
        ])
        views = self.sudo().browse(data_records.mapped('res_id')).exists()
        if views:
            views.unlink()
        if data_records:
            data_records.unlink()
        return True
