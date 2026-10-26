from uuid import uuid4

from psycopg2 import IntegrityError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger

from ..controllers.api_v1 import NolteStundenberichtApiV1


@tagged("post_install", "-at_install")
class TestChecklistSync(TransactionCase):
    def setUp(self):
        super().setUp()
        self.api = NolteStundenberichtApiV1()
        self.reports = self.env["nolte.service.report"].create([
            {"name": "CHECKLIST-SYNC-A"}, {"name": "CHECKLIST-SYNC-B"},
        ])
        self.key = str(uuid4())
        self.item = {"checklistUuid": self.key, "name": "Internal check", "visibility": "internal", "note": "Keep this note", "checked": True}

    def test_reused_id_in_another_report_is_independent(self):
        first, second = self.reports
        self.api._sync_checklist(first, [self.item])
        self.api._sync_checklist(second, [dict(self.item, name="Second check", checked=False)])
        self.assertNotEqual(first.checklist_ids.id, second.checklist_ids.id)
        self.assertEqual(first.checklist_ids.note, "Keep this note")
        self.assertTrue(first.checklist_ids.checked)
        self.assertFalse(second.checklist_ids.checked)
        self.api._sync_checklist(second, [])
        self.assertFalse(second.checklist_ids)
        self.assertEqual(len(first.checklist_ids), 1)

    def test_repeated_payload_and_ids_update_instead_of_create(self):
        first = self.reports[0]
        self.api._sync_checklist(first, [self.item, dict(self.item, checked=False)])
        item_id = first.checklist_ids.id
        self.assertFalse(first.checklist_ids.checked)
        self.api._sync_checklist(first, [dict(self.item, checked=True)])
        self.assertEqual(first.checklist_ids.id, item_id)
        self.assertEqual(len(first.checklist_ids), 1)
        self.assertTrue(first.checklist_ids.checked)
        self.api._sync_checklist(first, [{"checklistUuid": self.key, "name": "Edited"}])
        self.assertEqual(first.checklist_ids.visibility, "internal")

    def test_database_still_rejects_duplicates_inside_one_report(self):
        first = self.reports[0]
        self.api._sync_checklist(first, [self.item])
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.cr.savepoint():
            self.env["nolte.service.report.checklist"].create({
                "report_id": first.id, "mobile_uuid": self.key, "name": "Duplicate",
            })
