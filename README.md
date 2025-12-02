# EDA

## Running

```bash
php -S localhost:8000 -t public
```

## Example Query

```bash
curl --request POST \
  --url http://localhost:8000/eda/query \
  --header 'Content-Type: application/json' \
  --data '{
  "fields": ["Lcl_Date", "Lcl_Time", "AltB", "IAS"],
  "dateStart": "2025-11-22",
  "dateEnd": "2025-11-23",
  "acReg": "PK-SNP",
  "icaoCode": "WALJ",
  "includeMetadata": true
}'
```

## Environment Variables

- JWT_SECRET: potash_copper_coal (later can change)
- EDA_FILES_PATH=C:\Users\Rizky\Downloads\EDA_FILES\FILES
- DUCKDB_PATH=C:\Users\Rizky\Downloads\EDA_FILES\duckdb.exe

## File Structure

The EDA_FILES_PATH should contain folders with this example structure:

```
C:\Users\Rizky\Downloads\EDA_FILES\FILES\
├── EDA PK-SNP 22 NOV 2025\
│   ├── log_251122_082756_WALJ.csv
│   ├── log_251122_083456_WALJ.csv
│   ├── log_251122_084256_WALJ.csv
│   └── log_251122_063205______.csv (ignored)
├── EDA PK-ABC 23 NOV 2025\
│   ├── log_251123_091234_WIII.csv
│   └── log_251123_101234_WIII.csv
└── duckdb.exe (at parent level)
```

### Folder Name Format

- Pattern: `EDA {AIRCRAFT_REG} {DD} {MMM} {YYYY}`
- Example: `EDA PK-SNP 22 NOV 2025`
- Aircraft registration extracted: `PK-SNP`
- Date extracted: `22 NOV 2025`

### CSV File Name Format

- Pattern: `log_{YYMMDD}_{HHMMSS}_{ICAO}.csv`
- Example: `log_251122_082756_WALJ.csv`
- Date: `251122` = 22 Nov 2025
- Time: `082756` = 08:27:56
- ICAO: `WALJ` = Airport code
- Files ending with `______` are ignored

### CSV File Structure

- Line 1: Metadata (airframe info, software versions)
- Line 2: Data types
- Line 3: Column headers
- Line 4+: Flight data
