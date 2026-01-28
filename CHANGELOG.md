# Changelog

---

## [1.2.0] - 2026-01-28

- ✅ Config Backup/Restore feature (download/upload JSON)
- ✅ Container/hostname renamed to `freeair2lox`
- ✅ Config filename standardized to `FreeAir2Lox_config.json`
- ✅ Reduced Docker config file comments
- ✅ Code cleanup: removed unused variables and imports

---

## [1.1.0] - 2026-01-28

- ✅ Update status indicator (last data refresh time)
- ✅ Environment variables: PUID, PGID, UMASK, TZ, LOG_LEVEL
- ✅ Unraid-optimized Dockerfile with permission handling
- ✅ Auto-discovery for unknown FreeAir devices
- ✅ Dashboard redesign with device status cards

---

## [1.0.0] - 2026-01-20

**Initial Release** - Core features implemented:
- Multi-device FreeAir 100 support with AES-CBC decryption
- Loxone VirtualIn/VirtualOut integration (UDP JSON)
- Web admin UI with login/authentication
- Device management and XML generation
- Docker deployment (Unraid-optimized)
- Dark theme with responsive design

---

See [ROADMAP.md](docs/ROADMAP.md) for upcoming features.
