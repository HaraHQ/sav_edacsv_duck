# Flight Phase Classification - Ubuntu Server Setup

## Prerequisites

```bash
# Ensure PHP is installed
php -v

# Install required PHP extensions (if not already installed)
sudo apt update
sudo apt install php-cli php-mbstring php-xml
```

## Installation

### 1. Upload Files to Server

```bash
# Navigate to your EDA project directory
cd /var/www/eda

# Ensure the cron script exists
ls -la classify_phases_cron.php

# Make sure PHP has write permissions on CSV files
sudo chown -R www-data:www-data /data/eda_files/FILES
# OR if running as specific user:
sudo chown -R your-username:your-username /data/eda_files/FILES
```

### 2. Test Manual Execution

```bash
# Run the script manually first to test
php classify_phases_cron.php

# Check the log output
tail -f storage/logs/phase_classification.log
```

## Setup Cron Job (Automated)

### Option 1: Using Crontab (Recommended)

```bash
# Edit crontab for current user
crontab -e

# Add this line to run daily at 2:00 AM
0 2 * * * cd /var/www/eda && /usr/bin/php classify_phases_cron.php >> storage/logs/cron_execution.log 2>&1

# Or run every 6 hours
0 */6 * * * cd /var/www/eda && /usr/bin/php classify_phases_cron.php >> storage/logs/cron_execution.log 2>&1

# Or run every hour
0 * * * * cd /var/www/eda && /usr/bin/php classify_phases_cron.php >> storage/logs/cron_execution.log 2>&1
```

**Cron Schedule Examples:**
```
0 2 * * *       # Daily at 2:00 AM
0 */6 * * *     # Every 6 hours
0 * * * *       # Every hour
*/30 * * * *    # Every 30 minutes
0 0 * * 0       # Weekly on Sunday at midnight
```

### Option 2: System-wide Cron (as root)

```bash
# Edit system crontab
sudo crontab -e

# Add line (replace paths and user)
0 2 * * * cd /var/www/eda && /usr/bin/php classify_phases_cron.php >> /var/www/eda/storage/logs/cron_execution.log 2>&1
```

### Option 3: Using /etc/cron.d/

```bash
# Create a cron file
sudo nano /etc/cron.d/eda-phase-classification

# Add this content (replace username and paths):
0 2 * * * www-data cd /var/www/eda && /usr/bin/php classify_phases_cron.php >> /var/www/eda/storage/logs/cron_execution.log 2>&1

# Save and exit (Ctrl+X, Y, Enter)

# Set proper permissions
sudo chmod 644 /etc/cron.d/eda-phase-classification
```

## Verify Cron Job Setup

```bash
# List current user's cron jobs
crontab -l

# Check if cron service is running
sudo systemctl status cron

# View cron logs
sudo tail -f /var/log/syslog | grep CRON

# Check your application log
tail -f /var/www/eda/storage/logs/phase_classification.log
```

## Manual Trigger via API

```bash
# Trigger classification manually
curl --request POST \
  --url http://your-server.com/eda/classify-phases \
  --header 'Authorization: Bearer YOUR_JWT_TOKEN'

# Check status
curl --request GET \
  --url http://your-server.com/eda/classify-phases/status \
  --header 'Authorization: Bearer YOUR_JWT_TOKEN'
```

## Create Shell Script (Optional)

For easier management, create a wrapper script:

```bash
# Create script
nano /var/www/eda/run_classify_phases.sh
```

Add this content:

```bash
#!/bin/bash

# Flight Phase Classification Runner
# Change to project directory
cd /var/www/eda

# Run PHP script
/usr/bin/php classify_phases_cron.php

# Log execution time
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Cron job executed" >> storage/logs/cron_execution.log
```

Make it executable:

```bash
chmod +x /var/www/eda/run_classify_phases.sh

# Test it
./run_classify_phases.sh
```

Then use in crontab:

```bash
crontab -e

# Add:
0 2 * * * /var/www/eda/run_classify_phases.sh
```

## Environment Variables

Ensure `.env` file has correct paths:

```bash
# Edit .env
nano /var/www/eda/.env

# Verify these settings:
EDA_FILES_PATH=/path/to/EDA_FILES/FILES
DUCKDB_PATH=/path/to/duckdb
```

## Permissions Setup

