/** @odoo-module **/

import { registry } from "@web/core/registry";
import { formView } from "@web/views/form/form_view";

// Odoo 19: the ledger form keeps Odoo's own record pager.
registry.category("views").add("account_form_pager", formView);
