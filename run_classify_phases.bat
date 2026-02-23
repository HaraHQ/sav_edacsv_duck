@echo off
REM Flight Phase Classification Cron Job
REM Run this script with Windows Task Scheduler

cd /d "%~dp0"
php classify_phases_cron.php

REM Optional: Add timestamp to log
echo [%date% %time%] Cron job executed >> storage\logs\cron_execution.log
