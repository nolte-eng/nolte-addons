from odoo import Command
from odoo.tests.common import TransactionCase


class TestNolteMachineSpareparts(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create({"name": "Testkunde"})
        cls.machine = cls.env["product.product"].create({"name": "Testmaschine"})
        cls.spare_part = cls.env["product.product"].create({"name": "Testersatzteil"})
        cls.bom = cls.env["mrp.bom"].create(
            {
                "product_tmpl_id": cls.machine.product_tmpl_id.id,
                "product_qty": 1.0,
                "product_uom_id": cls.machine.uom_id.id,
                "bom_line_ids": [
                    Command.create(
                        {
                            "product_id": cls.spare_part.id,
                            "product_qty": 2.0,
                            "product_uom_id": cls.spare_part.uom_id.id,
                        }
                    )
                ],
            }
        )
        cls.equipment = cls.env["maintenance.equipment"].create(
            {
                "name": "Testanlage",
                "partner_id": cls.partner.id,
                "product_id": cls.machine.id,
            }
        )

    def test_bom_is_found(self):
        self.assertEqual(self.equipment.bom_id, self.bom)

    def test_create_quotation_from_bom(self):
        wizard = self.env["nolte.spareparts.quotation.wizard"].create(
            {"equipment_id": self.equipment.id}
        )
        wizard._onchange_equipment_id()
        self.assertEqual(len(wizard.line_ids), 1)
        action = wizard.action_create_or_update_quotation()
        order = self.env["sale.order"].browse(action["res_id"])
        self.assertEqual(order.partner_id, self.partner)
        self.assertEqual(order.order_line.product_id, self.spare_part)
        self.assertEqual(order.order_line.product_uom_qty, 2.0)
