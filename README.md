# ☀️ SolarBatterYield - PV-Rechner mit Speichervergleich

https://solarbatteryield.streamlit.app/

Open-Source-Tool zur Simulation von PV-Ertrag und Amortisation. Fokus auf Balkonkraftwerke, Speicher-Nachrüstung und
realistische Lastprofile.

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/app_screenshot_dark.png">
    <source media="(prefers-color-scheme: light)" srcset="assets/app_screenshot_light.png">
    <img src="assets/app_screenshot_light.png" alt="App Screenshot" width="90%">
  </picture>
</p>

## Features

### ☀️ Photovoltaik & Hardware

* 🔌 Flexible PV-Konfiguration – Beliebig viele Module mit individueller Leistung, Ausrichtung und Neigung.
* 📉 Realistische Wirkungsgrade – Simulation basierend auf CEC-Daten von 3.000+ Wechselrichtern
  (P10/P50/P90-Voreinstellungen oder eigene Kurven).
* ⚡ DC- & AC-Kopplung – Korrekte Abbildung beider Systemwelten (z. B. Speicher vor oder nach dem Wechselrichter).
* 🛑 Wechselrichter-Limit – Einstellbare Begrenzung (z. B. 800 W für BKW), für große Anlagen deaktivierbar.

### 🏠 Verbrauch & Lastprofile

* 📊 Dynamische Lastprofile – Unterscheidung nach Wochentagen, Jahreszeiten und Berücksichtigung deutscher Feiertage.
* 🧺 Intelligente Lastverschiebung – Simulation von Zusatzverbrauch an Sonnentagen (z. B. Waschmaschine/Spülmaschine).
* 🚿 Periodische Zusatzlasten – Abbildung von regelmäßigen Verbräuchen wie Warmwasser-Desinfektion
  (Legionellenschaltung).
* 📂 Experten-Modus – CSV-Upload eigener Smart-Meter-Daten für maximale Präzision.

### 💰 Wirtschaftlichkeit & Analyse

* 🔋 Speicher-Vergleichsszenarien – Direkter Vergleich verschiedener Kapazitäten von "Ohne Speicher" bis hin zu mehreren
  Batterie-Optionen.
* ⚡ Entladestrategien – Drei Modi: Nulleinspeisung (Smart Meter), Grundlastdeckung (konstante Abgabe) oder
  Zeitfenster (stundenweise Steuerung).
* 📈 PV vs. ETF-Rendite – Langfristiger Vergleich der kumulierten Rendite inklusive optionaler Reinvestition der
  Ersparnis.
* 🪙 Einspeisevergütung – Optionale Berücksichtigung aktueller Vergütungssätze in der Amortisationsrechnung.
* 🔗 Konfiguration teilen – Alle Parameter können via Deep-Link geteilt werden.

## Bedienung

Die Konfiguration erfolgt über die **Seitenleiste** in sieben aufklappbaren Abschnitten:

| Abschnitt                     | Inhalt                                                                                          |
|-------------------------------|-------------------------------------------------------------------------------------------------|
| 📍 **Standort**               | Ort suchen oder Koordinaten manuell eingeben                                                    |
| 💡 **Verbrauch**              | Jahresverbrauch, Lastprofil, Lastverschiebung, periodische Zusatzlast, Grundlast-Überschreibung |
| ☀️ **PV-Module**              | Module (Leistung, Ausrichtung, Neigung), Systemkosten                                           |
| ⚡ **PV-Konfiguration**        | PVGIS-Datenjahr, Systemverluste, WR-Wirkungsgrad, Wechselrichter-Limit                          |
| 🔋 **Speicher-Optionen**      | Ausbaustufen (Kapazität, Aufpreis)                                                              |
| 🪫 **Speicher-Konfiguration** | DC/AC-Kopplung, Batterie-WR, Lade-/Entladeverluste, SoC-Grenzen, Entladestrategie               |
| 💰 **Preise & Vergleich**     | Strompreis, Preissteigerung, Einspeisevergütung, ETF-Rendite, Analyse-Horizont                  |

Die Abschnitte **PV-Module** und **Speicher-Optionen** enthalten die häufig angepassten Einstellungen,
während **PV-Konfiguration** und **Speicher-Konfiguration** die technischen Details bündeln.

### Entladestrategien

Die Entladestrategie bestimmt, wie die Batterie ihren Strom abgibt:

| Strategie            | Beschreibung                                                                                 | Voraussetzung            |
|----------------------|----------------------------------------------------------------------------------------------|--------------------------|
| **Nulleinspeisung**  | Batterie folgt dem aktuellen Verbrauch in Echtzeit – höchster Eigenverbrauch                 | Smart Meter erforderlich |
| **Grundlastdeckung** | Batterie gibt konstant z.B. 200W ab – einfachste Steuerung                                   | Keine                    |
| **Zeitfenster**      | Batterie gibt je nach Tageszeit unterschiedliche Leistung ab (z.B. 300W abends, 100W nachts) | Keine                    |

