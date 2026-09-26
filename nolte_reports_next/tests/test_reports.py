from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestNolteReportsNext(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.partner = cls.env["res.partner"].create({
            "name": "Musterkunde Werkzeugmaschinen und Präzisionsfertigung GmbH & Co. KG",
            "ref": "K-12345", "street": "Lange Industriestraße 123", "zip": "40764", "city": "Langenfeld",
        })
        cls.product = cls.env["product.product"].create({"name": "Prüfmaschine", "list_price": 95000})
        cls.order = cls.env["sale.order"].create({"partner_id": cls.partner.id})
        cls.env["sale.order.line"].create({
            "order_id": cls.order.id, "product_id": cls.product.id,
            "product_uom_qty": 1, "price_unit": 95000,
            "name": "Prüfmaschine\n" + "Technische Daten: lange Beschreibung ohne Abschneiden.\n" * 65,
        })

    def render(self, report="nolte_reports_next.report_saleorder", orders=None):
        return self.env["ir.actions.report"]._render_qweb_html(report, (orders or self.order).ids)[0].decode()

    def test_render_and_customer_number(self):
        before = self.order.amount_total
        html = self.render()
        self.assertIn("K-12345", html)
        self.assertIn("nn-sender", html)
        self.assertIn("Technische Daten", html)
        self.assertEqual(before, self.order.amount_total)

    def test_empty_reference(self):
        self.partner.ref = False
        self.assertNotIn("Kundennummer", self.render())

    def test_payment_note_heading(self):
        from ..models.payment_note import clean_payment_note
        from lxml import html
        cases = [
            ('<p>Zahlungsbedingungen: 15 Tage</p>', '15 Tage'),
            ('<p><strong>Zahlungsbedingungen:</strong> 15 Tage</p>', ' 15 Tage'),
            ('<p>Zahlungsbedingungen:<br/>50 % sofort<br/>25 % Lieferung<br/>25 % Abnahme</p>', '50 % sofort25 % Lieferung25 % Abnahme'),
            ('<p>15 Tage</p>', '15 Tage'),
            ('<p>Es gelten folgende Zahlungsbedingungen: 15 Tage.</p>', 'Es gelten folgende Zahlungsbedingungen: 15 Tage.'),
        ]
        for source, expected in cases:
            self.assertEqual(html.fromstring(str(clean_payment_note(source))).text_content(), expected)
        self.assertEqual(str(clean_payment_note(False)), '')

    def test_commercial_reference(self):
        child = self.env["res.partner"].create({"name": "Einkauf", "parent_id": self.partner.id, "ref": "KONTAKT"})
        self.order.partner_id = child
        self.assertEqual(self.order._nolte_next_customer_reference(), "K-12345")

    def test_opt_in_and_rollback(self):
        self.company.nolte_next_sale_enabled = False
        self.assertNotIn('class="article nn-report"', self.render("sale.report_saleorder"))
        self.company.nolte_next_sale_enabled = True
        self.assertIn('class="article nn-report"', self.render("sale.report_saleorder"))
        self.company.nolte_next_sale_enabled = False
        self.assertNotIn('class="article nn-report"', self.render("sale.report_saleorder"))

    def test_csv_internal_note(self):
        self.order.note = "<p>CSV Import: internes Diagnoseprotokoll</p>"
        self.assertNotIn("internes Diagnoseprotokoll", self.render())
        self.order.note = "<p>Vertragsbedingungen <b>unverändert</b></p>"
        self.assertIn("Vertragsbedingungen", self.render())

    def test_section_note_discount_and_multiple_taxes(self):
        tax = self.env["account.tax"].create({"name": "USt 19%", "amount": 19, "type_tax_use": "sale"})
        self.order.order_line.tax_ids = tax
        self.order.order_line.discount = 5
        self.env["sale.order.line"].create([
            {"order_id": self.order.id, "display_type": "line_section", "name": "Montage", "sequence": 30},
            {"order_id": self.order.id, "display_type": "line_note", "name": "Abrechnung nach Aufwand", "sequence": 40},
        ])
        html = self.render()
        self.assertIn("Rabatt %", html)
        self.assertIn("Montage", html)
        self.assertIn("Abrechnung nach Aufwand", html)
        self.assertIn("Gesamtbetrag", html)

    def test_proforma_and_multi_order(self):
        self.company.nolte_next_sale_enabled = True
        self.assertIn("Pro-forma-Rechnung", self.render("sale.report_saleorder_pro_forma"))
        other = self.order.copy()
        html = self.render(orders=self.order | other)
        self.assertEqual(html.count('class="article nn-report"'), 2)

    def test_directors(self):
        self.company.nolte_next_director_1 = "Test Geschäftsführung"
        self.assertIn("Test Geschäftsführung", self.render())

    def test_paperformat_scoped_to_sale(self):
        report = self.env.ref("sale.action_report_saleorder")
        self.assertEqual(
            report.with_context(nolte_next_paperformat=True).get_paperformat(),
            self.env.ref("nolte_reports_next.paperformat_next"),
        )
        self.assertEqual(report.with_context(nolte_next_paperformat=False).get_paperformat(), report.get_paperformat())

    def test_legacy_layout_coexistence(self):
        legacy = self.env.ref("l10n_din5008.external_layout_din5008", raise_if_not_found=False)
        if not legacy:
            self.skipTest("Legacy DIN5008 not installed in this test environment")
        self.company.external_report_layout_id = legacy
        self.company.nolte_next_sale_enabled = True
        self.assertIn("K-12345", self.render("sale.report_saleorder"))
        if "ceo_01" in self.company._fields:
            self.company.nolte_next_director_1 = False
            self.company.ceo_01 = "Geschäftsführung aus Altmodul"
            self.assertIn("Geschäftsführung aus Altmodul", self.render())

    def test_pdf_structure(self):
        report = self.env["ir.actions.report"]
        bodies, ids, header, footer, args = report._prepare_html(self.render(), report_model="sale.order")
        self.assertEqual(ids, self.order.ids)
        self.assertEqual(len(bodies), 1)
        for fragment in (bodies[0], header, footer):
            self.assertIn(b"#58728b", fragment if isinstance(fragment, bytes) else fragment.encode())

    def test_pdf_section_heading_group(self):
        self.env['sale.order.line'].create({'order_id':self.order.id, 'sequence':0, 'display_type':'line_section', 'name':'Montagegruppe'})
        bodies, *_ = self.env['ir.actions.report']._prepare_html(self.render(), report_model='sale.order')
        from lxml import html
        root = html.fromstring(bodies[0])
        groups = root.xpath("//table[contains(@class, 'nn-section-start')]/tbody")
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0].findall('tr')), 2)
        self.assertIn('Montagegruppe', groups[0].text_content())
        self.assertIn('Prüfmaschine', groups[0].text_content())

    def test_mail_report_record_paperformat(self):
        import io
        from unittest.mock import patch
        from odoo.tools.pdf import PdfFileWriter
        self.company.nolte_next_sale_enabled = True
        report = self.env['ir.actions.report'].with_context(force_report_rendering=True, report_pdf_no_attachment=True)
        action = self.env.ref('sale.action_report_saleorder')
        expected = self.env.ref('nolte_reports_next.paperformat_next')
        checked = []
        def fake_pdf(record, bodies, report_ref=False, **kwargs):
            checked.append(record._get_report(report_ref).get_paperformat())
            writer = PdfFileWriter()
            writer.addBlankPage(595, 842)
            stream = io.BytesIO()
            writer.write(stream)
            return stream.getvalue()
        with patch.object(type(report), '_run_wkhtmltopdf', autospec=True, side_effect=fake_pdf):
            report._render_qweb_pdf(action, res_ids=self.order.ids)
        self.assertEqual(checked, [expected])
