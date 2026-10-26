"""Retain an unambiguous existing customer checklist as the company default."""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for company in env["res.company"].search([]):
        template = company.nolte_checklist_template_id
        if not template:
            candidates = env["nolte.service.checklist.template"].search([
                ("company_id", "=", company.id), ("visibility", "=", "customer"),
            ], limit=2)
            if len(candidates) != 1:
                continue
            template = candidates
            company.nolte_checklist_template_id = template
            _logger.info("Preserved existing customer checklist as default for company %s", company.id)
        if template.visibility == "customer" and template.company_id == company and template.name in ("Checkliste", "Pauschalen"):
            template.name = "Einsatzabschluss"
