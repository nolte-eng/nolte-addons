from odoo import models
from lxml import etree, html as lxml_html
from copy import deepcopy


class IrActionsReport(models.Model):
    _inherit = "ir.actions.report"

    def _prepare_html(self, html, report_model=False):
        # wkhtmltopdf ignores keep-with-next on rows and keep-together on tbody.
        # A small nested table inside ONE unbreakable row keeps a heading with
        # its first position. The remaining description stays freely breakable.
        if 'nn-report' in (html.decode('utf-8') if isinstance(html, bytes) else str(html)):
            root = lxml_html.fromstring(html)
            tables = root.xpath("//div[contains(concat(' ', normalize-space(@class), ' '), ' nn-report ')]//table[contains(concat(' ', normalize-space(@class), ' '), ' o_main_table ')]")
            for table in tables:
                headers = table.xpath('./thead/tr/th')
                column_count = len(headers)
                if not column_count:
                    continue
                widths = {'th_quantity': 13, 'th_priceunit': 12,
                          'th_discount': 8, 'th_taxes': 9, 'th_subtotal': 14}
                description_width = 100 - sum(widths.get(h.get('name'), 0) for h in headers)
                columns = etree.Element('colgroup')
                table.set('style', table.get('style', '') + '; table-layout: fixed;')
                for header in headers:
                    etree.SubElement(columns, 'col', style='width: %s%%' % widths.get(header.get('name'), description_width))
                table.insert(0, columns)
                for cell in table.xpath('.//td[@colspan="99"]'):
                    cell.set('colspan', str(column_count))
                for body in list(table.findall('tbody')):
                    rows = list(body)
                    if not any({'o_line_section', 'o_line_subsection'} & set(row.get('class', '').split()) for row in rows):
                        continue
                    offset = table.index(body)
                    table.remove(body)
                    index = 0
                    while index < len(rows):
                        group = etree.Element('tbody', dict(body.attrib))
                        is_heading = bool({'o_line_section', 'o_line_subsection'} & set(rows[index].get('class', '').split()))
                        if is_heading:
                            wrapper = etree.SubElement(group, 'tr', {'class': 'nn-keep-start'})
                            cell = etree.SubElement(wrapper, 'td', {'colspan': str(column_count), 'class': 'nn-group-cell'})
                            nested = etree.SubElement(cell, 'table', {'class': 'nn-section-start table table-borderless'})
                            nested.append(deepcopy(columns))
                            target = etree.SubElement(nested, 'tbody')
                            while index < len(rows) and {'o_line_section', 'o_line_subsection'} & set(rows[index].get('class', '').split()):
                                target.append(rows[index])
                                index += 1
                            if index < len(rows):
                                target.append(rows[index])
                                index += 1
                        else:
                            while index < len(rows) and not ({'o_line_section', 'o_line_subsection'} & set(rows[index].get('class', '').split())):
                                group.append(rows[index])
                                index += 1
                        table.insert(offset, group)
                        offset += 1
            html = lxml_html.tostring(root, encoding='utf-8')
        return super()._prepare_html(html, report_model=report_model)

    def _render_qweb_pdf(self, report_ref, res_ids=None, data=None):
        report = self._get_report(report_ref)
        native_sale = report.report_name in ("sale.report_saleorder", "sale.report_saleorder_pro_forma")
        ids = [res_ids] if isinstance(res_ids, int) else res_ids
        if native_sale and ids:
            orders = self.env["sale.order"].browse(ids)
            # Mixed old/new batches retain the original paper format.
            use_next = bool(orders) and all(orders.mapped("company_id.nolte_next_sale_enabled"))
            self = self.with_context(nolte_next_paperformat=use_next)
            # Mail templates pass a report record, not its name. Odoo's
            # _get_report keeps that record's context, so propagate the flag
            # there as well or emailed PDFs silently use the legacy margins.
            report_ref = report.with_context(nolte_next_paperformat=use_next)
        return super(IrActionsReport, self)._render_qweb_pdf(report_ref, res_ids=res_ids, data=data)

    def get_paperformat(self):
        if self.env.context.get("nolte_next_paperformat") and self.report_name in (
            "sale.report_saleorder", "sale.report_saleorder_pro_forma",
        ):
            return self.env.ref("nolte_reports_next.paperformat_next")
        return super().get_paperformat()
