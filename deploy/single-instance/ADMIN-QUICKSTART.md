# NBSR Connector — quickstart për adminin

## 1. Parakushtet

Përdor një checkout që përmban `deploy/single-instance/` dhe ekzekuto komandën
nga rrënja e repo-s. Duhet një mjedis i përgatitur Python (`>=3.12,<3.15` sipas
`pyproject.toml`) me varësitë e repo-s, përfshirë Pydantic. Skedari JSON duhet
të jetë lokal, i materializuar dhe pa lidhje simbolike ose reparse points.
Në Windows përdor një disk lokal fiks. Kontrolli nuk kërkon rrjet ose kredenciale.

## 2. Konfigurimi minimal

Fillo me [shembullin e plotë](config.example.json) dhe
[schema-n](config.schema.json). Hollësitë e validatorit janë te [README](README.md). Për një konfigurim tëndin offline, ruaj një
kopje të veçantë të shembullit me këto lidhje:

- Mbaj `mode: offline`, nga një bllok `client` dhe `gateway`, dhe saktësisht
  një shërbim te `origin.services`.
- Përdor të njëjtin `service_id` te klienti dhe te shërbimi, dhe të njëjtin
  `gateway_id` te klienti, gateway dhe shërbimi. Endpoint-i privat vendoset
  vetëm te `origin.services[0].target`.
- Mbaj kufijtë e regjistrimit dhe profilin HTTP `GET /` të shembullit.
  Fushat `*_ref` mbajnë emra logjikë `ref:…`. Identitetet dhe referencat
  e shembullit janë vlera testuese publike.

## 3. Statusi dhe log-et

```powershell
python -B deploy/single-instance/validate_config.py deploy/single-instance/config.example.json
```

Për të kontrolluar kopjen tënde, zëvendëso argumentin e fundit me shtegun e
skedarit. Lexo rezultatin në terminal:

| Ku | Rezultati | Kuptimi |
| --- | --- | --- |
| stdout, dalje `0` | `CONFIG_VALID_OFFLINE`, `service_count: 1`, `ready: false`, `references_verified: false` | Kaloi kontrolli i konfigurimit për një shërbim. |
| stderr, dalje `2` | `CONFIG_INVALID` | Lexo diagnostikën e redaktuar dhe korrigjo hyrjen. |

Validatori nuk shkruan skedar log-u. Kjo paketë offline nuk ofron komandë
statusi ose vendndodhje log-esh për një Connector live.

## 4. Përfundimi dhe ndalja

Komanda punon në plan të parë dhe përfundon vetë. Nuk hap socket, nuk nis
procese fëmijë ose kontejnerë dhe nuk lë shërbim për t'u ndalur. Për këtë
paketë nuk ka komandë për ndalje të pastër të një Connector-i live.

## Çka mbetet e paprovuar

- **Regjistrimi live.** Provat Go/Quinn në loopback përdorin TLS dhe lidhjen
  me exporter-in, me autoritet sintetik. Regjistrimi dhe rinovimi me
  autoritet real, statusi `READY` dhe ndalja e pastër e një instance të
  vendosur mbeten të paprovuara.
  [Vendimi i Stage 3](../../docs/reviews/2026-10-11-stage3-runtime-decision.md)
  · [Provat e zhvillimit](../../interop/nbsr-go-peer/connector/README.md).
- **Rikthimi nga backup-i.** Kodi i provuar për snapshot-in dhe koordinimin
  e ruajtjes mbulon një backend në memorie. Rikthimi nga backup-i i një
  instance Connector të vendosur mbetet i paprovuar. Kjo paketë nuk ka
  komandë rikthimi.
  [Provat e ruajtjes offline](../../docs/reviews/2026-10-11-inclusion-persistence-implementation.md)
  · [Plani i paketës së operatorit](../../docs/superpowers/plans/2026-10-10-single-instance-operator-package.md).
