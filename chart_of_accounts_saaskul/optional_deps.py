# -*- coding: utf-8 -*-
"""Shared helpers for optional Enterprise module hooks."""
import sys


def module_installed(module_name):
    """Return True if module_name is installed in the current db_name."""
    try:
        from odoo import sql_db, tools

        db_name = tools.config.get("db_name")
        if db_name in (None, False, "", "False"):
            if "-d" in sys.argv:
                db_name = sys.argv[sys.argv.index("-d") + 1]
        if isinstance(db_name, (list, tuple)):
            db_name = db_name[0] if db_name else None
        if not db_name:
            return False
        conn = sql_db.db_connect(db_name)
        cr = conn.cursor()
        try:
            cr.execute(
                "SELECT state FROM ir_module_module WHERE name=%s",
                (module_name,),
            )
            row = cr.fetchone()
            return bool(row and row[0] in ("installed", "to upgrade"))
        finally:
            cr.close()
            conn.close()
    except Exception:
        return False
