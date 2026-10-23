from odoo import _, models
from odoo.exceptions import AccessError


class ProjectTask(models.Model):
    _inherit = "project.task"

    def action_open_nolte_customer_history(self):
        self.ensure_one()
        if not self.env.user.has_group("nolte_stundenbericht.group_stundenbericht_user"):
            raise AccessError(_("Sie dürfen keine Kundenhistorie öffnen."))
        if self.env.user not in self.user_ids:
            raise AccessError(_("Die Kundenhistorie ist nur für Ihnen zugewiesene Einsätze verfügbar."))
        return {
            "type": "ir.actions.act_url",
            "url": "/my/stundenbericht/history/%s" % self.id,
            "target": "new",
        }
