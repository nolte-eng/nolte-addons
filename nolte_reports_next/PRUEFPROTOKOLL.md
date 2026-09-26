# Prüfprotokoll – 08.09.2026

## Umgebung

- Installierte Produktivversion **lesend** festgestellt: Odoo 19.0-20260817.
- Altmodul lokal gesichert und geprüft: `nolte_berichte`, Manifest-Version 19.0.1.2.0. Die Produktionsdatenbank führt weiterhin den installierten Stand 19.0.1.0.0; diese bereits vorhandene Abweichung wurde nicht durch ein Upgrade des Altmoduls verändert.
- Test auf demselben Odoo-Image, aber in separaten temporären Containern mit eigener PostgreSQL-Datenbank `nolte_reports_test`, nur synthetischen Daten, internem Netzwerk ohne veröffentlichte Ports und Ressourcenbegrenzung.
- Kein Zugriff der Testanwendung auf die produktive Datenbank oder deren Filestore. Keine Installation/Aktivierung in Produktion.

## Durchgeführt

1. Frische Installation ohne Abhängigkeit von `nolte_berichte`: erfolgreich.
2. Neun ursprüngliche Funktionstests zunächst ohne Altmodul, anschließend mit Altmodul und `l10n_din5008_sale`: erfolgreich.
3. Nach Layoutkorrekturen abschließender Lauf mit **11 Tests, 0 Fehler, 0 Fehlschläge**. Einschließlich expliziter DIN5008-Koexistenz, Geschäftsführerübernahme, Papierformat-Abgrenzung, Umschalten/Zurückschalten, Kundennummer, Leerwert, HTML-Notiz und interner CSV-Notiz, Rabatten, Abschnitten, Pro-forma und Sammelausgabe.
4. Echte PDF-Erzeugung über wkhtmltopdf 0.12.6.1: einseitiges Layoutbeispiel sowie vierseitiger Belastungstest. Alle vier Testseiten visuell geprüft.
5. Textprüfung: alle **95 nummerierten Beschreibungszeilen und 80 nummerierten Notizzeilen** im Belastungstest vorhanden. Kein leeres Deckblatt, keine Überlagerung mit wiederholtem Tabellenkopf oder Logo; Fußbereich auf jeder Seite.
6. Normaler Odoo-Verkaufsdruck nach Aktivierung ebenfalls als echte PDF erzeugt und visuell geprüft; korrekte A4-Ränder und identische Gestaltung.
7. XML-Dateien geparst, Python-Dateien kompiliert. Verpackung ohne Cache-/Bytecode-Dateien.

## Behobene Fehler aus den Testläufen

- QWeb-Felder in Tabellenzellen in erlaubte innere HTML-Elemente verschoben.
- Styles in Kopf, Körper und Fuß jeweils eingebettet, damit Odoo sie beim PDF-Aufteilen erhält.
- Kopfabstand passend zum tatsächlichen PDF-Renderer eingestellt.
- Lange Produktbeschreibungen und Positionsnotizen in kleinere Tabellenzeilen zerlegt, damit der wiederholte Tabellenkopf nicht über laufenden Text gedruckt wird.
- Standardtabellenränder aus Brieffeld und Fußzeile entfernt.

## Ergänzung: tatsächliche Produktionskopie, Version 19.0.1.0.1