**Nulleinspeisung** ist die optimale Strategie bei Smart-Meter-Anbindung. Die Batterie trackt den Verbrauch und
vermeidet Einspeisung. **Grundlastdeckung** und **Zeitfenster** sind für Systeme ohne Smart Meter geeignet – der
konstante Output kann den schwankenden Verbrauch nicht perfekt treffen, was zu etwas mehr Netzbezug und Einspeisung
führt.

Für eine korrekte Simulation wird insbesondere bei **Grundlastdeckung** und **Zeitfenster** ein realistischer
Wert für die Grundlast des Haushalts (Kühlschrank, Router, Standby-Geräte) benötigt. Dieser wird standardmäßig von
der App auf Basis des gewählten Lastprofils geschätzt, kann aber auch im Abschnitt **Verbrauch** manuell überschrieben
werden. Ein höherer Grundlast-Wert erhöht den simulierten Eigenverbrauch, da die konstante Last zuverlässiger von PV
oder Batterie gedeckt werden kann.

Nach Eingabe von **Standort** und **Jahresverbrauch** startet die Analyse automatisch.

## Analyse-Ergebnisse

- **Szenario-Übersicht** – Autarkie, Eigenverbrauch, Netzbezug, Einspeisung und Ersparnis pro Szenario
- **Monatliche Energiebilanz** – Gestapeltes Balkendiagramm (Direkt-PV, Batterie, Netzbezug, Einspeisung)
- **Speicher-Ladezustand pro Jahreszeit** - Verlauf des SoC zu unterschiedlichen Jahreszeiten
- **Inkrementelle Analyse** – Mehrwert jeder Ausbaustufe (Δ kWh, Δ €, Amortisation, Rendite)
- **Langzeit-Chart** – PV-Netto-Gewinn vs. ETF über den Analyse-Horizont
- **Zusammenfassung** – Bestes Szenario nach absolutem PV-Gewinn

## Simulationsmodell

Die Simulation läuft stündlich über ein volles Kalenderjahr (8.760 Stunden):

1. **PV-Erzeugung** – PVGIS liefert stündliche DC-Leistung pro Modul
2. **Haushaltslast** – BDEW H0-Profil mit automatischer Unterscheidung nach:
    - **Tagtyp**: Werktag / Samstag / Sonn- und Feiertag
    - **Jahreszeit**: Winter / Frühling / Sommer / Herbst
    - Optional mit Flex- und Periodiklast
3. **Energiefluss** – Pro Stunde in Abhängigkeit der Speicheranbindung:

   **DC-gekoppelt** (Smart-Inverter-Priorität):
    1. Haushaltslast aus PV decken (durch Wechselrichter, ≤ WR-Limit)
    2. Batterie aus überschüssigem DC laden (kein WR-Limit)
    3. Rest über Wechselrichter ins Netz einspeisen (≤ verbleibende WR-Kapazität)
    4. Defizit aus Batterie (durch WR) oder Netz

   **AC-gekoppelt**:
    1. Wechselrichter begrenzt gesamte PV-Leistung
    2. Haushaltslast decken, Überschuss in Batterie oder Netz

4. **SoC-Management** – Saisonale Min-/Max-Ladezustände (Sommer/Winter)

### Sub-stündliche Lastregressionskorrektur

Ein naiver stündlicher Vergleich von PV-Erzeugung und Haushaltslast überschätzt den Eigenverbrauch: Liegt die mittlere
Stundenlast z. B. bei 300 W und die PV bei 400 W, scheint die Last vollständig gedeckt. In Wirklichkeit schwankt der
Verbrauch innerhalb der Stunde erheblich – zeitweise deutlich unter und zeitweise über der PV-Leistung. Gerade bei
Balkonkraftwerken mit niedrigem Wechselrichter-Limit (z. B. 800 W) führt das zu spürbaren Abweichungen.

Um dies zu korrigieren, wird für jede Simulationsstunde der durchschnittliche Verbrauch in eine
**Wahrscheinlichkeitsdichtefunktion** (PDF) der momentanen Leistungsaufnahme überführt (25-W-Bins). Für jedes
Leistungsintervall wird der Anteil der PV-Erzeugung berechnet, der die momentane Last decken kann. Die gewichtete Summe
über alle Intervalle ergibt den realistischen Direkt-PV-Anteil. Dadurch können innerhalb einer Stunde sowohl
Überschuss (Einspeisung / Batterieladung) als auch Defizit (Netzbezug / Batterieentladung) gleichzeitig auftreten.

#### Zweischicht-Modell mit Grundlast

Die Haushaltslast wird in zwei Schichten zerlegt:

1. **Grundlast** (konstant) – Always-On-Geräte wie Kühlschrank, Router, Standby. Diese Last ist dauerhaft vorhanden
   und wird bei ausreichender PV- oder Batterieleistung vollständig gedeckt.
2. **Variable Last** (schwankend) – Alle übrigen Verbraucher. Auf diesen Anteil wird die statistische Regression
   angewendet.

