# cron-monitor

Simple cron job monitor that checks if your scheduled tasks are actually running and sends email alerts when they're overdue.

## Why I built this

I kept forgetting to check if my backup scripts and cleanup jobs were actually running. This tool monitors log files from cron jobs and alerts me when something hasn't run in longer than expected.

## Quick start

```bash
# Install dependencies
pip install -r requirements.txt

# Initialize config
python cron_monitor.py --init

# Edit cron_config.json with your jobs

# Run a check
python cron_monitor.py

# Run with email alerts
python cron_monitor.py --alert
```

## Configuration

Edit `cron_config.json` to add your jobs:

```json
{
  "jobs": [
    {
      "name": "daily_backup",
      "log_pattern": "backup*.log",
      "expected_interval_hours": 24,
      "alert_threshold_hours": 26
    }
  ],
  "email": {
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "sender": "you@example.com",
    "recipients": ["admin@example.com"],
    "username": "your_username",
    "password": "your_password"
  }
}
```

### Job config fields

- `name`: Whatever you want to call the job
- `log_pattern`: Pattern to match log files (uses substring matching, not full glob)
- `expected_interval_hours`: How often the job should run
- `alert_threshold_hours`: When to trigger an alert (usually a bit more than expected)

## How it works

1. Scans common log directories (`/var/log`, home dir) for files matching your patterns
2. Checks the last modification time of those files
3. Compares against your configured thresholds
4. Reports status: OK, warning, overdue, or unknown
5. Optionally sends email if any jobs are overdue

## Running it

```bash
# Basic check (no alerts)
python cron_monitor.py

# With email alerts
python cron_monitor.py --alert

# Custom config file
python cron_monitor.py -c /path/to/config.json

# Initialize fresh config
python cron_monitor.py --init
```

## Exit codes

- `0`: All jobs OK
- `1`: One or more jobs overdue or warning

Useful for CI/CD or chaining with other scripts.

## Adding to crontab

Run this monitor itself as a cron job:

```cron
0 * * * * /usr/bin/python3 /path/to/cron_monitor.py --alert >> /var/log/cron-monitor.log 2>&1
```

## Notes

- No external dependencies beyond Python stdlib
- State file tracks last check time (auto-created)
- Email uses SMTP with optional TLS
- Log file detection is based on modification time, not content parsing

## License

MIT - do whatever you want with it.
