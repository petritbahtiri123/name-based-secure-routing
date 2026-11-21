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

## Checklistë për pilotin me një shërbim të brendshëm

Kriteret operative më poshtë zbatojnë [Stage 10 të planit ekzistues](../../docs/superpowers/plans/2026-10-10-single-instance-operator-package.md#10-run-and-close-one-bounded-customer-pilot).

Kjo checklistë vlen për një ekip, një shërbim të brendshëm dhe një mjedis të
miratuar. Statusi aktual i pilotit është **MOS E NIS**. Plotëso kriteret para
nisjes përpara se të lejosh trafik pilot. Për çdo provë shëno kohën, operatorin
dhe rezultatin (kaloi, dështoi ose nuk u krye). Ruaj edhe dështimet, me log-e
të redaktuara pa çelësa, kredenciale ose të dhëna të klientëve.

### Provat që ekzistojnë

- Stage 1–2 kanë mbulim për kontratën offline dhe konfigurimin për një
  shërbim. `CONFIG_VALID_OFFLINE` lë `ready: false` dhe
  `references_verified: false`. [Kontrolli offline](#3-statusi-dhe-log-et)
  · [Statusi i implementimit](../../docs/protocol/status.md).
- Loopback-u i zhvillimit provoi TLS dhe lidhjen me exporter-in me autoritet
  sintetik. Provat e veçanta offline mbulojnë nënshkrimet dhe kohëmatësit me
  fixture. Autoriteti real i regjistrimit, dërgimi i revokimit dhe kohëmatësit
  realë mbeten për t'u provuar. [Vendimi i Stage 3](../../docs/reviews/2026-10-11-stage3-runtime-decision.md).
- Provat e snapshot-it dhe prova e izoluar e filesystem-it mbulojnë rrugë
  testimi. Rikthimi nga backup-i i Connector-it të instaluar mbetet i
  paprovuar. [Prova e filesystem-it](../../docs/reviews/2026-10-11-inclusion-filesystem-matching-module.md).

### Para nisjes — ende për t'u verifikuar

| Kriteri | Rezultati i pritshëm | Evidenca për t'u ruajtur |
| --- | --- | --- |
| Miratimi dhe kufijtë | Pronari i shërbimit dhe admini miratojnë hostin, gateway, një shërbim, klientët e lejuar, egress-in, dritaren, kufijtë e kërkesave dhe burimeve, pragjet e ndaljes dhe personin që vendos për ndaljen. | Miratimi, topologjia, kufijtë numerikë dhe emrat e përgjegjësve. |
| Auditimi i sigurisë | Përfundon auditimi i kërkuar në plan, me rishikim të pavarur dhe riprovim të gjetjeve të korrigjuara. | Raporti, vendimet për gjetjet, rezultatet e riprovimit dhe rishikimi. |
| Paketa dhe identiteti | Stage 9 është pranuar për platformën e zgjedhur. Paketa përdor artefakte të fiksuara, identitete reale dhe delegim vetëm për shërbimin e miratuar. | Vendimi i pranimit, commit-i, versionet dhe hash-et e artefakteve e konfigurimit, identifikuesit publikë dhe rezultati i verifikimit të delegimit. |
| Gatishmëria për ndërhyrje dhe rikthim | Admini ka qasje te statusi, log-et dhe numëruesit. Në mjedis të izoluar janë provuar ndalja, restart-i, rollback-u kompatibil dhe rikthimi nga backup-i pa ulur pragjet e ruajtura të autoritetit ose ringjallur autorizime të vjetra. | Hapat e përdorur, inventari para/pas, versioni dhe integriteti i backup-it, identiteti dhe gjendja e rikthyer, rezultatet e pastrimit dhe të verifikimit të autoritetit. |

### Gjatë pilotit — çfarë verifikon admini

| Kriteri | Rezultati i pritshëm | Evidenca për t'u ruajtur |
| --- | --- | --- |
| Rruga e rrjetit | Connector-i përdor vetëm egress-in e miratuar. Klienti i pilotit arrin shërbimin me emrin NBSR. Rruga direkte nga ai klient te origjina private është e paarritshme. | Topologjia dhe rezultatet me kohë për rrugën NBSR dhe kontrollin e rrugës direkte. |
| Regjistrimi, rinovimi dhe gatishmëria | Autoriteti real pranon vetëm identitetin dhe shërbimin e deleguar. Ka saktësisht një pronar aktiv. `READY` shfaqet vetëm gjatë regjistrimit të vlefshëm. Rinovimi bëhet në të njëjtën lidhje kur ajo mbetet e shëndetshme. | Ngjarjet e redaktuara të regjistrimit/rinovimit, kalimet e statusit dhe numëruesi i pronarëve. |
| Kërkesa e lejuar dhe kërkesat e refuzuara | Një kërkesë e lejuar GET / brenda kufijve të profilit jep përgjigjen e pritur dhe arrin një herë në origjinë. Emri i gabuar dhe klienti i paautorizuar refuzohen pa rritur numëruesin e kërkesave në origjinë. | Identifikuesit e korrelacionit, rezultatet e klientit dhe numëruesit para/pas në origjinë. |
| Ndërprerja, skadimi dhe revokimi | Ndërprerja e dakorduar heq gatishmërinë kur regjistrimi s'është më aktiv. Rikthimi kërkon autoritet të vlefshëm dhe s'krijon pronar të dytë ose kërkesë të dyfishtë. Skadimi dhe revokimi i verifikuar ndalojnë pranimin sipas profilit. | Vija kohore e ngjarjeve, statusi, rezultati i verifikimit të revokimit dhe numëruesit e pronarëve e të kërkesave. |

### Kur ndalet piloti

| Kriteri | Rezultati i pritshëm | Evidenca për t'u ruajtur |
| --- | --- | --- |
| Shkelje sigurie ose sjellje jashtë profilit | Ndal menjëherë trafikun pilot nëse origjina del e arritshme direkt, kalon kërkesë e paautorizuar, ka pronar/kërkesë të dyfishtë, shfaqet `READY` pa autoritet të vlefshëm ose skadimi/revokimi s'zbatohet sipas profilit. Mos rifillo pa vendim të ri të pronarit të pilotit. | Arsyeja, koha, gjendja e fundit e njohur, log-et dhe numëruesit përkatës. |
| Mbarim i dritares, tejkalim i pragut ose humbje e vëzhgimit | Ndal trafikun te kufiri i miratuar i kohës, kërkesave ose burimeve, ose sapo statusi, log-et apo numëruesit e nevojshëm s'mund të verifikohen. Mos e zgjat dritaren gjatë ekzekutimit. | Kufiri i miratuar, vlera e matur ose sinjali që mungon, koha e ndaljes dhe maksimumet e burimeve. |
| Ndalja dhe mbyllja | Gatishmëria hiqet dhe pastrimi konfirmohet brenda afatit. Admini verifikon se s'kanë mbetur procese, lidhje ose pronarë të paketës. Identiteti, gjendja e qëndrueshme dhe burimet e palidhura ruhen. Pastrimi i pakonfirmuar ose një kriter i pakryer e lë pilotin të papranuar. | Statusi final, inventari para/pas, konfirmimi i pastrimit dhe vendimi i dokumentuar prano/refuzo me kufizimet. |
