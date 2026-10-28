from odoo import api, models


class IrActionsReport(models.Model):
    _inherit = "ir.actions.report"

    @api.model
    def _build_wkhtmltopdf_args(self, paperformat_id, landscape,
                              specific_paperformat_args=None, set_viewport_size=False):
        args = super()._build_wkhtmltopdf_args(
            paperformat_id, landscape, specific_paperformat_args, set_viewport_size)
        service_format = self.env.ref(
            "nolte_stundenbericht.paperformat_customer_service_report", raise_if_not_found=False)
        if service_format and paperformat_id == service_format:
            # The custom report uses self-contained page fragments. Their
            # UTF-8 metadata can be lost during Odoo's body extraction.
            # Set the renderer's encoding explicitly without changing layout.
            args.extend(["--encoding", "utf-8"])
        return args
