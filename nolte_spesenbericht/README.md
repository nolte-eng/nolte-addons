# Nolte Spesenbericht für Odoo 19

Dieses Modul integriert den Spesenbericht direkt als geschützte Odoo-Webseite.

## Aufruf

Nach der Installation und Rechtevergabe:

`https://ihre-odoo-domain/my/spesenbericht`

## Voraussetzungen

- Odoo 19 Enterprise auf Odoo.sh oder einem eigenen Server
- Apps: Website, Mitarbeiter, Abwesenheiten und Spesen
- Beim Odoo-Benutzer muss ein Mitarbeiter im Feld **Zugehöriger Benutzer** verknüpft sein

Odoo Online unterstützt keine eigenen Python-Module. In diesem Fall ist ein Wechsel zu Odoo.sh oder eine reine Studio-/Standardlösung erforderlich.

## Installation auf Odoo.sh

1. Den Ordner `nolte_spesenbericht` in das GitHub-Repository des Odoo.sh-Projekts kopieren.
2. Zunächst in eine Entwicklungs- oder Staging-Branch übertragen.
3. Nach erfolgreichem Build in Odoo den Entwicklermodus aktivieren.
4. **Apps → App-Liste aktualisieren** öffnen.
5. Nach **Nolte Spesenbericht** suchen und das Modul installieren.
6. Unter **Einstellungen → Benutzer** die passende Rolle vergeben.

## Rollen

- **Spesenbericht Mitarbeiter**: eigene Monatsberichte erfassen und einreichen
- **Spesenbericht Prüfer**: Unternehmensberichte prüfen, freigeben oder zurückgeben
- **Spesenbericht Administrator**: Spesenprodukte konfigurieren und freigegebene Berichte an Odoo Spesen übergeben

## Ersteinrichtung

Im Odoo-Hauptmenü **Spesenbericht → Konfiguration** öffnen und pro Unternehmen drei vorhandene Odoo-Spesenprodukte auswählen:

- Verpflegung / Reisepauschalen
- Hotel
- Sonstige Auslagen

## Enthaltene Funktionen

- Monatsraster mit 15-Minuten-Zeitschritten
- automatische Arbeitszeit und Überstunden
- BMF-Pauschalen und Mahlzeitenabzüge
- Hotelpauschale oder Hotelbeleg
- Upload von Belegen in die Odoo-Dokumentablage
- Übernahme genehmigter Odoo-Abwesenheiten mit 8 bzw. 4 Stunden
- Einreichung und Freigabe mit Odoo-Protokoll
- Erzeugung einzelner, direkt mit dem Monatsbericht verknüpfter `hr.expense`-Datensätze nach dem vereinfachten Odoo-19-Ablauf
- CSV-Download sowie Drucken/PDF

## Vor Produktivbetrieb prüfen

- BMF-Sätze und Buchungskonten
- passende Spesenprodukte und Steuern
- Benutzer- und Unternehmensrechte
- Test mit Volltag, halbem Urlaubstag, Hotelbeleg und Auslagenbeleg
- Freigabe und Buchung in einer Odoo-Staging-Datenbank
