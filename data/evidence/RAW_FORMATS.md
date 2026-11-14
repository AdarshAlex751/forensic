# RAW_FORMATS.md — exact raw line formats of the case files

The generator writes the case files in `CASE-1010F/` in exactly these formats, and every `source.quote` in the
fakes is written as the line the generator will produce. All times are EST with a fixed `-05:00` offset.
Host machine `lt-219` appears in logs as `LT-219`.

## CSV files (header is line 1; one record per line; no quoting unless a field contains a comma)

| File | Header | Example row |
|---|---|---|
| `access/badge_access.csv` | `timestamp,badge_id,reader_id,direction,result` | `2026-03-04T18:16:40-05:00,40417,rdr-219,IN,GRANTED` |
| `network/wifi_ap_logs.csv` | `timestamp,ap_id,client_mac,event,rssi,ssid` | `2026-03-04T18:41:00-05:00,ap-2-03,02:1F:9A:10:00:02,DISASSOC,-61,JRR2-SECURE` |
| `endpoint/security_log.csv` | `TimeCreated,EventID,Computer,TargetUserName,LogonType,ObjectName,AccessMask,ProcessName` | logon: `2026-03-04T18:17:05-05:00,4624,LT-219,hgibson,2,,,C:\Windows\System32\winlogon.exe` |
| | | file access: `2026-03-04T18:18:02-05:00,4663,LT-219,hgibson,,C:\Projects\Titan\thruster_v4.step,0x1,C:\Windows\explorer.exe` |
| | | logoff: `2026-03-04T18:31:20-05:00,4634,LT-219,hgibson,2,,,` |
| `endpoint/file_audit.csv` | `timestamp,host,user,action,path,bytes,target_volume` | `2026-03-04T18:18:02-05:00,LT-219,hgibson,COPY,C:\Projects\Titan\thruster_v4.step,48211968,E:` (READ rows leave `target_volume` empty) |
| `cctv/index.csv` | `camera_id,window_start,window_end,status,clip_ref` | `cam-03,2026-03-04T18:05:00-05:00,2026-03-04T18:30:00-05:00,OFFLINE,` |
| `it/maintenance_calendar.csv` | `work_order,asset,start,end,technician,description` | `WO-3117,lt-219,2026-03-04T19:00:00-05:00,2026-03-04T21:30:00-05:00,Frederik Mendelssohn,Monthly security patching (offline media)` |
| `financial/transactions.csv` | `timestamp,account,description,counterparty,amount,balance` | `2026-03-06T10:42:00-05:00,CHK-7731,SIGNING BONUS,Northline Systems Inc,25000.00,31842.17` |
| `access/parking_exit.csv` | `timestamp,lane,permit_id,plate,direction` | `2026-03-04T18:44:00-05:00,EXIT-1,P-2088,W26-VCU,OUT` |

Event mapping notes:
- One `cctv/index.csv` OFFLINE row yields two events citing the same line: `camera_offline` at `window_start`,
  `camera_online` at `window_end`.
- One `maintenance_calendar.csv` row yields one `maintenance_window` event at `start`.
- `parking_exit.csv` direction `IN` → `parking_entry`, `OUT` → `parking_exit`.

## Text and document files

| File | Format | What `quote` is |
|---|---|---|
| `endpoint/usbstor.txt` | RegRipper `usbstor` output, one block per device (below) | the `S/N:` line |
| `comms/mailbox.mbox` | standard mbox; `Date:` headers like `Wed, 04 Mar 2026 17:30:00 -0500` | the exact body line containing the sentence |
| `comms/slack_export/<channel or DM id>/<YYYY-MM-DD>.json` | Slack export: array of `{"type":"message","user":…,"text":…,"ts":…}`, 2-space indent | the message `text` exactly |
| `statements/<name>.pdf` | interview statement; each key sentence on its own line | the sentence exactly |

usbstor block:

```
Disk&Ven_SanDisk&Prod_Ultra&Rev_1.00 [2026-03-04T18:17:30-05:00]
  S/N: 4C530001230918112443&0 [2026-03-04T18:17:30-05:00]
  FriendlyName  : SanDisk Ultra USB Device
  First InstallDate : 2026-03-04T18:17:30-05:00
```

Slack `ts` is the Unix epoch of the message time as a string with six decimals (`"1772638200.000100"`); the
event's `t` is the same moment in EST.
