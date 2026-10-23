/** @odoo-module **/
import { registry } from "@web/core/registry";
import { ListController } from "@web/views/list/list_controller";
import { listView } from "@web/views/list/list_view";
import { FormController } from "@web/views/form/form_controller";
import { formView } from "@web/views/form/form_view";

const intakeAction = "nolte_stundenbericht.action_nolte_service_intake_wizard";

class ServiceReportListController extends ListController {
    async createRecord() {
        return this.actionService.doAction(intakeAction);
    }
}

class ServiceReportFormController extends FormController {
    async create() {
        const record = this.model.root;
        if (await record.isDirty()) {
            const saved = await record.save({onError: (error, options) => this.onSaveError(error, options, true)});
            if (!saved) return;
        }
        return this.actionService.doAction(intakeAction);
    }
}

registry.category("views").add("nolte_service_report_list", {
    ...listView, Controller: ServiceReportListController,
});
registry.category("views").add("nolte_service_report_form", {
    ...formView, Controller: ServiceReportFormController,
});
