# -*- coding: utf-8 -*-
{
 'name': 'Saaskul Recipe Book',
 'summary': 'Restaurant recipe, theoretical food cost, consumption and closing stock control',
 'version': '14.0.1.0.0',
 'category': 'Operations/Restaurant',
 'author': 'Saaskul', 'website': 'https://www.saaskul.co',
 'license': 'LGPL-3',
 'depends': ['base','product','sale_management','stock','purchase'],
 'data': [
   'security/recipe_security.xml','security/ir.model.access.csv',
   'views/recipe_views.xml','views/consumption_views.xml','views/dashboard_views.xml','views/menu.xml',
   'wizard/closing_stock_wizard_views.xml'
 ],
 'images': ['static/description/banner.png'],
 'application': True, 'installable': True,
}
