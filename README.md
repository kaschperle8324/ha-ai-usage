# AI Usage für Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)
![Version](https://img.shields.io/badge/version-1.0.0-blue)

Zeigt den Verbrauch deiner KI-Dienste als Sensoren in Home Assistant an:

| Anbieter | Daten | Schnittstelle |
|---|---|---|
| **Claude Abo** (Pro/Max) | 5-Stunden- und Wochenauslastung in %, Rest, Reset-Zeitpunkte, Limit erreicht | inoffiziell (wie die Anzeige in Claude Code) |
| **Anthropic API** | Kosten Monat/heute, Eingabe-/Ausgabe-Tokens | offizielle Admin API |
| **OpenAI API** | Kosten Monat/heute, Tokens, Anfragen | offizielle Admin API |
| **Mistral API** | Monatskosten nach Kategorie, Ausgabenlimit erreicht | offizielle Admin API, *experimentell* |

Jeder Anbieter wird als eigener Eintrag eingerichtet – du kannst also z. B. nur das Claude Abo und OpenAI einbinden.

## Was nicht geht

- **ChatGPT Plus/Pro**: OpenAI stellt für Abo-Kontingente keine Schnittstelle bereit. Die OpenAI-Einbindung zeigt nur den Verbrauch der **API** (platform.openai.com).
- **Le Chat (Mistral)**: kein Abo-Verbrauch abrufbar. Die Mistral-Admin-API gibt es nur im **Enterprise**-Tarif.
- **Anthropic API**: Admin-Schlüssel gibt es nur für Organisationen, nicht für Einzelkonten.

## Installation

### Über HACS
1. HACS → ⋮ → **Benutzerdefinierte Repositories**
2. URL `https://github.com/kaschperle8324/ha-ai-usage`, Typ **Integration**
3. **AI Usage** installieren und Home Assistant neu starten

### Manuell
Den Ordner `custom_components/ai_usage` nach `/config/custom_components/` kopieren und Home Assistant neu starten.

## Einrichtung

**Einstellungen → Geräte & Dienste → Integration hinzufügen → AI Usage**, dann den Anbieter wählen.

### Claude Abo
1. Der Dialog zeigt einen Anmelde-Link. Öffnen, mit dem Claude-Konto anmelden und bestätigen.
2. Die Seite zeigt danach einen Code (Form `abc…#xyz…`). Komplett kopieren und im Dialog einfügen.

Die Integration hat damit eine **eigene** Anmeldung. Claude Code auf deinem Rechner wird nicht abgemeldet. Die Tokens werden automatisch erneuert; läuft die Anmeldung doch einmal ab, meldet Home Assistant „Erneute Anmeldung erforderlich“.

> Anthropic dokumentiert den Abo-Endpunkt nicht offiziell. Ändert sich die Schnittstelle, kann dieser Teil ausfallen, bis die Integration angepasst ist. Der Endpunkt ist stark rate-limitiert – Abfrageintervall nicht unter 5 Minuten stellen (Standard: 10 Minuten).

### Anthropic / OpenAI / Mistral API
Einen **Admin-Schlüssel** anlegen und einfügen:
- Anthropic: Console → Settings → Admin Keys (`sk-ant-admin…`)
- OpenAI: Settings → Organization → Admin Keys (`sk-admin-…`), nur als Organisationsinhaber
- Mistral: Admin Panel (nur Enterprise)

Ein normaler API-Schlüssel funktioniert nicht.

## Optionen

Über **Konfigurieren** am Eintrag lässt sich das Abfrageintervall (5–240 min) ändern.

| Anbieter | Standard |
|---|---|
| Claude Abo | 10 min |
| Anthropic / OpenAI API | 30 min |
| Mistral API | 60 min |

## Entitäten

### Claude Abo
| Entität | Bedeutung |
|---|---|
| `sensor.<name>_5_stunden_auslastung` | Verbrauch im rollierenden 5-Stunden-Fenster in % |
| `sensor.<name>_5_stunden_rest` | verbleibend in % |
| `sensor.<name>_5_stunden_reset` | Zeitpunkt des nächsten Resets |
| `sensor.<name>_wochenauslastung` / `_wochenrest` / `_wochen_reset` | dasselbe für das Wochenlimit |
| `sensor.<name>_wochenauslastung_opus` / `_sonnet` | modellbezogene Wochenwerte, falls vom Konto geliefert |
| `sensor.<name>_zusatznutzung` | Auslastung bezahlter Zusatznutzung, falls aktiviert |
| `binary_sensor.<name>_5_stunden_limit_erreicht` / `_wochenlimit_erreicht` | an bei 100 % |

### API-Konten
| Entität | Bedeutung |
|---|---|
| `sensor.<name>_kosten_monat` / `_kosten_heute` | Kosten in der Abrechnungswährung (meist USD) |
| `sensor.<name>_eingabe_tokens_monat` / `_ausgabe_tokens_monat` / `_tokens_heute` | Token-Summen |
| `sensor.<name>_anfragen_monat` | Anzahl Anfragen (nur OpenAI) |

Die genauen Entitäts-IDs hängen vom Namen ab, den du beim Einrichten vergibst. Die Anbieter liefern Kosten mit einigen Minuten bis Stunden Verzögerung.

## Dashboard-Beispiel

```yaml
type: vertical-stack
cards:
  - type: gauge
    name: Claude 5 Stunden
    entity: sensor.claude_abo_5_stunden_auslastung
    severity: {green: 0, yellow: 70, red: 90}
  - type: gauge
    name: Claude Woche
    entity: sensor.claude_abo_wochenauslastung
    severity: {green: 0, yellow: 70, red: 90}
  - type: entities
    entities:
      - entity: sensor.claude_abo_5_stunden_reset
        format: relative
      - entity: sensor.claude_abo_wochen_reset
        format: datetime
      - sensor.openai_api_kosten_monat
      - sensor.anthropic_api_kosten_monat
```

## Fehlersuche

```yaml
logger:
  logs:
    custom_components.ai_usage: debug
```

Bei Mistral wird die Rohantwort im Debug-Log ausgegeben – hilfreich, falls die Monatskosten nicht stimmen.

## Änderungen

### 1.0.0
- Erste Version: Claude Abo, Anthropic API, OpenAI API, Mistral API (experimentell)

## Lizenz

GPL-3.0 – Copyright © 2026 Markus Kaspar-Otto
