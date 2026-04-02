# ☀️ PV-Analyse mit Speichervergleich

https://pv-analysis.streamlit.app/

Eine interaktive Streamlit-App zur Simulation und Wirtschaftlichkeitsanalyse von Photovoltaik-Anlagen mit Batteriespeicher – optimiert für **Balkonkraftwerke** und kleine Aufdachanlagen.

## Features

- **PVGIS-Integration** – Stündliche PV-Ertragsdaten direkt von der EU-Datenbank (2005–2023)
- **Standortsuche** – Koordinaten per Ortsname via OpenStreetMap Nominatim
- **Flexible PV-Konfiguration** – Beliebig viele Module mit individueller Leistung, Ausrichtung und Neigung
- **Wechselrichter-Limit** – 800 W Standard (Balkonkraftwerk), deaktivierbar für größere Anlagen
- **Lastabhängiger Wechselrichter-Wirkungsgrad** – Realistische Effizienz basierend auf CEC-Daten von 3.000+ Wechselrichtern:
  - Drei Voreinstellungen: Pessimistisch (P10), Median (P50), Optimistisch (P90)
  - Optional: Eigene Wirkungsgradkurve für Experten
- **DC- und AC-gekoppelte Speicher** – Korrekte Simulation beider Anbindungsarten:
  - **DC-gekoppelt**: Batterie lädt direkt vom DC-Bus, Wechselrichter-Limit gilt nur für die AC-Seite
  - **AC-gekoppelt**: Wechselrichter begrenzt den gesamten PV-Ertrag
- **BDEW H0-Standardlastprofil** – Realistisches Lastprofil mit Unterscheidung nach:
  - Werktagen, Samstagen und Sonn-/Feiertagen
  - Jahreszeiten (Winter, Frühling, Sommer, Herbst)
  - Deutsche Feiertage werden automatisch berücksichtigt
- **Erweiterter Verbrauchsmodus** – Eigene stündliche Lastprofile mit optionaler Tagtyp-Differenzierung
- **Lastverschiebung** – Optionale Zusatzlast an ertragreichen Sonnentagen (z. B. Waschmaschine)
- **Periodische Zusatzlast** – Regelmäßiger Verbrauch unabhängig vom Wetter (z. B. Warmwasser)
- **Einspeisevergütung** – Berücksichtigung der Vergütung in allen Wirtschaftlichkeitsberechnungen
- **Mehrere Speicher-Szenarien** – Vergleich von „Ohne Speicher" bis zu beliebig vielen Batterie-Optionen
- **Langzeitvergleich PV vs. ETF** – Kumulierte Rendite über konfigurierbare Laufzeit
- **Konfiguration teilen** – Alle Parameter als komprimierter URL-Parameter

## Schnellstart

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

### Voraussetzungen

- Python ≥ 3.10
- Internetverbindung (für PVGIS- und Geocoding-Abfragen)

## Bedienung

Die Konfiguration erfolgt über die **Seitenleiste** in fünf aufklappbaren Abschnitten:

| Abschnitt | Inhalt |
|---|---|
| 📍 **Standort** | Ort suchen oder Koordinaten manuell eingeben |
| 💡 **Verbrauch** | Jahresverbrauch, Lastprofil, Lastverschiebung, periodische Zusatzlast |
| ⚡ **PV-System** | PVGIS-Datenjahr, Systemverluste, Wechselrichter-Limit, Einspeisevergütung, Module |
| 🔋 **Speicher** | DC/AC-Kopplung, Lade-/Entladeverluste, SoC-Grenzen, Speicher-Optionen |
| 💰 **Preise & Vergleich** | Strompreis, Preissteigerung, ETF-Rendite, Analyse-Horizont |

Nach Eingabe von **Standort** und **Jahresverbrauch** startet die Analyse automatisch.

## Analyse-Ergebnisse

- **Szenario-Übersicht** – Autarkie, Eigenverbrauch, Netzbezug, Einspeisung und Ersparnis pro Szenario
- **Monatliche Energiebilanz** – Gestapeltes Balkendiagramm (Direkt-PV, Batterie, Netzbezug, Einspeisung)
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
   4. Deficit aus Batterie (durch WR) oder Netz

   **AC-gekoppelt**:
   1. Wechselrichter begrenzt gesamte PV-Leistung
   2. Haushaltslast decken, Überschuss in Batterie oder Netz

4. **SoC-Management** – Saisonale Min-/Max-Ladezustände (Sommer/Winter)

## Wirtschaftlichkeitsrechnung

- **Ersparnis** = eingesparter Netzbezug × Strompreis + Einspeisung × Einspeisevergütung
- **Strompreis** steigt jährlich um den konfigurierten Prozentsatz
- **Einspeisevergütung** bleibt konstant (entspricht deutschem EEG)
- **ETF-Vergleich** – Gleicher Investitionsbetrag mit konfigurierter Jahresrendite

## Konfiguration teilen

Über den Button **🔗 Link mit aktueller Konfiguration erstellen** werden alle Parameter (inkl. Module, Speicher, Profile) als komprimierter Base64-String in die URL kodiert. Der Link kann geteilt werden – beim Öffnen wird die Konfiguration automatisch wiederhergestellt.

## Datenquellen

| Dienst oder Datenquelle                                                                                          | Zweck | Anbieter                                               |
|------------------------------------------------------------------------------------------------------------------|---|--------------------------------------------------------|
| [PVGIS](https://re.jrc.ec.europa.eu/pvg_tools/en/)                                                               | Stündliche PV-Ertragsdaten | European Commission Joint Research Center (JRC)        |
| [Nominatim](https://nominatim.openstreetmap.org/)                                                                | Geocoding (Ortssuche → Koordinaten) | OpenStreetMap                                          |
| [BDEW H0-Profil](https://www.bdew.de/energie/standardlastprofile-strom/)                                         | Standard-Lastprofil für Haushalte | Bundesverband der Energie- und Wasserwirtschaft (BDEW) |
| [CEC Solar Equipment Lists ](https://www.energy.ca.gov/programs-and-topics/programs/solar-equipment-lists) | Lastabhängige Wirkungsgradkurven | California Energy Commission (CEC)                     |

Das BDEW H0-Standardlastprofil stammt aus der offiziellen Veröffentlichung "Repräsentative VDEW-Lastprofile" (1999) des Bundesverbands der Energie- und Wasserwirtschaft. Die 15-Minuten-Werte werden zu stündlichen Mittelwerten aggregiert.
- **Tagtypen**: Werktag (Mo-Fr), Samstag, Sonn-/Feiertag
- **Jahreszeiten**: Winter, Frühling, Sommer, Herbst
- **Feiertage**: Gesetzliche deutsche Feiertage werden automatisch berücksichtigt

Die Wechselrichter-Wirkungsgradkurven basieren auf dem CEC (California Energy Commission) Grid Support Inverter List, der Effizienz­daten von über 3.000 Wechselrichtern enthält. Die App bietet drei Voreinstellungen:
- **Pessimistisch (P10)**: 10. Perzentil – konservative Schätzung
- **Median (P50)**: 50. Perzentil – typischer moderner Wechselrichter
- **Optimistisch (P90)**: 90. Perzentil – Premium-/Hocheffizienz-Geräte

Zusätzlich können Experten eigene Wirkungsgradkurven eingeben.

## Lizenz

Dieses Projekt steht unter der [MIT License](LICENSE).

