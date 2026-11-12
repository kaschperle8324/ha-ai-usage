# AI Usage für Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)
![Version](https://img.shields.io/badge/version-1.1.0-blue)

Zeigt die Auslastung deines **Claude-Abos** (Pro/Max) als Sensoren in Home Assistant an – dieselben Werte wie unter *Einstellungen → Nutzung* auf claude.ai:

- Auslastung im rollierenden **5-Stunden-Fenster** in %
- **Wochenauslastung** in %
- jeweils der **Rest** in % und der **Reset-Zeitpunkt**
- modellbezogene Wochenwerte (Opus/Sonnet) und Zusatznutzung, falls das Konto sie liefert
- Binärsensoren **Limit erreicht**

## Installation

### Über HACS
1. HACS → ⋮ → **Benutzerdefinierte Repositories**
2. URL `https://github.com/kaschperle8324/ha-ai-usage`, Typ **Integration**
3. **AI Usage** installieren und Home Assistant neu starten

### Manuell
Den Ordner `custom_components/ai_usage` nach `/config/custom_components/` kopieren und Home Assistant neu starten.

## Einrichtung

**Einstellungen → Geräte & Dienste → Integration hinzufügen → AI Usage**

1. Der Dialog zeigt einen Anmelde-Link. Öffnen, mit dem Claude-Konto anmelden und bestätigen.
2. Die Seite zeigt danach einen Code (Form `abc…#xyz…`). Komplett kopieren und im Dialog einfügen.

Die Integration hat damit eine **eigene** Anmeldung. Claude Code auf deinem Rechner wird nicht abgemeldet. Die Tokens werden automatisch erneuert; läuft die Anmeldung doch einmal ab, meldet Home Assistant „Erneute Anmeldung erforderlich“.

> Anthropic dokumentiert den Abo-Endpunkt nicht offiziell. Ändert sich die Schnittstelle, kann die Integration ausfallen, bis sie angepasst ist. Der Endpunkt ist stark rate-limitiert – Abfrageintervall nicht unter 5 Minuten stellen.

## Optionen

Über **Konfigurieren** am Eintrag lässt sich das Abfrageintervall ändern (5–240 min, Standard 10 min).

## Entitäten

Die Entitäts-IDs richten sich nach dem Namen, den du beim Einrichten vergibst (Standard „Claude Abo“).

| Entität | Bedeutung |
|---|---|
| `sensor.claude_abo_5_stunden_auslastung` | Verbrauch im rollierenden 5-Stunden-Fenster in % |
| `sensor.claude_abo_5_stunden_rest` | verbleibend in % |
| `sensor.claude_abo_5_stunden_reset` | Zeitpunkt des nächsten Resets |
| `sensor.claude_abo_wochenauslastung` | Verbrauch im Wochenlimit in % |
| `sensor.claude_abo_wochenrest` | verbleibend in % |
| `sensor.claude_abo_wochen_reset` | Zeitpunkt des Wochen-Resets |
| `sensor.claude_abo_wochenauslastung_opus` / `_sonnet` | modellbezogene Wochenwerte, falls geliefert |
| `sensor.claude_abo_zusatznutzung` | Auslastung bezahlter Zusatznutzung, falls aktiviert |
| `binary_sensor.claude_abo_5_stunden_limit_erreicht` | an bei 100 % |
| `binary_sensor.claude_abo_wochenlimit_erreicht` | an bei 100 % |

## Dashboard-Beispiel

```yaml
type: grid
columns: 2
square: false
cards:
  - type: gauge
    name: 5 Stunden
    entity: sensor.claude_abo_5_stunden_auslastung
    needle: true
    severity: {green: 0, yellow: 70, red: 90}
  - type: gauge
    name: Woche
    entity: sensor.claude_abo_wochenauslastung
    needle: true
    severity: {green: 0, yellow: 70, red: 90}
  - type: tile
    entity: sensor.claude_abo_5_stunden_reset
    name: Reset 5 Stunden
  - type: tile
    entity: sensor.claude_abo_wochen_reset
    name: Reset Woche
```

## Fehlersuche

```yaml
logger:
  logs:
    custom_components.ai_usage: debug
```

## Änderungen

### 1.1.0
- Nur noch Claude-Abo: Anthropic-, OpenAI- und Mistral-API entfernt
- Einrichtung startet direkt mit der Claude-Anmeldung
- Vorhandene Einträge für die entfernten Anbieter starten nicht mehr und können gelöscht werden

### 1.0.0
- Erste Version: Claude Abo, Anthropic API, OpenAI API, Mistral API (experimentell)

## Lizenz

GPL-3.0 – Copyright © 2026 Markus Kaspar-Otto
