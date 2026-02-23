<?php

/**
 * Flight Phase Classification Cron Job
 * 
 * Usage: php classify_phases_cron.php
 * 
 * This script:
 * 1. Scans EDA_FILES_PATH for CSV files
 * 2. Checks which files don't have 'phase' column
 * 3. Adds 'phase' and 'agl' columns to those files
 * 4. Classifies each row using flight phase logic
 */

require_once __DIR__ . '/vendor/autoload.php';

// Load environment
try {
    (new \Dotenv\Dotenv(__DIR__))->load();
} catch (\Exception $e) {
    echo "Warning: Could not load .env file\n";
}

$edaFilesPath = getenv('EDA_FILES_PATH') ?: 'C:\Users\Rizky\Downloads\EDA_FILES\FILES';
$logFile = __DIR__ . '/storage/logs/phase_classification.log';

// Aircraft configurations
$aircraftConfigs = [
    'Cessna 208 Caravan' => [
        'climb_torque_min' => 1200.0,
        'rotation_ias' => 58.0,
        'taxi_speed_threshold' => 6.0,
        'climb_rate_threshold' => 400.0,
    ],
    'Cessna 208B Grand Caravan' => [
        'climb_torque_min' => 1200.0,
        'rotation_ias' => 60.0,
        'taxi_speed_threshold' => 6.0,
        'climb_rate_threshold' => 400.0,
    ],
    'Generic' => [
        'climb_torque_min' => 1000.0,
        'rotation_ias' => 60.0,
        'taxi_speed_threshold' => 5.0,
        'climb_rate_threshold' => 300.0,
    ]
];

// Valid state transitions
$validTransitions = [
    'GROUND' => ['GROUND', 'TAXI', 'TAKEOFF ROLL'],
    'TAXI' => ['TAXI', 'GROUND', 'TAKEOFF ROLL', 'INITIAL CLIMB', 'CLIMBING FLIGHT'],
    'TAKEOFF ROLL' => ['TAKEOFF ROLL', 'ROTATION', 'INITIAL CLIMB', 'CLIMB', 'CLIMBING FLIGHT', 'GROUND'],
    'ROTATION' => ['ROTATION', 'INITIAL CLIMB', 'CLIMB', 'CLIMBING FLIGHT', 'TAKEOFF ROLL'],
    'INITIAL CLIMB' => ['INITIAL CLIMB', 'CLIMB', 'CLIMBING FLIGHT', 'LEVEL FLIGHT'],
    'CLIMB' => ['CLIMB', 'CLIMBING FLIGHT', 'CRUISE', 'LEVEL FLIGHT'],
    'CLIMBING FLIGHT' => ['CLIMBING FLIGHT', 'CLIMB', 'LEVEL FLIGHT', 'CRUISE', 'DESCENDING FLIGHT'],
    'CRUISE' => ['CRUISE', 'DESCENT', 'DESCENDING FLIGHT', 'LEVEL FLIGHT', 'CLIMBING FLIGHT'],
    'LEVEL FLIGHT' => ['LEVEL FLIGHT', 'CRUISE', 'CLIMBING FLIGHT', 'DESCENDING FLIGHT', 'MANEUVERING'],
    'DESCENDING FLIGHT' => ['DESCENDING FLIGHT', 'DESCENT', 'LEVEL FLIGHT', 'APPROACH', 'CRUISE'],
    'DESCENT' => ['DESCENT', 'DESCENDING FLIGHT', 'APPROACH', 'LEVEL FLIGHT'],
    'APPROACH' => ['APPROACH', 'FLARE', 'TOUCHDOWN', 'ROLLOUT', 'GROUND', 'TAXI', 'CLIMBING FLIGHT', 'LEVEL FLIGHT'],
    'FLARE' => ['FLARE', 'TOUCHDOWN', 'ROLLOUT', 'GROUND', 'TAXI', 'CLIMBING FLIGHT'],
    'TOUCHDOWN' => ['TOUCHDOWN', 'ROLLOUT', 'GROUND', 'TAXI'],
    'ROLLOUT' => ['ROLLOUT', 'TAXI', 'GROUND'],
    'MANEUVERING' => ['MANEUVERING', 'LEVEL FLIGHT', 'CLIMBING FLIGHT', 'DESCENDING FLIGHT', 'CRUISE'],
];

