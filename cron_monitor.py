#!/usr/bin/env python3
"""
Cron job monitor with email alerts.
Monitors cron jobs by checking their last execution time and alerts if they're overdue.
"""

import os
import sys
import json
import smtplib
import argparse
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path


CRON_LOG_DIR = "/var/log"
DEFAULT_CONFIG_FILE = "cron_config.json"
DEFAULT_STATE_FILE = "cron_state.json"


def load_config(config_path):
    """Load job configuration from JSON file."""
    if not os.path.exists(config_path):
        print(f"Config file not found: {config_path}")
        print("Creating default configuration...")
        default_config = {
            "jobs": [
                {
                    "name": "backup_daily",
                    "log_pattern": "backup*.log",
                    "expected_interval_hours": 24,
                    "alert_threshold_hours": 26
                },
                {
                    "name": "cleanup_weekly",
                    "log_pattern": "cleanup*.log",
                    "expected_interval_hours": 168,
                    "alert_threshold_hours": 180
                }
            ],
            "email": {
                "smtp_server": "smtp.example.com",
                "smtp_port": 587,
                "sender": "alerts@example.com",
                "recipients": ["admin@example.com"],
                "username": "",
                "password": ""
            }
        }
        with open(config_path, "w") as f:
            json.dump(default_config, f, indent=2)
        return default_config
    
    with open(config_path, "r") as f:
        return json.load(f)


def load_state(state_path):
    """Load previous run state from file."""
    if not os.path.exists(state_path):
        return {"last_check": None, "job_states": {}}
    
    with open(state_path, "r") as f:
        return json.load(f)


def save_state(state_path, state):
    """Save current state to file."""
    state["last_check"] = datetime.now().isoformat()
    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)


def find_log_files(log_pattern, search_dirs=None):
    """Find log files matching the pattern in common log directories."""
    if search_dirs is None:
        search_dirs = [CRON_LOG_DIR, "/var/log/cron", os.path.expanduser("~")]
    
    matching_files = []
    for search_dir in search_dirs:
        if not os.path.exists(search_dir):
            continue
        try:
            for root, dirs, files in os.walk(search_dir):
                for filename in files:
                    if log_pattern.replace("*", "") in filename:
                        matching_files.append(os.path.join(root, filename))
        except PermissionError:
            continue
    
    return matching_files


def get_last_modification_time(filepath):
    """Get the last modification time of a file."""
    try:
        mtime = os.path.getmtime(filepath)
        return datetime.fromtimestamp(mtime)
    except OSError:
        return None


def check_job_status(job, state):
    """Check if a cron job is running on schedule."""
    log_files = find_log_files(job["log_pattern"])
    
    if not log_files:
        return {
            "name": job["name"],
            "status": "unknown",
            "message": f"No log files found matching pattern: {job['log_pattern']}",
            "last_run": None
        }
    
    latest_time = None
    latest_file = None
    
    for log_file in log_files:
        mtime = get_last_modification_time(log_file)
        if mtime and (latest_time is None or mtime > latest_time):
            latest_time = mtime
            latest_file = log_file
    
    if latest_time is None:
        return {
            "name": job["name"],
            "status": "unknown",
            "message": "Could not determine last modification time",
            "last_run": None
        }
    
    now = datetime.now()
    time_since_last_run = now - latest_time
    hours_since_last_run = time_since_last_run.total_seconds() / 3600
    
    threshold = job.get("alert_threshold_hours", job["expected_interval_hours"] * 1.2)
    
    if hours_since_last_run > threshold:
        status = "overdue"
        message = f"Job is {hours_since_last_run:.1f} hours overdue (threshold: {threshold}h)"
    elif hours_since_last_run > job["expected_interval_hours"]:
        status = "warning"
        message = f"Job running late: {hours_since_last_run:.1f}h since last run"
    else:
        status = "ok"
        message = f"Last run {hours_since_last_run:.1f} hours ago"
    
    return {
        "name": job["name"],
        "status": status,
        "message": message,
        "last_run": latest_time.isoformat(),
        "log_file": latest_file,
        "hours_since_last_run": hours_since_last_run
    }


