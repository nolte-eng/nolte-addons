# Nolte Berichte – Next (Odoo 19)

Eigenständiger Ersatz **für die Verkaufsberichtsausgabe**: Angebote, Auftragsbestätigungen und Pro-forma-Ausgabe. Kein vollständiger Ersatz für Rechnungs-, Einkaufs- oder Lagerberichte des Altmoduls.

## Sichere Einführung

1. Vor Installation Datenbank und Filestore sichern, Wiederherstellung prüfen.
2. ZIP entpacken und den Ordner `nolte_reports_next` in einen tatsächlich konfigurierten Addons-Pfad legen. Odoo neu starten, App-Liste aktualisieren, Modul installieren. Nicht per Studio und nicht über den PDF-Angebotsbauer importieren.
3. Installation zunächst in einer Testkopie des Produktivsystems. Das Modul aktiviert **keine globale Umstellung** bei Installation.
4. Im Angebot den Druckeintrag **Angebot / Auftrag – Nolte Next (Test)** verwenden. Dieser zeigt ausschließlich den Berichtsinhalt; PDF-Angebotsbauer-Vorspann/Nachspann sind bei diesem separaten Druckeintrag nicht enthalten.
5. Unter Einstellungen → Unternehmen → Firma → „Nolte Berichte – Next“ Geschäftsführung prüfen/eintragen. Solange das Altmodul installiert ist, können leere neue Geschäftsführerfelder lesend auf `ceo_01`/`ceo_02` zurückfallen. Vor dessen Deinstallation die Werte explizit in die neuen Felder kopieren.
6. Erst nach Abnahme „Neues Layout für alle Angebote und Aufträge“ aktivieren. Das gilt für alle Angebotsvorlagen **dieser Firma** und die normale Verkaufs-PDF-Ausgabe. Andere Firmen bleiben unverändert. Bei mehreren Firmen je Firma entscheiden.
7. Standarddruck, E-Mail-PDF-Anhang, Portal-PDF, Pro-forma sowie PDF-Angebotsbauer in der Testkopie prüfen. Dessen Enterprise-Erweiterungen und dynamische PDF-Felder sind nicht Teil dieses Moduls. Eigenständige Drittanbieter-Berichtsaktionen, die den normalen Verkaufsbericht umgehen, werden nicht automatisch umgestellt.

**Rollback:** Firmen-Schalter deaktivieren. Das ursprüngliche Dokument und seine Studio-Anpassungen wurden nicht ersetzt; Standarddruck verwendet wieder das bisherige Layout. Keine Deinstallation des Altmoduls als Teil dieser Umstellung durchführen.

## Gestaltung

- Weißes Papier, navyfarbene Titel, blaugraue Absenderzeile und Feldbeschriftungen, hellblaue Trennlinien, sehr helle Tabellen und Summen.
- Keine Werbezeile unter „Angebot“, kein Unternehmensslogan im Kopf.
- Unverzerrtes Firmenlogo aus den Unternehmensdaten.
- Kundenadresse ohne feste Höhe/Abschneidung, vorhandener Datenblock um Kundennummer ergänzt.
- Kundennummer: Standardfeld `res.partner.ref`, zuerst Geschäftspartner/Firma, dann ausgewählter Kontakt. Keine erfundene Nummer; leere Zeile entfällt. Bei Nutzung eines anderen individuellen Nummernfelds muss die Zuordnung vor Aktivierung angepasst werden.
- Fünfspaltige Fußzeile in der bisherigen Aufteilung: Firma/Adresse, Kontakt, Steuer-/Registerdaten/Fußtext, Geschäftsführung, Bankdaten (erste zwei Konten wie im Altmodul). Seitenangabe mit Belegnummer, nur Farben angepasst.
- Wiederholter Tabellenkopf, teilbare lange Produktbeschreibungen/Notizen, Abschnittsüberschriften möglichst mit Folgeinhalt, zusammengehaltene Summen.
- Firmenlogo, Kontaktdaten, Bankdaten und rechtliche Angaben bleiben dynamisch. Kein Stammdaten-Overwrite.
- Keine pauschale Änderung von Vertragstexten, Preisen, Steuern, Zahlungsbedingungen oder Artikeln. Interne Notizen mit Präfix `CSV Import:` bleiben wie bisher ausgeblendet.

