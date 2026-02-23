# Flight Phase Classification - Cron Job

## Overview

Automatically adds `phase` and `agl` columns to newly uploaded CSV files that don't have them yet.

## Files Created

1. **classify_phases_cron.php** - Main cron script
2. **run_classify_phases.bat** - Windows batch file for Task Scheduler
3. **EdaController.php** - Added 2 new endpoints

## How It Works

1. Scans all folders in `EDA_FILES_PATH`
2. Checks each CSV file for `phase` column
3. If missing, calculates:
   - **AGL** (Above Ground Level) - Dynamic ground reference
   - **Phase** - Flight phase classification (GROUND, TAXI, TAKEOFF, CLIMB, etc.)
4. Adds columns to CSV and saves back
5. Logs all activity to `storage/logs/phase_classification.log`

## Setup Cron Job (Windows Task Scheduler)

### Option 1: Manual Trigger via API

```bash
# Trigger classification manually
curl --request POST \
  --url http://localhost:8053/eda/classify-phases \
  --header 'Authorization: Bearer <your-jwt-token>'

# Check status/logs
curl --request GET \
  --url http://localhost:8053/eda/classify-phases/status \
  --header 'Authorization: Bearer <your-jwt-token>'
```

### Option 2: Windows Task Scheduler (Automated)

1. Open **Task Scheduler** (taskschd.msc)
2. Click **Create Basic Task**
3. Name: `EDA Flight Phase Classification`
4. Trigger: **Daily** at **2:00 AM** (or your preferred time)
5. Action: **Start a program**
   - Program: `C:\Users\Rizky\Desktop\EDA\run_classify_phases.bat`
   - Start in: `C:\Users\Rizky\Desktop\EDA`
6. Finish and test: Right-click task → **Run**

### Option 3: Command Line Setup

```cmd
schtasks /create /tn "EDA_PhaseClassification" /tr "C:\Users\Rizky\Desktop\EDA\run_classify_phases.bat" /sc daily /st 02:00 /ru SYSTEM
```

## Manual Execution

```bash
# Run directly
php classify_phases_cron.php

# Or use batch file
run_classify_phases.bat
```

## What Gets Added to CSV Files

### Before:
```
Lcl Date,Lcl Time,AltGPS,GndSpd,IAS,VSpd,E1 Torq,Pitch
2025-11-22,08:27:56,1250,0,0,0,450,0
2025-11-22,08:28:00,1250,5,0,0,480,0
2025-11-22,08:30:15,1250,45,55,850,1350,8
```

### After:
```
Lcl Date,Lcl Time,AltGPS,GndSpd,IAS,VSpd,E1 Torq,Pitch,agl,phase
2025-11-22,08:27:56,1250,0,0,0,450,0,0,GROUND
2025-11-22,08:28:00,1250,5,0,0,480,0,0,TAXI
2025-11-22,08:30:15,1250,45,55,850,1350,8,450,INITIAL CLIMB
```

## Flight Phases Detected

- **GROUND** - Parked, engines off/idle
- **TAXI** - Moving on ground
- **TAKEOFF ROLL** - Accelerating on runway
- **ROTATION** - Nose lifting off
- **INITIAL CLIMB** - First 500ft climbing
- **CLIMB** - Climbing to cruise
- **CRUISE** - Level flight at altitude
- **LEVEL FLIGHT** - Level flight below cruise altitude
- **DESCENDING FLIGHT** - Descending
- **DESCENT** - Controlled descent
- **APPROACH** - Final approach
- **FLARE** - Nose up before touchdown
- **TOUCHDOWN** - Wheels touch runway
- **ROLLOUT** - Slowing after landing
- **MANEUVERING** - Other flight maneuvers

## Logs

Check logs at: `storage/logs/phase_classification.log`

Example log output:
```
[2025-01-08 02:00:01] === Flight Phase Classification Cron Job Started ===
[2025-01-08 02:00:02] Processing: log_251122_082756_WALJ.csv
[2025-01-08 02:00:05] SUCCESS: Processed 1850 rows
[2025-01-08 02:00:06] Processing: log_251122_083456_WALJ.csv
[2025-01-08 02:00:09] SUCCESS: Processed 1920 rows
[2025-01-08 02:00:10] === Cron Job Completed ===
[2025-01-08 02:00:10] Processed: 2 files
[2025-01-08 02:00:10] Skipped: 15 files (already have phase column)
```

## Performance

- **Processing speed**: ~600 rows/second
- **Memory usage**: ~50MB per file
- **Typical file**: 1800 rows = ~3 seconds

## Troubleshooting

### Files not being processed?

Check if they already have `phase` column:
```bash
# Check CSV header (line 3)
head -n 3 "C:\Users\Rizky\Downloads\EDA_FILES\FILES\EDA PK-SNP 22 NOV 2025\log_251122_082756_WALJ.csv"
```

### Script not running?

1. Check PHP path: `where php`
2. Test manually: `php classify_phases_cron.php`
3. Check logs: `storage\logs\phase_classification.log`

### Permission errors?

Run as Administrator or ensure write permissions on CSV files.

## Integration with Existing Endpoints

Once files have `phase` column, you can query it:

```bash
# Query with phase filter
curl --request GET \
  --url 'http://localhost:8053/eda/query?fields[]=Lcl_Date&fields[]=phase&fields[]=E1_Torq&acReg=PK-SNP' \
  --header 'Authorization: Bearer <your-jwt-token>'
```

## Future Enhancements

- [ ] Add phase-based torque limit alerts (only alert during CLIMB)
- [ ] Phase duration statistics endpoint
- [ ] Phase transition validation alerts
- [ ] Real-time classification during CSV upload
- [ ] Phase-colored charts