def send_email_alert(config, job_results):
    """Send email alert for failed/overdue jobs."""
    email_config = config.get("email", {})
    
    if not email_config.get("smtp_server"):
        print("Email not configured. Skipping alert.")
        return False
    
    overdue_jobs = [j for j in job_results if j["status"] in ("overdue", "warning")]
    
    if not overdue_jobs:
        return False
    
    subject = f"[Cron Alert] {len(overdue_jobs)} job(s) require attention"
    
    body = "Cron Job Monitor Alert\n"
    body += "=" * 40 + "\n\n"
    body += f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    
    for job in overdue_jobs:
        body += f"Job: {job['name']}\n"
        body += f"Status: {job['status'].upper()}\n"
        body += f"Details: {job['message']}\n"
        if job.get("last_run"):
            body += f"Last Run: {job['last_run']}\n"
        if job.get("log_file"):
            body += f"Log File: {job['log_file']}\n"
        body += "\n"
    
    msg = MIMEMultipart()
    msg["From"] = email_config["sender"]
    msg["To"] = ", ".join(email_config["recipients"])
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))
    
    try:
        if email_config.get("username") and email_config.get("password"):
            server = smtplib.SMTP(email_config["smtp_server"], email_config["smtp_port"])
            server.starttls()
            server.login(email_config["username"], email_config["password"])
            server.send_message(msg)
            server.quit()
        else:
            server = smtplib.SMTP(email_config["smtp_server"], email_config["smtp_port"])
            server.send_message(msg)
            server.quit()
        
        print(f"Alert email sent to {email_config['recipients']}")
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False


def run_monitor(config_path, state_path, send_alerts=False):
    """Run the cron job monitor."""
    config = load_config(config_path)
    state = load_state(state_path)
    
    print(f"Cron Monitor - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)
    
    job_results = []
    
    for job in config.get("jobs", []):
        result = check_job_status(job, state)
        job_results.append(result)
        
        status_icon = {"ok": "✓", "warning": "⚠", "overdue": "✗", "unknown": "?"}.get(
            result["status"], "?"
        )
        print(f"[{status_icon}] {result['name']}: {result['message']}")
    
    print("=" * 50)
    
    if send_alerts:
        send_email_alert(config, job_results)
    
    save_state(state_path, state)
    
    overdue_count = sum(1 for j in job_results if j["status"] == "overdue")
    warning_count = sum(1 for j in job_results if j["status"] == "warning")
    
    print(f"\nSummary: {overdue_count} overdue, {warning_count} warnings")
    
    return overdue_count + warning_count


def init_config(config_path):
    """Initialize configuration file."""
    config = {
        "jobs": [
            {
                "name": "example_job",
                "log_pattern": "*.log",
                "expected_interval_hours": 24,
                "alert_threshold_hours": 26
            }
        ],
        "email": {
            "smtp_server": "smtp.example.com",
            "smtp_port": 587,
            "sender": "cron-monitor@example.com",
            "recipients": ["admin@example.com"],
            "username": "",
            "password": ""
        }
    }
    
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
    
    print(f"Configuration file created: {config_path}")
    print("Edit this file to configure your cron jobs and email settings.")


def main():
    parser = argparse.ArgumentParser(
        description="Monitor cron jobs and send email alerts when they're overdue."
    )
    parser.add_argument(
        "-c", "--config",
        default=DEFAULT_CONFIG_FILE,
        help="Path to configuration file (default: cron_config.json)"
    )
    parser.add_argument(
        "-s", "--state",
        default=DEFAULT_STATE_FILE,
        help="Path to state file (default: cron_state.json)"
    )
    parser.add_argument(
        "-a", "--alert",
        action="store_true",
        help="Send email alerts for overdue jobs"
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="Initialize configuration file"
    )
    
    args = parser.parse_args()
    
    if args.init:
        init_config(args.config)
        sys.exit(0)
    
    exit_code = run_monitor(args.config, args.state, send_alerts=args.alert)
    sys.exit(0 if exit_code == 0 else 1)


if __name__ == "__main__":
    main()
