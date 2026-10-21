from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    sequence = env.ref("nolte_stundenbericht.seq_nolte_service_report", raise_if_not_found=False)
    if sequence:
        sequence.write({
            "prefix": "EB/%(year)s/%(month)s/",
            "padding": 3,
            "use_date_range": True,
        })
    data_record = env["ir.model.data"].search([
        ("module", "=", "nolte_stundenbericht"),
        ("name", "=", "seq_nolte_service_report"),
    ], limit=1)
    if data_record and data_record.noupdate:
        data_record.write({"noupdate": False})
