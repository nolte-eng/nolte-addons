"""Presentation-only normalization; never change payment-term master data."""
import re

from lxml import html
from markupsafe import Markup


def clean_payment_note(note):
    if not note:
        return Markup('')
    root = html.fragment_fromstring(str(note), create_parent='div')
    nodes = root.xpath('.//text()[normalize-space()]')
    if nodes:
        first = nodes[0]
        cleaned = re.sub(r'^\s*Zahlungsbedingungen\s*:\s*', '', str(first), count=1, flags=re.IGNORECASE)
        if cleaned != str(first):
            if first.is_tail:
                first.getparent().tail = cleaned
            else:
                first.getparent().text = cleaned
    # Input is Odoo's sanitized HTML field, not arbitrary user-provided markup.
    return Markup(html.tostring(root, encoding='unicode'))
