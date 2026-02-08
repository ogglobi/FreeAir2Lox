# FreeAir2Lox-Bridge v1.4.0

**Eine Bridge zum Verbinden von FreeAir 100 Ventilationssystemen mit Loxone Smart Home Automation. Mit Multi-Miniserver-Unterstützung.**

https://cdn.githubraw.com/ogglobi/FreeAir2Lox/main/Screenshots/Freeair2Lox%20WebUI.png

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Docker Ready](https://img.shields.io/badge/docker-ready-brightgreen.svg)]()
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)]()
[![Multi-Server](https://img.shields.io/badge/v1.4.0-multi%20miniserver-green.svg)]()

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/ogglobi)

## 🚀 Quick Start (3 Minuten)

### Anforderungen
- **Docker + Docker Compose** (oder Python 3.11+)
- **Loxone Miniserver**

### 1️⃣ Starten
```bash
# Repository klonen
git clone https://github.com/ogglobi/FreeAir2Lox-Bridge.git
cd FreeAir2Lox-Bridge

# Web-Interface starten
docker-compose up -d

# Web-Interface öffnen
# http://localhost:8080 → First-Start Wizard
```

## ✨ Features

| Feature | Status | Details |
|---------|--------|---------|
| **AES-CBC Decryption** | ✅ | Sichere FreeAir Payload Entschlüsselung |
| **45+ Sensoren** | ✅ | Vollständige Datenerfassung von FreeAir 100 |
| **RSSI Monitoring** | ✅ | Signalstärke-Tracking (dBm) |
| **Web Admin UI** | ✅ | Modernes Device-Management Interface |
| **Multi-Miniserver** | ✅ | Daten an multiple Miniserver senden per UDP |
| **Per-Server XML** | ✅ | Automatische Virtual In-/ Outputs |
| **Docker Ready** | ✅ | Single-Command Deployment |
| **Multi-Device** | ✅ | Support für mehrere FreeAir Units |
| **Command Lock System** | ✅ | Race-Condition Prevention |
| **Update Indicator** | ✅ | Echtzeit Polling Status Anzeige |
| **Umgebungsvariablen** | ✅ | Unraid/Docker Support (PUID/PGID/TZ) |

---

## 🌐 Multi-Miniserver Unterstützung (v1.4.0)

Mit v1.4.0 können Sie ein **FreeAir-Gerät mehreren Loxone Miniservers zuweisen**:

```
FreeAir 100 → Bridge
                ├─→ Miniserver 1 (192.168.1.50) - Wohnzimmer
                ├─→ Miniserver 2 (192.168.1.51) - Büro
                └─→ Miniserver 3 (192.168.1.52) - Küche
```

### Features:
- **Per-Device Routing**: Jedes FreeAir-Gerät kann zu 1 oder mehreren Servern senden
- **Per-Server API-Keys**: Jeder Miniserver hat eigene UUID für sichere Authentifizierung
- **Per-Server XML-Generierung**: Download VirtualIn/Out XML für jeden Miniserver mit korrekten Einstellungen

### Web-UI Server-Verwaltung:

1. **Server-Liste ansehen**: "Loxone" Tab → "Server verwalten" Button
2. **Neuen Server hinzufügen**: Button "Neuer Server" → IP/Port eintragen → Auto-Generated API-Key
3. **Device zuweisen**: Device bearbeiten → Checkboxes für "Zugewiesene Loxone Server"
4. **XML per-Server Download**: Device bearbeiten → "Sensoren"/"Befehle" → Dropdown für Server-Auswahl

---

## 📋 Erfasste Daten

- **Temperaturen:** Außen, Zuluft, Fortluft, Abluft
- **Feuchte:** Außen, Fortluft, Absolute Feuchte
- **Luftqualität:** CO₂ Level, Luftdruck, Luftdichte
- **Betrieb:** Modus, Komfort-Level, Lüfter-RPM
- **Filter:** Status & Betriebsstunden
- **Netzwerk:** RSSI Signalstärke (dBm)
- **Status:** Verbindungsstatus, Fehler-Flag
- **Weitere:** Luftflow, Betriebsstunden, Systemzustände

## 🐳 Docker Installation

### Quick Start (Empfohlen)
```bash
git clone https://github.com/ogglobi/FreeAir2Lox-Bridge.git
cd FreeAir2Lox-Bridge

# Starten (Konfiguration über Web-UI)
docker-compose up -d

# Logs überprüfen
docker-compose logs -f freeair2lox

# Web-Interface öffnen: http://localhost:8080
```

### Erweiterte Konfiguration (docker-compose.yml)
```yaml
services:
  freeair2lox:
    environment:
      # === UNRAID SYSTEM VARIABLES ===
      PUID: 99              # User ID für Datei-Ownership
      PGID: 100             # Group ID für Datei-Ownership
      UMASK: "000"          # Datei-Erstellungs-Maske
      TZ: UTC               # Timezone (z.B. Europe/Berlin)
      LOG_LEVEL: INFO       # DEBUG, INFO, WARNING, ERROR
      # === INTERNAL CONFIGURATION ===
      CONFIG_FILE: /app/config/FreeAir2Lox_config.json
    ports:
      - "8080:80"           # Web-Interface
      - "80:80"             # FreeAir HTTP API
      - "5555:5555/udp"     # Loxone UDP JSON
```

### 🐍 Manuelle Installation (Python)
```bash
pip install -r requirements.txt
cp config/FreeAir2Lox_config.example.json config/FreeAir2Lox_config.json
python web_admin.py
# Web-Interface: http://localhost:80
```

---

## � Persistent Storage (Unraid/Docker)

### APPDATA Path Configuration
Die Konfiguration wird persistent in einem Docker Volume gespeichert:

```yaml
# docker-compose.yml
volumes:
  # Unraid: /mnt/user/appdata/freeair2lox
  # Lokal: ./config
  - /mnt/user/appdata/freeair2lox:/app/config
```

**Unraid Template Auto-Setup:**
- Template enthält automatisch: `APPDATA: /mnt/user/appdata/freeair2lox`
- Config wird in `/appdata/freeair2lox/` gespeichert
- Backups können über Admin → 💾 Backup Tab heruntergeladen werden

**Wichtig:**
- Stelle sicher, dass das APPDATA-Verzeichnis im Unraid existiert
- PUID/PGID müssen für Dateizugriff korrekt gesetzt sein
- **NEUF v1.2.0+:** Beim ersten Start wird `FreeAir2Lox_config.example.json` automatisch → `FreeAir2Lox_config.json` kopiert (Unraid Bind-Mount Workaround, siehe [Unraid Forum](https://forums.unraid.net/topic/108147-solved-dockerfile-volume-unraid-appdata/))
- Folgende Starts verwenden die bestehende Config (keine Überschreibung)

---

## 🔧 Umgebungsvariablen - COMMUNITY APPS WICHTIG

### APPDATA Path (Hart Codiert in docker-compose.yml)
```yaml
volumes:
  # Unraid Community Apps APPDATA - HART CODIERT
  # Der Pfad muss mit /mnt/user/appdata/freeair2lox/ beginnen!
  - /mnt/user/appdata/freeair2lox:/app/config
```

### System-Variablen
| Variable | Standard | Beschreibung |
|----------|----------|-------------|
| `PUID` | `99` | Benutzer-ID für Datei-Ownership (Unraid) |
| `PGID` | `100` | Gruppen-ID für Datei-Ownership (Unraid) |
| `UMASK` | `000` | Datei-Erstellungs-Maske (rw-rw-rw-) |
| `TZ` | `UTC` | Timezone für Logs (z.B. `Europe/Berlin`) |
| `LOG_LEVEL` | `INFO` | Log-Level: DEBUG, INFO, WARNING, ERROR |

### Anwendungs-Variablen
**WICHTIG:** FreeAir Serial, Loxone IP, Passwörter werden über die **Web-UI First-Start Wizard** konfiguriert.


## 🌐 Web-Interface

Zugriff: `http://localhost:8080`

### Features
- ✅ First-Start Wizard für initiales Setup
- ✅ Device Management (Hinzufügen/Bearbeiten/Löschen)
- ✅ Echtzeit Sensorwerte & RSSI Signal-Stärke
- ✅ Loxone Integration Preview (XML generieren)
- ✅ Live-Log Viewer
- ✅ Update Status Indicator (🟢 aktuell / 🟡 alt / 🔴 offline)

## 🔗 Loxone Integration

Die Bridge sendet alle Sensorwerte als **UDP JSON** Pakete an Loxone.

### Beispiel Payload
```json
{
  "device": "Wohnzimmer",
  "timestamp": "2026-01-28T12:35:21.478747",
  "is_online": true,
  "air_flow": 85,
  "rssi": -42,
  "co2": 928,
  "temperature": 21.4,
  "error_state": 0,
  "has_errors": false,
  "filter_hours": 2185,
  "operating_hours": 14417
}
```

### Loxone Konfiguration
1. **Geräte in FreeAir2Lox konfigurieren** (Web-UI → First-Start Wizard)
2. **XML Vorlagen generieren** (Web-UI → Settings → Loxone XML exportieren)
3. **In Loxone importieren** (Loxone Config → Virtual Inputs/Outputs)
4. **Bausteinvorlage von Github für einfache Config-Konfiguration**

## 🔐 Sicherheit

- ✅ AES-CBC Verschlüsselung (FreeAir Payload)
- ✅ Session-basierte Web-UI Authentifizierung
- ✅ Passwörter nur lokal gespeichert
- ✅ UDP nur im lokalen Netzwerk (kein Internet nötig)
- ✅ HTTPS-ready (über Reverse Proxy)

## 📝 Version History

Siehe **[CHANGELOG.md](CHANGELOG.md)** für vollständige Version History


## 🙏 Credits

Spezielle Danksagungen an:
- **Scrounger** für die [ioBroker.freeair](https://github.com/ioBrokerModul/ioBroker.freeair) Adapter (AES-CBC Decryption)


## 👨‍💻 Autor

**Development:** 2026
**Status:** Production Ready ✅

<p align="center">Made with ❤️ by <a href="https://github.com/ogglobi">ogglobi</a></p>

<p align="center">
  <a href="https://ko-fi.com/ogglobi">
    <img src="https://img.shields.io/badge/Buy%20Me%20a%20Coffee-☕-orange?style=flat-square" alt="Ko-fi">
  </a>
</p>

---

## 📄 Lizenz

MIT License - Siehe [LICENSE](LICENSE) Datei für Details

## 🆘 Support

Probleme oder Fragen?

1. **Konfiguration**: Siehe [CONFIGURATION.md](CONFIGURATION.md)
2. **Deployment**: Siehe [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)
3. **GitHub Issues**: Repository Issues öffnen
4. **Logs**: `docker-compose logs freeair2lox`