## Aufbau und Grenzen

Drei Model-Erweiterungen für Konfiguration, Kundennummer/Notizfilter sowie Papierformat und PDF-Umbruch; keine Abhängigkeit von `nolte_berichte`, Studio oder DIN5008. Bestehende Geschäftsdaten bleiben erhalten. Keine neuen Zugriffsrechte auf Geschäftsdaten und keine sudo-Lesezugriffe auf Angebote.

Eigene QWeb-Dokumente verhindern, dass alte Studio-XPaths auf `sale.report_saleorder_document` das neue Dokument verändern. Die Odoo-19-Positions-/Steuerdarstellung wurde aus dem tatsächlich installierten Community-Quellcode abgeleitet, nicht aus bearbeiteten Datenbankansichten. Dadurch bleiben Rabatt, Steuergruppen, Abschnitte/Unterabschnitte, Kombinationen und zusammengefasste Abschnitte strukturell erhalten. Fremde globale CSS-Regeln und tiefgreifende Python-Overrides müssen trotzdem in der Testkopie überprüft werden.

Die Oberfläche des Kundenportals wird nicht umgestaltet, nur dessen normale Verkaufs-PDF-Ausgabe nach Aktivierung. Das Modul ist für deutschsprachige Dokumente konzipiert; statische neue Beschriftungen sind deutsch. Es beansprucht keine geprüfte DIN5008-Konformität für Fensterumschläge. A4-Ränder 18/14 mm, Kopf 34 mm, Fuß 30 mm; das bisherige Firmenpapierformat wird nicht überschrieben. Gemischte Alt-/Neu-Sammeldrucke behalten das bisherige Papierformat und sollten getrennt gedruckt werden.

## Tests

Odoo-Modultests: `--test-enable --test-tags /nolte_reports_next --stop-after-init`.
Sie prüfen Rendering, Referenzvererbung, leere Nummer, Notizschutz, Geschäftsführer, Rabatt/Abschnitte, Pro-forma, Mehrfachdruck, Umschaltung/Rollback und die PDF-HTML-Struktur.
Echte wkhtmltopdf-Ausgabe wird zusätzlich außerhalb der transaktionalen Modultests geprüft (deren uncommittete Asset-Datensätze können den PDF-Renderer blockieren).

Stand **19.0.1.0.1**: zusätzlich in einer isolierten Kopie von `sales19e` einschließlich aller installierten Erweiterungen geprüft. 13 Funktionstests erfolgreich; alle sieben vorhandenen Angebotsvorlagen als HTML geprüft. Echte PDFs von fünf vorhandenen Belegen erzeugt. Bei S00179 sind Standarddruck, E-Mail-Anhang und Portal-PDF dateiidentisch. Das Abschalten erzeugt wieder die bisherige PDF. Die Version hält Abschnitt und erste Position zusammen und übernimmt das neue Papierformat auch bei E-Mail-Aufrufen mit einem Report-Datensatz.

Bei QSZ ist das Standard-Referenzfeld derzeit leer; die Kundennummer wird deshalb nicht gedruckt. Die vorhandenen Deckblatt- und AGB-Dokumente bleiben unverändert. Die von Odoo zusammengesetzte Prüf-PDF ist **keine neue ausfüllbare PDF-Vorlage**: Der bestehende Angebotsbauer liefert befüllte Seiten-Widgets, aber keinen kanonischen AcroForm-Feldbaum. Diese vorhandene Einschränkung wird vom Berichtsmodul weder verursacht noch repariert.

Siehe beiliegendes Prüfprotokoll für Details und noch notwendige fachliche Freigaben. **Nicht im Produktivsystem installiert oder aktiviert.** Rechnungen, Einkauf und Lagerberichte bleiben beim Altmodul.
