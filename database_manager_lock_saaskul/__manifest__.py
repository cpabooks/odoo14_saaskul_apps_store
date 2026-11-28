# -*- coding: utf-8 -*-
{
    'name': 'Database Manager Lock - Hide & Block Database Manager and Selector',
    'summary': 'Secure the Odoo login page: hide Manage Databases and the database selector, and block /web/database/manager, backup, restore, drop and create URLs. Unlock from odoo.conf when needed.',
    'description': """
Database Manager Lock
=====================
Security for the Odoo login page and database manager.

* Removes the "Manage Databases" link from the login page
* Removes the "Select" database button from the login form
* Returns 404 for /web/database/manager, /web/database/selector and the
  create, duplicate, drop, backup, restore and change password URLs
* Unlock when you need the manager: add ``db_manager_unlock = True`` to the
  Odoo server configuration file and restart Odoo
* Depends only on the web module

Keywords: hide database manager, disable database manager, hide manage
databases, hide database selector, block database backup, secure login page,
database security, lock database manager.
""",
    'version': '19.0.1.0.0',
    'category': 'Extra Tools',
    'author': 'Saaskul',
    'website': 'https://saaskul.com',
    'live_test_url': 'https://saaskul.com/contactus?name=Live%20Preview%20-%20Database%20Manager%20Lock',
    'support': 'info.cpabooks@gmail.com',
    'license': 'OPL-1',
    'price': 10.00,
    'currency': 'USD',
    'images': [
        'static/description/banner.png',
    ],
    'depends': [
        'web',
    ],
    'data': [
        'views/login_templates.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
