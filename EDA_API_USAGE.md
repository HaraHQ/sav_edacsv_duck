# EDA API Usage Guide

## Overview
This Lumen 8 API provides GraphQL-like functionality to query CSV data from DuckDB with filtering capabilities.

## Endpoints

### Test Endpoint
```
GET /test
```
Verifies the API setup and environment configuration.

### Query Endpoint
```
GET|POST /eda/query
```

## Query Parameters

### Fields Selection (GraphQL-like)
- `fields[]`: Array of field names to return (optional, returns all fields if not specified)
- Available fields: `Lcl_Date`, `Lcl_Time`, `UTCOfst`, `AtvWpt`, `Latitude`, `Longitude`, `AltB`, `BaroA`, `AltMSL`, `OAT`, `IAS`, `GndSpd`, `VSpd`, `Pitch`, `Roll`, `LatAc`, `NormAc`, `HDG`, `TRK`, `volt1`, `amp1`, `FQtyL`, `FQtyR`, `FQtyLlbs`, `FQtyRlbs`, `E1_FFlow`, `E1_OilT`, `E1_OilP`, `E1_Torq`, `E1_NP`, `E1_NG`, `E1_ITT`, `AltGPS`, `TAS`, `HSIS`, `CRS`, `NAV1`, `NAV2`, `COM1`, `COM2`, `HCDI`, `VCDI`, `WndSpd`, `WndDr`, `WptDst`, `WptBrg`, `MagVar`, `AfcsOn`, `RollM`, `PitchM`, `RollC`, `PichC`, `VSpdG`, `GPSfix`, `HAL`, `VAL`, `HPLwas`, `HPLfd`, `VPLwas`

### Filters
- `dateStart`: Start date filter (format: YYYY-MM-DD)
- `dateEnd`: End date filter (format: YYYY-MM-DD)
- `acReg`: Aircraft registration filter (e.g., "PK-SNP")
- `icaoCode`: ICAO airport code filter (e.g., "WALL")
- `includeMetadata`: Include CSV metadata (airframe info, software versions, etc.)
- Any CSV field name: Filter by field value (e.g., `AtvWpt=WALL`)

## Usage Examples

### 1. Get all data
```bash
curl "http://localhost:8000/eda/query"
```

### 2. Get specific fields only
```bash
curl "http://localhost:8000/eda/query?fields[]=timestamp&fields[]=altitude&fields[]=speed"
```

### 3. Filter by date range
```bash
curl "http://localhost:8000/eda/query?dateStart=2025-12-01&dateEnd=2025-12-02"
```

### 4. Filter by aircraft registration
```bash
curl "http://localhost:8000/eda/query?acReg=PK-SNP"
```

### 5. Filter by ICAO code
```bash
curl "http://localhost:8000/eda/query?icaoCode=WALL"
```

### 6. Combined filters with specific fields
```bash
curl "http://localhost:8000/eda/query?fields[]=Lcl_Date&fields[]=AltB&dateStart=2025-12-01&dateEnd=2025-12-02&acReg=PK-SNP&icaoCode=WALL"
```

### 7. Include metadata from CSV files
```bash
curl "http://localhost:8000/eda/query?includeMetadata=true&fields[]=Lcl_Date&fields[]=AltB"
```

### 8. Filter by CSV field values
```bash
curl "http://localhost:8000/eda/query?fields[]=Lcl_Date&fields[]=AltB&AtvWpt=WALL"
```

### 9. POST request with JSON
```bash
curl -X POST "http://localhost:8000/eda/query" \
  -H "Content-Type: application/json" \
  -d '{
    "fields": ["Lcl_Date", "AltB", "IAS"],
    "dateStart": "2025-12-01",
    "dateEnd": "2025-12-02",
    "acReg": "PK-SNP",
    "icaoCode": "WALL",
    "includeMetadata": true
  }'
```

## Folder Structure Expected
```
C:\Users\Rizky\Downloads\EDA_FILES\FILES\
├── EDA PK-SNP 22 NOV 2025\
│   ├── log_251122_082756_WALL.csv
│   ├── log_251122_083456_WALL.csv
│   └── log_251122_063205______.csv (ignored)
└── EDA PK-ABC 23 NOV 2025\
    ├── log_251123_091234_WIII.csv
    └── log_251123_101234_WIII.csv
```

## Response Format

### Standard Response
```json
{
  "success": true,
  "result": [
    {
      "Lcl_Date": "2025-11-22",
      "Lcl_Time": "08:27:56",
      "AltB": "1500",
      "IAS": "250"
    }
  ]
}
```

### Response with Metadata
```json
{
  "success": true,
  "result": {
    "data": [
      {
        "Lcl_Date": "2025-11-22",
        "Lcl_Time": "08:27:56",
        "AltB": "1500",
        "IAS": "250"
      }
    ],
    "metadata": {
      "log_version": "1.01",
      "airframe_name": "Cessna 208B",
      "unit_software_part_number": "006-B1177-56",
      "unit_software_version": "20.05",
      "system_software_part_number": "006-B2499-03",
      "system_id": "25B51076C",
      "mode": "NORMAL",
      "flightstream_header": "25B51076C_20000101_000000"
    }
  }
}
```

## Error Response
```json
{
  "success": false,
  "error": "Error message here"
}
```