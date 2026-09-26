# Herkunft und Wartung

Basis: Odoo Community **19.0-20260817**, gelesen aus dem installierten Image `nolte-odoo:19.0` am 08.09.2026. Copyright Odoo S.A.; Lizenz LGPL-3. Die abgeleiteten Vorlagen bleiben LGPL-3.

- `addons/sale/report/ir_actions_report_templates.xml`, SHA-256 `a9b17e7f2855f46031cfdbc17e7f573b7086718f3f9d29e1844f5df2b029f7c1`
- `addons/account/views/report_invoice.xml`, SHA-256 `c8008a06b6619a23a898309479ebb9ffa46469b3684d76fcdda8d2d280970e07`

`report/sale_document.xml` enthält eine gezielte Momentaufnahme der Positions- und Steuerausgabe. Bewusster Kompromiss: Isolation von Alt-/Studio-Vererbung statt Vererbung einer möglicherweise veränderten Datenbankansicht. Keine eigene Preis- oder Steuerberechnung; die nativen Odoo-Daten und Methoden werden verwendet.

Bei Odoo-Upgrades **auch innerhalb Version 19** native Methoden, Feldnamen und Vorlagenänderungen vergleichen. Nicht ungeprüft auf Odoo 20 oder ältere Hauptversionen übertragen. Generator und vollständiger Quellcode werden im Arbeitspaket aufbewahrt; das Installationsmodul benötigt den Generator nicht.

## Nicht übernommene Altlasten

Das gelesene `nolte_berichte` (Manifest 19.0.1.2.0) enthält:

- `account_journal.py`: Warnungen zu Bankauszügen mit Stichtag 01.01.2024. Gehört nicht in ein Berichtsmodul; nicht übernommen. Vor späterer Deinstallation separat bewerten, weil diese auch fachliches Verhalten verändert.
- `account_move.py`: parallele `x_l10n_german_*`-Berechnungsfelder mit als Text kodierten Listen. Im gelesenen Modul keine verwendenden QWeb-Verweise gefunden; Nutzung durch andere Module/Studio ist nicht ausgeschlossen. Nicht übernommen.
- Feste/überschriebene DIN5008-Abstände und allgemein wirkende SCSS-Selektoren. Im neuen Angebot durch eigene abgegrenzte Klassen ersetzt.
- Direkter SCSS-Link zusätzlich zum Asset-Bundle. Nicht übernommen.
- `ceo_title`: im gelesenen Berichts-XML nicht verwendet. Nicht übernommen.
- Zwei Geschäftsführerfelder und fünfspaltiger Fußbereich: funktional erhalten, eigene Feldnamen plus lesender Übergang.
- CSV-Import-Notizschutz: funktional erhalten; lange HTML-Notizen werden nicht mehr pauschal in Plaintext umgewandelt.

Keine Altdatei wurde auf dem Produktivsystem geändert oder gelöscht. Rechnungen/Einkauf/Lager sind weiterhin gesondert zu auditieren, bevor das alte Modul entfernt werden darf.
