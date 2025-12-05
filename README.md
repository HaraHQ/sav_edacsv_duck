# EDA

## Running

```bash
# Start the web server
php -S localhost:8053 -t public

# Start the queue processor (in separate terminal)
php process_queue.php
```

## Authentication

All API endpoints require JWT authentication. Include the token in the Authorization header:

```bash
Authorization: Bearer <your-jwt-token>
```

The JWT token must be signed with HMAC256 using the JWT_SECRET from environment variables.

**Note:** JWT authentication is disabled when `APP_DEBUG=true` for development convenience.

### Creating JWT Token

**PHP Example:**

Below is not using any module to create JWT Token (HMAC256)

```php
<?php
function createJwtToken($secret, $expirationMinutes = 1) {
    $header = json_encode(['typ' => 'JWT', 'alg' => 'HS256']);
    $payload = json_encode(['exp' => time() + ($expirationMinutes * 60)]);
    
    $headerEncoded = rtrim(strtr(base64_encode($header), '+/', '-_'), '=');
    $payloadEncoded = rtrim(strtr(base64_encode($payload), '+/', '-_'), '=');
    
    $signature = hash_hmac('sha256', "$headerEncoded.$payloadEncoded", $secret, true);
    $signatureEncoded = rtrim(strtr(base64_encode($signature), '+/', '-_'), '=');
    
    return "$headerEncoded.$payloadEncoded.$signatureEncoded";
}

$token = createJwtToken('potash_copper_coal', 1);
echo $token;
?>
```

**JavaScript Example:**

```js
const crypto = require('crypto');

function createJwtToken(secret, expirationMinutes = 1) {
    const header = Buffer.from(JSON.stringify({typ: 'JWT', alg: 'HS256'})).toString('base64url');
    const payload = Buffer.from(JSON.stringify({exp: Math.floor(Date.now() / 1000) + (expirationMinutes * 60)})).toString('base64url');
    
    const signature = crypto.createHmac('sha256', secret)
        .update(`${header}.${payload}`)
        .digest('base64url');
    
    return `${header}.${payload}.${signature}`;
}

const token = createJwtToken('potash_copper_coal', 1);
console.log(token);
```

## API Endpoints

### 1. Test Endpoint
```bash
# Test API connectivity and configuration
curl --request GET \
  --url http://localhost:8053/test \
  --header 'Authorization: Bearer <your-jwt-token>'
```

### 2. Query Data (GET)
```bash
# Get all data
curl --request GET \
  --url http://localhost:8053/eda/query \
  --header 'Authorization: Bearer <your-jwt-token>'

# Get specific fields with filters
curl --request GET \
  --url 'http://localhost:8053/eda/query?fields[]=Lcl_Date&fields[]=AltB&dateStart=2025-11-22&acReg=PK-SNP' \
  --header 'Authorization: Bearer <your-jwt-token>'
```

### 3. Query Data (POST)
```bash
# Complex query with JSON payload
curl --request POST \
  --url http://localhost:8053/eda/query \
  --header 'Content-Type: application/json' \
  --header 'Authorization: Bearer <your-jwt-token>' \
  --data '{
  "fields": ["Lcl_Date", "Lcl_Time", "AltB", "IAS"],
  "dateStart": "2025-11-22",
  "dateEnd": "2025-11-23",
  "acReg": "PK-SNP",
  "icaoCode": "WALJ",
  "includeMetadata": true
}'
```

### 4. Check Job Status
```bash
# Get processing job status counts
curl --request GET \
  --url http://localhost:8053/eda/status \
  --header 'Authorization: Bearer <your-jwt-token>'
```
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
