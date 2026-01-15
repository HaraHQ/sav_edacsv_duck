# EDA Upload Flow

## Overview

The EDA upload endpoint now automatically creates jobs that are picked up by the queue processor for extraction.

## How It Works

### 1. Upload Endpoint (`/eda/upload`)

When a file is uploaded:
- Saves ZIP file to `storage/files/eda_{uniqid}_{original_name}.zip`
- Creates job JSON in `storage/queue/job_{uniqid}.json`
- Returns immediately with job ID

**Code Location**: `app/Http/Controllers/EdaController.php` → `upload()` method

### 2. Queue Processor (`process_queue.php`)

Runs continuously and:
- Watches `storage/queue/` directory every 2 seconds
- Picks up new `.json` files
- Extracts ZIP to `EDA_FILES_PATH` (from .env)
- Moves job JSON to `storage/processed/`
- Deletes temporary ZIP file

**Run Command**:
```bash
php process_queue.php
```

### 3. Job JSON Structure

```json
{
  "id": "job_67835a1f2b3c4",
  "file_name": "flight_data.zip",
  "file_path": "C:\\path\\to\\EDA\\storage\\files\\eda_67835a1f2b3c4_flight_data.zip",
  "status": "pending",
  "created_at": "2025-01-07 14:30:45"
}
```

## Directory Structure

```
EDA/
├── storage/
│   ├── files/          # Uploaded ZIP files (temporary)
│   ├── queue/          # Pending jobs (JSON)
│   └── processed/      # Completed jobs (JSON)
└── process_queue.php   # Queue processor script
```

## Environment Variables

Required in `.env`:

```env
EDA_FILES_PATH=C:\Users\Rizky\Downloads\EDA_FILES\FILES
```

This is where CSV files will be extracted to.

## API Usage

**Request**:
```bash
curl -X POST http://localhost:8053/eda/upload \
  -H "Authorization: Bearer <jwt-token>" \
  -F "file=@flight_data.zip"
```

**Response**:
```json
{
  "success": true,
  "jobId": "job_67835a1f2b3c4",
  "elapsed": 0.15,
  "message": "File uploaded successfully, processing in background"
}
```

## Monitoring

### Check Queue Status

```bash
# Count pending jobs
dir storage\queue\*.json | measure

# Count processed jobs
dir storage\processed\*.json | measure
```

### View Processor Logs

The queue processor outputs to console:
```
[2025-01-07 14:30:45] Queue processor started...
Watching directory: C:\path\to\EDA\storage\queue
EDA_FILES_PATH: C:\Users\Rizky\Downloads\EDA_FILES\FILES

[2025-01-07 14:30:47] Found 1 job(s)
[2025-01-07 14:30:47] Processing job: job_67835a1f2b3c4 (flight_data.zip)
  - Zip file: C:\path\to\EDA\storage\files\eda_67835a1f2b3c4_flight_data.zip
  - Extract to: C:\Users\Rizky\Downloads\EDA_FILES\FILES
  - Extracting 150 files...
  - Extraction completed, temp file cleaned
[2025-01-07 14:30:49] ✓ Job completed: job_67835a1f2b3c4
```

## Troubleshooting

### Jobs Not Processing

1. Check if `process_queue.php` is running
2. Verify `storage/queue/` directory exists and is writable
3. Check `EDA_FILES_PATH` in `.env` is correct and writable

### Upload Fails

1. Check JWT token is valid
2. Verify `storage/files/` directory exists and is writable
3. Check PHP upload limits in `php.ini`:
   - `upload_max_filesize = 256M`
   - `post_max_size = 256M`
   - `memory_limit = 384M`

### Extraction Fails

1. Check ZIP file is valid
2. Verify `EDA_FILES_PATH` exists and is writable
3. Check processor logs for specific error messages