- Datenbank `sales19e` mit `pg_dump` lesend kopiert, in eigener PostgreSQL-Instanz als `nolte_sales_stage` wiederhergestellt. Filestore und zusätzlich benötigte Python-Pakete separat kopiert. Kein produktiver Datenbank- oder Filestore-Mount in der Testanwendung.
- Internes Docker-Netzwerk ohne veröffentlichte Ports; ausgehende Verbindungen gesperrt. 87 Cronjobs, vier SMTP-Server, fünf Posteingangsserver und 31 Zahlungsanbieter in der Kopie deaktiviert. Sieben wartende/fehlgeschlagene E-Mails nur in der Kopie abgebrochen. Keine E-Mail versendet, keine Zahlung ausgelöst.
- Installation und Aktualisierung mit dem tatsächlichen Enterprise-/Studio-/Drittanbieter-Bestand: **326 Module geladen**. Abschließender Lauf: **13 Funktionstests, 0 Fehler, 0 Fehlschläge**. Die Teststatistik zählt zusätzlich Setup/Teardown; maßgeblich ist die Abschlussmeldung „0 failed, 0 error(s) of 13 tests“.
- Alle sieben bestehenden Angebotsvorlagen mit temporären, anschließend zurückgerollten Testangeboten als HTML gerendert: M.C.M, Delta Rotax, Comev (leere Vorlage), Abene konventionell, Abene CNC, Intel Nuc und Serviceeinsatz.
- Vorhandene Belege **S00179, S00178, S00165, S00156 und S00177** als echte PDFs erzeugt. Damit geprüft: lange Maschinenbeschreibung, Vertragsnotizen, Abschnitte, kurze Auftragsbestätigung, Servicepositionen, abweichende Rechnungsadresse, steuerfreie Ausgabe, Referenz/Incoterm sowie Prospektanhang. Die eigentlichen Berichtsseiten dieser fünf Belege visuell geprüft.
- Kein vorhandener rabattierter Auftrag gefunden. Rabatt und mehrere Steuergruppen deshalb mit synthetischen Modultests geprüft, nicht durch Änderung realer Belege.
- **S00179:** drei neue Inhaltsseiten statt vier bisheriger Inhaltsseiten. Zusammen mit bestehendem Deckblatt und fünf AGB-Seiten insgesamt **neun statt zehn Seiten**. Alle neun Seiten der vollständigen Prüf-PDF visuell geprüft.
- Standarddruck, automatisch generierter E-Mail-Anhang und authentifizierter Portal-Download ergeben **dieselbe PDF-Datei**. SHA-256: `0ce183f06c38d09ac644934c9f2a405808112969b3924f65ed93f50864df077c`.
- Abschalten des Firmen-Schalters erzeugt wieder die dateiidentische bisherige PDF. SHA-256: `ef1ac019f5da521824261e53cd6571dee2c65cf4bd3173105e9e364dbc3e4b0a`.
- Positionen, Mengen, Preise, Steuern, Texte, Zahlungsbedingung, Kunden, Dokumentauswahl und Angebotsstatus von S00179 vor/nach dem Lauf per Daten-Hash abgeglichen: **unverändert**. Gesamtbetrag bleibt **174.577,77 EUR**. Der Beleg war bereits im Status „Gesendet“; durch die Prüfung wurde er nicht erneut versendet.
- Kundenreferenz bei QSZ und zugehöriger Firma leer. Kein eindeutiges zusätzliches Kundennummernfeld gefunden. Deshalb keine erfundene Nummer und kein Platzhalter im Datenblock.
- Inhaltsstreams des Deckblatts und aller fünf AGB-Seiten gegenüber der bisherigen Gesamtausgabe identisch. Die beiden dynamischen Deckblatt-Widgets enthalten S00179 und den richtigen Kundennamen; beide haben nichtleere Erscheinungsbilder. **Vorhandene Odoo-Einschränkung:** Die zusammengesetzte Ausgabe hat keinen kanonischen AcroForm-Feldbaum. Sie ist eine Berichts-Prüfausgabe, keine neu erstellte ausfüllbare PDF-Vorlage. Keine Reparatur oder Abflachung der bestehenden Builder-Dokumente vorgenommen.
- Abschluss: temporäre Datenbank, Filestore-/Paketkopie, drei Testcontainer und internes Testnetzwerk entfernt. Originaldaten bleiben vorhanden; eine Testkopie kann daraus neu erstellt werden. Modul, Prüfprotokoll und lokale Prüf-PDF bleiben erhalten.
- Produktion abschließend lesend kontrolliert: `nolte_reports_next` nicht installiert/gelistet; Altmodul weiterhin installiert. Manifest, Berichts-XML und SCSS des Altmoduls stimmen mit der anfänglichen Sicherung überein. Produktionscontainer lief durchgehend mit unverändertem Startzeitpunkt vom 04.09.2026; kein Neustart durch diese Arbeiten.

### Zusätzliche Korrekturen aus der Produktionskopie

- Abschnittsüberschrift mit erster Position in einer kleinen, zusammengehaltenen Tabellengruppe; der restliche Beschreibungstext bleibt umbruchfähig. „Maschinenaufbau nach Aufwand“ steht nicht mehr allein am Ende der ersten Inhaltsseite.
- Einheitliche Spaltenbreiten auch in diesen Gruppen; Rabatt-/Steuerspalten dynamisch berücksichtigt.
- E-Mail-Aufrufe über einen Report-Datensatz erhalten den Papierformat-Kontext ebenfalls. Ohne diese Ergänzung griff dort trotz neuem Layout noch das alte Papierformat.
- Fehlende Styles zu Beginn der Testkopie lagen an kopierten Filestore-Berechtigungen. Ausschließlich die Rechte der isolierten Kopie korrigiert; keine Produktionsrechte verändert.

## Vor Produktivfreigabe noch erforderlich

- Fachliche Sichtfreigabe des neuen Layouts durch Lars; das verwendete Kundennummernfeld bestätigen, bevor Nummern gepflegt/zugeordnet werden.
- Firmenstammdaten, Bankdaten und Geschäftsführung fachlich bestätigen. Sonderfälle anderer Firmen, sehr langer Fußtexte oder zweier Bankkonten zusätzlich prüfen, falls eingesetzt.
- Frische Sicherung und abgestimmtes Zeitfenster für die parallele Installation im Produktivsystem. Globale Aktivierung erst nach ausdrücklicher Freigabe.
- Keine vollständige Rechnungs-/Einkaufs-/Lagerberichtsmigration erfolgt. Altmodul deshalb nicht deinstallieren.

Das Ergebnis ist ein installierbarer, auch mit der tatsächlichen Produktionskopie geprüfter **Pilotstand**, keine bereits erfolgte Produktivinstallation oder rechtliche Prüfung der bestehenden Vertragstexte.
