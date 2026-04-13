# multisend

A `telegram-send` replacement with support for **multiple named bot profiles**.

No external dependencies — uses only Python 3 stdlib.

## Install

**One-liner (curl):**
```bash
curl -fsSL https://raw.githubusercontent.com/humojaguar/multisend/main/install.sh | bash
```

**Or clone and install:**
```bash
git clone https://github.com/humojaguar/multisend.git
cd multisend
bash install.sh
```

**Or manually:**
```bash
curl -fsSL https://raw.githubusercontent.com/humojaguar/multisend/main/multisend.py -o multisend.py
chmod +x multisend.py
sudo mv multisend.py /usr/local/bin/multisend
```

## Setup

```bash
multisend --configure          # add your first bot
multisend --configure          # run again to add more bots
multisend --list               # view all configured bots
multisend --set-default alerts # change the default bot
multisend --remove homelab     # delete a profile
```

Config is stored at `~/.config/multisend/config.ini` (mode 600).

## Usage

```bash
# Send to the default bot
multisend "hello world"

# Send to a specific bot
multisend -b alerts "disk at 95%"

# Send to multiple bots (comma-separated)
multisend -b homelab,alerts "rebooting in 5 min"

# Send to ALL configured bots
multisend --all "deploy complete"

# Pipe stdin
echo "build passed" | multisend -b ci
df -h | multisend -b homelab

# Formatting
multisend --markdown "*bold* and _italic_"
multisend --html "<b>bold</b>"

# Disable link preview
multisend --no-preview "https://example.com"

# Silent (no notification sound)
multisend --silent "low priority note"

# Send image with caption
multisend --image /tmp/graph.png "Weekly stats" -b reports

# Send a video (inline playback)
multisend --video /tmp/clip.mp4 -b mybot
multisend --video /tmp/clip.mp4 "check this out" -b mybot

# Send a file
multisend --file /tmp/backup.tar.gz -b homelab

# Suppress success output (for scripts/cron)
multisend -q "cron job done"

# Print config file path
multisend --config-file
```

## Logging

All sends and errors are logged automatically to `~/.config/multisend/multisend.log`.
Logs rotate at 5 MB and keep up to 5 files (`multisend.log`, `multisend.log.1` … `.5`).

```
2026-04-13 14:22:01  INFO      sent bot=mybot chat_id=55667788 message_id=42
2026-04-13 14:22:08  ERROR     failed bot=alerts chat_id=112233445 error=Network error: ...
```

Override the log path with `--log-file`:

```bash
multisend --log-file /var/log/multisend.log "hello"
```

## Config file format

```ini
[homelab]
token = 123456789:ABCdef...
chat_id = -100123456789
default = yes

[alerts]
token = 987654321:XYZabc...
chat_id = 112233445

[personal]
token = 111222333:...
chat_id = 55667788
```

You can also edit this file directly.

## Systemd / cron examples

```bash
# crontab — send daily disk report
0 8 * * * df -h | /usr/local/bin/multisend -q -b homelab

# Script integration
if ! pg_dump mydb > /tmp/backup.sql; then
    multisend -b alerts "⚠ DB backup failed on $(hostname)"
fi
```

## Tips

- The **default bot** is used when `-b` is not specified. The first configured bot is the default unless you set one with `--set-default`.
- Multiple bots via `-b` are comma-separated with no spaces: `-b homelab,alerts`.
- `--all` sends to every profile regardless of default.
- Exit code is 0 on full success, 1 if any send fails (useful in scripts).
- Video uploads are capped at 50 MB by the Telegram Bot API.
- Log and config files both live under `~/.config/multisend/` by default.
