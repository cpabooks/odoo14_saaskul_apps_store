odoo.define("cpabooks_faff.process_flow", function (require) {
    "use strict";

    var AbstractAction = require("web.AbstractAction");
    var core = require("web.core");

    var _t = core._t;

    var FLOW_ROWS = [
        [
            {
                n: 1,
                title: "CRM Lead / Opportunity",
                system: "CRM",
                icon: "fa-users",
                color: "#2563eb",
                tasks: [
                    "Create Lead / Opportunity",
                    "Customer Details",
                    "Contact Person",
                    "Site / Project Location",
                    "Job Type (FA / FF)",
                    "Sales Person",
                ],
                xmlid: "cpabooks_faff.action_faff_crm",
            },
            {
                n: 2,
                title: "Site Visit / Inspection",
                system: "FAFF",
                icon: "fa-map-marker",
                color: "#16a34a",
                tasks: [
                    "Site Visit",
                    "Existing System",
                    "Requirement / Problem",
                    "Observations",
                    "Photos",
                    "Recommendation",
                ],
                xmlid: "cpabooks_faff.action_faff_visit",
            },
            {
                n: 3,
                title: "Estimation (BOQ + Costing)",
                system: "FAFF",
                icon: "fa-calculator",
                color: "#ea580c",
                tasks: [
                    "Prepare BOQ",
                    "Cost of Material",
                    "Labour Cost",
                    "Other Costs",
                    "Margin %",
                    "Selling Price",
                ],
                xmlid: "cpabooks_faff.action_faff_estimate",
            },
            {
                n: 4,
                title: "Quotation",
                system: "Sales",
                icon: "fa-file-text-o",
                color: "#7c3aed",
                tasks: [
                    "Create Quotation",
                    "Terms & Conditions",
                    "Validity",
                    "Attach BOQ",
                    "Send to Customer",
                ],
                xmlid: "cpabooks_faff.action_faff_quotations",
            },
            {
                n: 5,
                title: "Confirm Quotation",
                system: "Sales",
                icon: "fa-check-square-o",
                color: "#0f766e",
                tasks: [
                    "Customer Approval",
                    "Confirm Sale Order",
                    "Convert to Project",
                ],
                xmlid: "cpabooks_faff.action_faff_confirmed_orders",
            },
        ],
        [
            {
                n: 6,
                title: "Project + Tasks",
                system: "Project",
                icon: "fa-tasks",
                color: "#b45309",
                tasks: [
                    "Create Project",
                    "Default Tasks",
                    "Assign Engineer",
                    "Planned Dates",
                ],
                xmlid: "cpabooks_faff.action_faff_projects",
            },
            {
                n: 7,
                title: "Material Arrangement",
                system: "Inventory",
                icon: "fa-cubes",
                color: "#1e3a8a",
                tasks: [
                    "Check Material Requirement",
                    "In Stock → Issue",
                    "Not in Stock → RFQ / PO",
                ],
                xmlid: "cpabooks_faff.action_faff_material",
            },
            {
                n: 8,
                title: "Execution (Job Work)",
                system: "Project",
                icon: "fa-wrench",
                color: "#166534",
                tasks: [
                    "Execute Work as per Tasks",
                    "Manpower Hours",
                    "Progress Photos",
                    "Site Updates",
                ],
                xmlid: "cpabooks_faff.action_faff_execution_jobs",
            },
            {
                n: 9,
                title: "Testing & Commissioning",
                system: "FAFF",
                icon: "fa-check-circle",
                color: "#0891b2",
                tasks: [
                    "Panel / Devices / Pump",
                    "Alarm & Cause-Effect",
                    "Pass or Rectification",
                ],
                xmlid: "cpabooks_faff.action_faff_testing",
            },
        ],
        [
            {
                n: 10,
                title: "Delivery Note / Completion",
                system: "FAFF",
                icon: "fa-handshake-o",
                color: "#9333ea",
                tasks: [
                    "Work Completion",
                    "Customer Signature",
                    "Handover Note",
                    "Warranty",
                ],
                xmlid: "cpabooks_faff.action_faff_completion",
            },
            {
                n: 11,
                title: "Invoice",
                system: "Accounting",
                icon: "fa-file-text",
                color: "#be123c",
                tasks: [
                    "Create Invoice from SO",
                    "Post Invoice",
                    "Link to FAFF Job",
                ],
                xmlid: "cpabooks_faff.action_faff_invoices",
            },
            {
                n: 12,
                title: "Payment",
                system: "Accounting",
                icon: "fa-money",
                color: "#15803d",
                tasks: [
                    "Register Payment",
                    "Full or Partial",
                    "Update Job Balance",
                ],
                xmlid: "cpabooks_faff.action_faff_payments",
            },
            {
                n: 13,
                title: "Job Closing",
                system: "FAFF",
                icon: "fa-flag-checkered",
                color: "#334155",
                tasks: [
                    "All documents linked",
                    "Mark job Finished",
                    "Archive / Close",
                ],
                xmlid: "cpabooks_faff.action_faff_job_closed",
            },
        ],
    ];

    var FaffProcessFlowAction = AbstractAction.extend({
        contentTemplate: "FaffProcessFlow",
        xmlDependencies: ["/cpabooks_faff/static/src/xml/faff_process_flow.xml"],
        events: {
            "click .o_faff_flow_card": "_onCardClick",
            "click .o_faff_flow_start": "_onStartClick",
        },

        start: function () {
            var self = this;
            this.set("title", _t("FAFF Process Flow"));
            try {
                require("cpabooks_faff.shell").requestSyncSidebar(true);
            } catch (e) {
                /* ignore */
            }
            return this._super.apply(this, arguments).then(function () {
                self._renderBoard();
            });
        },

        _renderBoard: function () {
            var $board = this.$(".o_faff_flow_board").empty();
            _.each(FLOW_ROWS, function (row, rowIdx) {
                var $row = $('<div class="o_faff_flow_row"/>');
                _.each(row, function (step, idx) {
                    if (idx) {
                        $row.append($('<div class="o_faff_flow_arrow"><i class="fa fa-arrow-right"/></div>'));
                    }
                    var $ul = $("<ul/>");
                    _.each(step.tasks, function (task) {
                        $ul.append($("<li/>").text(task));
                    });
                    var $card = $('<a href="#" class="o_faff_flow_card"/>')
                        .attr("data-xmlid", step.xmlid)
                        .css("--faff-step", step.color)
                        .append(
                            $('<div class="o_faff_flow_card_top"/>').append(
                                $('<span class="o_faff_flow_icon"><i class="fa ' + step.icon + '"/></span>'),
                                $('<span class="o_faff_flow_num"/>').text(step.n)
                            ),
                            $('<div class="o_faff_flow_card_title"/>').text(step.title),
                            $ul,
                            $('<div class="o_faff_flow_sys"/>').text("System: " + step.system)
                        );
                    $row.append($card);
                });
                $board.append($row);
                if (rowIdx < FLOW_ROWS.length - 1) {
                    $board.append(
                        $('<div class="o_faff_flow_down"><i class="fa fa-arrow-down"/></div>')
                    );
                }
            });
        },

        _onCardClick: function (ev) {
            ev.preventDefault();
            var xmlid = $(ev.currentTarget).data("xmlid");
            if (xmlid) {
                this.do_action(xmlid);
            }
        },

        _onStartClick: function (ev) {
            ev.preventDefault();
            this.do_action("cpabooks_faff.action_faff_job_wizard");
        },
    });

    core.action_registry.add("faff_process_flow", FaffProcessFlowAction);
    return FaffProcessFlowAction;
});
