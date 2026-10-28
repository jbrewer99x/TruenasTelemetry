Disk telemetry uses cached Linux sysfs metadata to enumerate disks and select
ATA versus SCSI commands without probing devices to identify them.

* SATA/ATA: `hdparm -C /dev/sdX` (ATA CHECK POWER MODE).
* SAS/SCSI, including disk shelves: `sg_requests --raw /dev/sdX`
  (SCSI REQUEST SENSE). Both fixed and descriptor sense formats are decoded.
* SSD/NVMe: shown as SSD (no spindle); spin-down is not applicable.

Neither status command requests media access or starts the spindle. Failed,
unsupported, malformed, or unauthorized checks show Unknown, never Spun down.
SCSI LOW POWER and STANDBY_Y are shown as rotation unknown because those states
do not prove the spindle has stopped. A successful SCSI NO SENSE response is
interpreted as active, as in smartmontools; actual reporting depends on firmware.

The old unconditional `midclt call disk.temperatures` call is replaced. ATA
SMART temperature reads use explicit `-d ata -n standby,3,5 -A -j`: standby or
unsupported power checks exit without further reads. SAS temperature collection
uses only LOG SENSE (`sg_logs --readonly -xx --page=0x0d`); -xx suppresses
INQUIRY. HDD temperature requests are skipped for standby, sleep, unknown, and
ambiguous low-power states. Missing temperatures are not displayed as zero.

TrueNAS requires hdparm, sg_requests, sg_logs, and smartctl. The SSH account must
have device access, or passwordless sudo for these commands (the collector uses
`sudo -n` when not root). No permissions or host packages are changed automatically.
Missing tools fail per drive. Requests run eight drives at a time with five-second
subprocess timeouts. Browser polls do not overlap.

Validation: `python3 -m unittest discover -s tests -v` and
`node --check static/js/dashboard.js`. Tests mock disk commands; hardware behavior
has not been verified against this particular controller/shelf.

Deployment must include disk_probe.py alongside app.py. The current local source
and /mnt/telemetry deployed source differ beyond this change; reconcile those
existing differences before deploying. /mnt/telemetry is currently read-only.

If hdparm returns an unrecognized state successfully, the collector falls back
to the existing guarded ATA smartctl command. Successful SMART attribute output
indicates the standby/unsupported checks passed (smartctl 7.4 omits power_mode
from JSON). Standby is recognized from the explicit message, never exit code
alone. Unsupported checks stay unknown; no unguarded retry is used.