function logMessage($message) {
    global $logFile;
    $timestamp = date('Y-m-d H:i:s');
    $logMessage = "[$timestamp] $message\n";
    echo $logMessage;
    @file_put_contents($logFile, $logMessage, FILE_APPEND);
}

function hasPhaseColumn($csvPath) {
    $handle = fopen($csvPath, 'r');
    if (!$handle) return false;
    
    fgets($handle); // Skip metadata
    fgets($handle); // Skip data types
    $headerLine = fgets($handle);
    fclose($handle);
    
    if (!$headerLine) return false;
    
    $headers = str_getcsv(trim($headerLine));
    return in_array('phase', $headers) || in_array('Phase', $headers);
}

function calculateAGL($rows, $altColumn) {
    if (empty($rows)) return array_fill(0, count($rows), 0);
    
    $altitudes = array_column($rows, $altColumn);
    $altitudes = array_map('floatval', $altitudes);
    
    // Get departure elevation (first 180 rows)
    $depSample = array_slice($altitudes, 0, min(180, count($altitudes)));
    $depElev = !empty($depSample) ? median($depSample) : 0;
    
    // Get destination elevation (last 180 rows)
    $destSample = array_slice($altitudes, -min(180, count($altitudes)));
    $destElev = !empty($destSample) ? median($destSample) : 0;
    
    // Find peak altitude index
    $maxAlt = max($altitudes);
    $peakIdx = array_search($maxAlt, $altitudes);
    
    // Calculate AGL
    $aglValues = [];
    foreach ($altitudes as $idx => $alt) {
        $groundElev = ($idx <= $peakIdx) ? $depElev : $destElev;
        $aglValues[] = max(0, $alt - $groundElev);
    }
    
    return $aglValues;
}

function median($arr) {
    sort($arr);
    $count = count($arr);
    if ($count == 0) return 0;
    $mid = floor($count / 2);
    return ($count % 2) ? $arr[$mid] : ($arr[$mid - 1] + $arr[$mid]) / 2;
}

function classifyPhase($row, $prevPhase, $config, $validTransitions) {
    $agl = $row['agl'] ?? 0;
    $gndSpd = $row['GndSpd'] ?? 0;
    $ias = $row['IAS'] ?? 0;
    $vspd = $row['VSpd'] ?? 0;
    $torque = $row['E1 Torq'] ?? 0;
    $pitch = $row['Pitch'] ?? 0;
    
    // Speed Gate (Primary)
    $isDefinitelyGround = $gndSpd < 40;
    
    // Altitude Gate
    $isNearGround = $agl < 75;
    
    $isMoving = $gndSpd > $config['taxi_speed_threshold'];
    $isHighPower = $torque > $config['climb_torque_min'];
    $isClimbing = $vspd > $config['climb_rate_threshold'];
    $isDescending = $vspd < -$config['climb_rate_threshold'];
    
    // Ground operations
    if ($isNearGround || $isDefinitelyGround) {
        if ($gndSpd > 40) {
            if (in_array($prevPhase, ['APPROACH', 'FLARE', 'TOUCHDOWN', 'DESCENDING FLIGHT'])) {
                return 'ROLLOUT';
            }
            if (in_array($prevPhase, ['TAKEOFF ROLL', 'ROTATION'])) {
                return 'TAKEOFF ROLL';
            }
            return 'TOUCHDOWN';
        }
        
        if ($isHighPower && $isMoving && $gndSpd > 15) {
            return 'TAKEOFF ROLL';
        }
        
        return $isMoving ? 'TAXI' : 'GROUND';
    }
    
    // Flight operations
    if ($agl < 200 && $isHighPower && $pitch > 0 && $vspd > 0) {
        return 'ROTATION';
    }
    
    if ($agl < 200 && !$isHighPower) {
        return $pitch > 0 ? 'FLARE' : 'APPROACH';
    }
    
    if ($isClimbing) {
        return $agl < 500 ? 'INITIAL CLIMB' : 'CLIMB';
    }
    
    if ($isDescending) {
        return $agl < 1000 ? 'APPROACH' : 'DESCENT';
    }
    
    if (abs($vspd) < 200) {
        return $agl > 3000 ? 'CRUISE' : 'LEVEL FLIGHT';
    }
    
    return 'MANEUVERING';
}

