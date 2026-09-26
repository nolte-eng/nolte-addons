from odoo.tests.common import TransactionCase


class TestCallForPrice(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product = cls.env["product.template"].create(
            {"name": "Preis auf Anfrage", "price_call": True}
        )

    def test_call_for_price_disables_quick_add(self):
        self.assertFalse(self.product._website_show_quick_add())

    def test_request_keeps_existing_model_and_fields(self):
        request = self.env["call.price"].create(
            {
                "product_id": self.product.id,
                "first_name": "Erika",
                "email": "erika@example.com",
                "quantity": 2,
            }
        )
        self.assertEqual(request.product_id, self.product)
        self.assertEqual(request.state, "draft")