Die vorberechneten Verteilungen stammen aus gemessenen Minutenlastprofilen von 38 deutschen Einfamilienhäusern
(Schlemminger et al. 2022). Um Verzerrungen durch unterschiedliche Grundlasten zwischen Haushalten zu vermeiden, wurde
pro Haushalt die Grundlast (1%-Perzentil) ermittelt und abgezogen. Die resultierende Verteilung beschreibt nur die
Variabilität oberhalb der Grundlast.

Bei der Anwendung wird die Grundlast des Nutzers (automatisch berechnet oder manuell überschrieben) als Offset addiert.
Dadurch ergibt sich eine präzisere Eigenverbrauchsberechnung – insbesondere bei niedrigen PV-/Batterie-Outputs nahe
der Grundlast. Für Lasten über 3.450 W wird eine synthetische bimodale Gaußverteilung erzeugt.

## Wirtschaftlichkeitsrechnung

- **Ersparnis** = eingesparter Netzbezug × Strompreis + Einspeisung × Einspeisevergütung
- **Strompreis** steigt jährlich um den konfigurierten Prozentsatz
- **Einspeisevergütung** bleibt konstant (entspricht deutschem EEG)
- **ETF-Vergleich** – Gleicher Investitionsbetrag mit konfigurierter Jahresrendite

## Konfiguration teilen

Über den Button **🔗 Link mit aktueller Konfiguration erstellen** werden alle Parameter (inkl. Module, Speicher, Profile)
als komprimierter Base64-String in die URL kodiert. Der Link kann geteilt werden – beim Öffnen wird die Konfiguration
automatisch wiederhergestellt.

## Datenquellen

| Dienst oder Datenquelle                                                                                   | Zweck                                       | Anbieter                                                                                                                    |
|-----------------------------------------------------------------------------------------------------------|---------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------|
| [PVGIS](https://re.jrc.ec.europa.eu/pvg_tools/en/)                                                        | Stündliche PV-Ertragsdaten                  | European Commission Joint Research Center (JRC)                                                                             |
| [Nominatim](https://nominatim.openstreetmap.org/)                                                         | Geocoding (Ortssuche → Koordinaten)         | © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors, [ODbL](https://opendatacommons.org/licenses/odbl/) |
| [BDEW H0-Profil](https://www.bdew.de/energie/standardlastprofile-strom/)                                  | Standard-Lastprofil für Haushalte           | Bundesverband der Energie- und Wasserwirtschaft (BDEW)                                                                      |
| [CEC Solar Equipment Lists](https://www.energy.ca.gov/programs-and-topics/programs/solar-equipment-lists) | Lastabhängige Wirkungsgradkurven            | California Energy Commission (CEC)                                                                                          |
| [Schlemminger et al. 2022](https://doi.org/10.1038/s41597-022-01156-1)                                    | Gemessene Minutenlastprofile (38 Haushalte) | ISFH / *Scientific Data*                                                                                                    |

Das BDEW H0-Standardlastprofil stammt aus der offiziellen Veröffentlichung "Repräsentative VDEW-Lastprofile" (1999) des
Bundesverbands der Energie- und Wasserwirtschaft. Die 15-Minuten-Werte werden zu stündlichen Mittelwerten aggregiert.

- **Tagtypen**: Werktag (Mo-Fr), Samstag, Sonn-/Feiertag
- **Jahreszeiten**: Winter, Frühling, Sommer, Herbst
- **Feiertage**: Gesetzliche deutsche Feiertage werden automatisch berücksichtigt

Die Wechselrichter-Wirkungsgradkurven basieren auf dem CEC (California Energy Commission) Grid Support Inverter List,
der Effizienzdaten von über 3.000 Wechselrichtern enthält. Die App bietet drei Voreinstellungen:

- **Pessimistisch (P10)**: 10. Perzentil – konservative Schätzung
- **Median (P50)**: 50. Perzentil – typischer moderner Wechselrichter
- **Optimistisch (P90)**: 90. Perzentil – Premium-/Hocheffizienz-Geräte

Zusätzlich können Experten eigene Wirkungsgradkurven eingeben.

Die sub-stündlichen Lastregressionsverteilungen basieren auf dem Datensatz von Schlemminger, M., Ohrdes, T., Schneider,
E. et al.: *"Dataset on electrical single-family house and heat pump load profiles in Germany."*, Sci Data 9, 56 (
2022), [DOI: 10.1038/s41597-022-01156-1](https://doi.org/10.1038/s41597-022-01156-1). Die Minutendaten von
38 deutschen Haushalten wurden grundlast-bereinigt aufbereitet: Pro Haushalt wird die Grundlast (1%-Perzentil) ermittelt
und abgezogen. Die resultierende Verteilung beschreibt nur die Variabilität oberhalb der Grundlast. Bei der Anwendung
wird die Grundlast des Nutzers als Offset addiert, was eine präzisere Eigenverbrauchsberechnung ermöglicht.

## Entwicklung

Siehe [CONTRIBUTING.md](CONTRIBUTING.md) für Setup, Tests und Commit-Konventionen.

## Lizenz

Dieses Projekt steht unter der [MIT License](LICENSE).