```bash
# Ensure log directory exists and is writable
mkdir -p /var/www/eda/storage/logs
chmod 755 /var/www/eda/storage/logs

# Ensure CSV files are writable
chmod -R 755 /path/to/EDA_FILES/FILES

# If running as www-data user
sudo chown -R www-data:www-data /var/www/eda/storage
sudo chown -R www-data:www-data /path/to/EDA_FILES/FILES
```

## Monitoring & Logs

### View Real-time Logs

```bash
# Watch classification log
tail -f /var/www/eda/storage/logs/phase_classification.log

# Watch cron execution log
tail -f /var/www/eda/storage/logs/cron_execution.log

# Watch system cron log
sudo tail -f /var/log/syslog | grep CRON
```

### Check Last Run

```bash
# View last 50 lines of classification log
tail -n 50 /var/www/eda/storage/logs/phase_classification.log

# Check if cron ran today
grep "$(date +%Y-%m-%d)" /var/www/eda/storage/logs/cron_execution.log
```

## Troubleshooting

### Cron not running?

```bash
# Check cron service
sudo systemctl status cron

# Restart cron service
sudo systemctl restart cron

# Check cron is enabled
sudo systemctl is-enabled cron
```

### Permission denied errors?

```bash
# Check file ownership
ls -la /var/www/eda/classify_phases_cron.php

# Fix ownership
sudo chown www-data:www-data /var/www/eda/classify_phases_cron.php

# Check CSV directory permissions
ls -la /path/to/EDA_FILES/FILES
```

### PHP not found in cron?

```bash
# Find PHP path
which php

# Use full path in crontab
0 2 * * * cd /var/www/eda && /usr/bin/php classify_phases_cron.php
```

### Script runs but doesn't process files?

```bash
# Run manually with verbose output
php classify_phases_cron.php

# Check .env file is readable
cat /var/www/eda/.env | grep EDA_FILES_PATH

# Verify path exists
ls -la /path/to/EDA_FILES/FILES
```

## Email Notifications (Optional)

Setup email alerts when cron runs:

```bash
# Install mail utility
sudo apt install mailutils

# Edit crontab
crontab -e

# Add MAILTO at top
MAILTO=your-email@example.com

# Your cron job will now email output
0 2 * * * cd /var/www/eda && /usr/bin/php classify_phases_cron.php
```

## Performance Optimization

For large datasets:

```bash
# Increase PHP memory limit
sudo nano /etc/php/8.1/cli/php.ini

# Find and modify:
memory_limit = 512M
max_execution_time = 300

# Restart PHP-FPM if using it
sudo systemctl restart php8.1-fpm
```

## Systemd Service (Advanced)

Create a systemd service for better control:

```bash
# Create service file
sudo nano /etc/systemd/system/eda-phase-classification.service
```

Add content:

```ini
[Unit]
Description=EDA Flight Phase Classification
After=network.target

[Service]
Type=oneshot
User=www-data
WorkingDirectory=/var/www/eda
ExecStart=/usr/bin/php /var/www/eda/classify_phases_cron.php
StandardOutput=append:/var/www/eda/storage/logs/phase_classification.log
StandardError=append:/var/www/eda/storage/logs/phase_classification.log

[Install]
WantedBy=multi-user.target
```

Create timer:

```bash
sudo nano /etc/systemd/system/eda-phase-classification.timer
```

Add content:

```ini
[Unit]
Description=Run EDA Phase Classification Daily
Requires=eda-phase-classification.service

[Timer]
OnCalendar=daily
OnCalendar=02:00
Persistent=true

[Install]
WantedBy=timers.target
```

Enable and start:

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable timer
sudo systemctl enable eda-phase-classification.timer

# Start timer
sudo systemctl start eda-phase-classification.timer

# Check status
sudo systemctl status eda-phase-classification.timer

# List all timers
sudo systemctl list-timers

# Run manually
sudo systemctl start eda-phase-classification.service
```

## Quick Reference

```bash
# Setup cron (simplest method)
crontab -e
# Add: 0 2 * * * cd /var/www/eda && php classify_phases_cron.php >> storage/logs/cron_execution.log 2>&1

# Test manually
cd /var/www/eda && php classify_phases_cron.php

# View logs
tail -f storage/logs/phase_classification.log

# Check cron status
crontab -l
sudo systemctl status cron
```

## Security Notes

```bash
# Restrict log file access
chmod 640 /var/www/eda/storage/logs/*.log

# Ensure .env is not web-accessible
chmod 600 /var/www/eda/.env

# Verify CSV directory is not web-accessible
# Add to nginx/apache config to deny access
```