function isValidTransition($from, $to, $validTransitions) {
    return isset($validTransitions[$from]) && in_array($to, $validTransitions[$from]);
}

function processFile($csvPath, $config, $validTransitions) {
    logMessage("Processing: " . basename($csvPath));
    
    $handle = fopen($csvPath, 'r');
    if (!$handle) {
        logMessage("ERROR: Cannot open file");
        return false;
    }
    
    // Read file
    $metadata = fgets($handle);
    $dataTypes = fgets($handle);
    $headerLine = fgets($handle);
    $headers = str_getcsv(trim($headerLine));
    
    // Find column indices
    $colMap = array_flip($headers);
    $altCol = $colMap['AltGPS'] ?? $colMap['AltB'] ?? $colMap['AltMSL'] ?? null;
    
    if ($altCol === null) {
        fclose($handle);
        logMessage("ERROR: No altitude column found");
        return false;
    }
    
    // Read all data rows
    $rows = [];
    while (($line = fgets($handle)) !== false) {
        $data = str_getcsv($line);
        if (count($data) != count($headers)) continue;
        
        $row = array_combine($headers, $data);
        $rows[] = $row;
    }
    fclose($handle);
    
    if (empty($rows)) {
        logMessage("WARNING: No data rows found");
        return false;
    }
    
    // Calculate AGL
    $aglValues = calculateAGL($rows, $headers[$altCol]);
    
    // Classify phases
    $prevPhase = 'GROUND';
    foreach ($rows as $idx => &$row) {
        $row['agl'] = $aglValues[$idx];
        $newPhase = classifyPhase($row, $prevPhase, $config, $validTransitions);
        
        // Validate transition
        if (!isValidTransition($prevPhase, $newPhase, $validTransitions)) {
            $newPhase = $prevPhase; // Keep previous phase if invalid
        }
        
        $row['phase'] = $newPhase;
        $prevPhase = $newPhase;
    }
    
    // Write back to file
    $tempPath = $csvPath . '.tmp';
    $outHandle = fopen($tempPath, 'w');
    if (!$outHandle) {
        logMessage("ERROR: Cannot create temp file");
        return false;
    }
    
    // Write headers with new columns
    fwrite($outHandle, $metadata);
    fwrite($outHandle, $dataTypes);
    fwrite($outHandle, implode(',', array_merge($headers, ['agl', 'phase'])) . "\n");
    
    // Write data
    foreach ($rows as $row) {
        $values = [];
        foreach ($headers as $h) {
            $values[] = isset($row[$h]) ? $row[$h] : '';
        }
        $values[] = $row['agl'];
        $values[] = $row['phase'];
        fputcsv($outHandle, $values);
    }
    
    fclose($outHandle);
    
    // Replace original file
    if (!rename($tempPath, $csvPath)) {
        @unlink($tempPath);
        logMessage("ERROR: Cannot replace original file");
        return false;
    }
    
    logMessage("SUCCESS: Processed " . count($rows) . " rows");
    return true;
}

// Main execution
logMessage("=== Flight Phase Classification Cron Job Started ===");

$folders = glob($edaFilesPath . '/*', GLOB_ONLYDIR);
$processedCount = 0;
$skippedCount = 0;

foreach ($folders as $folder) {
    $csvFiles = glob($folder . '/*.csv');
    
    foreach ($csvFiles as $csvPath) {
        $fileName = basename($csvPath);
        
        // Skip files ending with ______
        if (preg_match('/______\.csv$/', $fileName)) {
            continue;
        }
        
        // Check if already has phase column
        if (hasPhaseColumn($csvPath)) {
            $skippedCount++;
            continue;
        }
        
        // Determine aircraft type from folder name
        $folderName = basename($folder);
        $aircraftType = 'Generic';
        foreach (array_keys($aircraftConfigs) as $type) {
            if (stripos($folderName, $type) !== false) {
                $aircraftType = $type;
                break;
            }
        }
        
        $config = $aircraftConfigs[$aircraftType];
        
        if (processFile($csvPath, $config, $validTransitions)) {
            $processedCount++;
        }
    }
}

logMessage("=== Cron Job Completed ===");
logMessage("Processed: $processedCount files");
logMessage("Skipped: $skippedCount files (already have phase column)");
