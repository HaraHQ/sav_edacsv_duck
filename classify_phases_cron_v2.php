<?php

/**
 * Flight Phase Classification Cron Job – v2
 * ------------------------------------------
 * Wraps the Python FOQA Flight Phase Classifier v3.0.
 *
 * Mirrors the v1 cron setup:
 *   - Reads EDA_FILES_PATH from .env
 *   - Scans all subfolders for CSV files
 *   - Skips files ending in ______
 *   - Skips files already containing a FLIGHT_PHASE column
 *   - Detects aircraft type from the subfolder name
 *   - Runs the Python classifier and replaces the original file in-place
 *   - Logs to storage/logs/phase_classification.log
 *
 * Usage: php classify_phases_cron_v2.php
 *
 * Recommended crontab entry (every 5 minutes):
 *   *\/5 * * * * /usr/bin/php /path/to/classify_phases_cron_v2.php >> /dev/null 2>&1
 */

require_once __DIR__ . '/vendor/autoload.php';

// ─────────────────────────────────────────────────────────────────
//  CONFIGURATION  –  edit paths if needed
// ─────────────────────────────────────────────────────────────────

define('PYTHON_BIN',   '/usr/bin/python3');
define('SCRIPT_PATH',  __DIR__ . '/flight_phase_classifier.py');
define('LOG_FILE',     __DIR__ . '/storage/logs/phase_classification.log');
define('LOCK_FILE',    '/tmp/foqa_classify_v2.lock');
define('DEBUG_MODE',   false);   // Set true to pass --debug to the classifier

// ─────────────────────────────────────────────────────────────────
//  ENVIRONMENT
// ─────────────────────────────────────────────────────────────────

try {
    $dotenv = \Dotenv\Dotenv::createImmutable(__DIR__);
    $dotenv->load();
} catch (\Exception $e) {
    echo "Warning: Could not load .env file\n";
}

$edaFilesPath = getenv('EDA_FILES_PATH') ?: ($_ENV['EDA_FILES_PATH'] ?? null);

if (!$edaFilesPath) {
    logMessage("ERROR: EDA_FILES_PATH is not set. Add it to your .env file.");
    exit(1);
}

// ─────────────────────────────────────────────────────────────────
//  AIRCRAFT CONFIGS  –  matched against subfolder names
// ─────────────────────────────────────────────────────────────────

$aircraftConfigs = [
    'Cessna 208B Grand Caravan EX' => 'Cessna 208B Grand Caravan EX',
    'Cessna 208B Grand Caravan'    => 'Cessna 208B Grand Caravan',
    'Cessna 208 Caravan'           => 'Cessna 208 Caravan',
    'Generic'                      => 'Generic',   // fallback
];

// ─────────────────────────────────────────────────────────────────
//  LOCK  –  prevent overlapping cron runs
// ─────────────────────────────────────────────────────────────────

$lockHandle = fopen(LOCK_FILE, 'c');
if (!$lockHandle || !flock($lockHandle, LOCK_EX | LOCK_NB)) {
    logMessage("Another instance is already running. Exiting.");
    exit(0);
}

// ─────────────────────────────────────────────────────────────────
//  SANITY CHECKS
// ─────────────────────────────────────────────────────────────────

@mkdir(dirname(LOG_FILE), 0755, true);

if (!is_executable(PYTHON_BIN)) {
    logMessage("ERROR: Python binary not found or not executable: " . PYTHON_BIN);
    releaseLock($lockHandle);
    exit(1);
}

if (!is_file(SCRIPT_PATH)) {
    logMessage("ERROR: Classifier script not found: " . SCRIPT_PATH);
    releaseLock($lockHandle);
    exit(1);
}

// ─────────────────────────────────────────────────────────────────
//  MAIN
// ─────────────────────────────────────────────────────────────────

logMessage("=== Flight Phase Classification Cron Job v2 Started ===");
logMessage("EDA Files Path: " . $edaFilesPath);
logMessage("Running as user: " . get_current_user());

$folders = glob($edaFilesPath . '/*', GLOB_ONLYDIR);
logMessage("Found " . count($folders) . " folder(s)");

if (empty($folders)) {
    logMessage("ERROR: No subfolders found in EDA_FILES_PATH. Check the path.");
    logMessage("Attempted path: " . $edaFilesPath);
    releaseLock($lockHandle);
    exit(1);
}

$processedCount = 0;
$skippedCount   = 0;
$failedCount    = 0;

foreach ($folders as $folder) {
    logMessage("Scanning folder: " . basename($folder));
    $csvFiles = glob($folder . '/*.csv');
    logMessage("  Found " . count($csvFiles) . " CSV file(s)");

    // Detect aircraft type from folder name (longest match wins)
    $aircraftType = detectAircraftType(basename($folder), $aircraftConfigs);

    foreach ($csvFiles as $csvPath) {
        $fileName = basename($csvPath);
        logMessage("  Checking: " . $fileName);

        // Skip files ending with ______
        if (preg_match('/______\.csv$/', $fileName)) {
            logMessage("    Skipped: ends with ______");
            continue;
        }

        // Skip files already classified
        if (hasPhaseColumn($csvPath)) {
            logMessage("    Skipped: already has FLIGHT_PHASE column");
            $skippedCount++;
            continue;
        }

        logMessage("    Aircraft type : " . $aircraftType);
        logMessage("    Will process  : " . $fileName);

        $result = processFile($csvPath, $aircraftType);

        if ($result === true) {
            $processedCount++;
        } else {
            $failedCount++;
        }
    }
}

logMessage("=== Cron Job v2 Completed ===");
logMessage("Processed : $processedCount file(s)");
logMessage("Skipped   : $skippedCount file(s) (already classified)");
logMessage("Failed    : $failedCount file(s)");

releaseLock($lockHandle);
exit($failedCount > 0 ? 1 : 0);


// ─────────────────────────────────────────────────────────────────
//  FUNCTIONS
// ─────────────────────────────────────────────────────────────────

/**
 * Run the Python classifier on $csvPath.
 * Outputs to a temp file, then replaces the original in-place.
 */
function processFile(string $csvPath, string $aircraftType): bool
{
    $tempOutput = $csvPath . '.classified.tmp';

    $cmd = buildCommand($csvPath, $tempOutput, $aircraftType);

    $output   = [];
    $exitCode = 0;
    exec($cmd . ' 2>&1', $output, $exitCode);

    $outputText = implode("\n", $output);

    if ($exitCode !== 0) {
        logMessage("    ERROR: Classifier failed (exit $exitCode)");
        logMessage("    Output: " . substr($outputText, 0, 500));
        @unlink($tempOutput);
        return false;
    }

    // Replace original with classified version
    if (!rename($tempOutput, $csvPath)) {
        logMessage("    ERROR: Could not replace original file (check permissions)");
        @unlink($tempOutput);
        return false;
    }

    logSummary($outputText);
    logMessage("    SUCCESS: File updated in-place");
    return true;
}

/**
 * Build the escaped shell command for the Python classifier.
 */
function buildCommand(string $input, string $output, string $aircraft): string
{
    $py     = escapeshellarg(PYTHON_BIN);
    $script = escapeshellarg(SCRIPT_PATH);
    $in     = escapeshellarg($input);
    $out    = escapeshellarg($output);
    $ac     = escapeshellarg($aircraft);
    $debug  = DEBUG_MODE ? ' --debug' : '';

    return "$py $script $in $out --aircraft $ac$debug";
}

/**
 * Check if the CSV already has a FLIGHT_PHASE column (3-line header format).
 */
function hasPhaseColumn(string $csvPath): bool
{
    $handle = fopen($csvPath, 'r');
    if (!$handle) return false;

    fgets($handle); // metadata line 1
    fgets($handle); // metadata line 2
    $headerLine = fgets($handle);
    fclose($handle);

    if (!$headerLine) return false;

    $headers = array_map('trim', str_getcsv(trim($headerLine)));
    return in_array('FLIGHT_PHASE', $headers, true);
}

/**
 * Match the folder name against known aircraft types (longest match first).
 */
function detectAircraftType(string $folderName, array $configs): string
{
    // Sort by string length descending so longer (more specific) names match first
    $types = array_keys($configs);
    usort($types, fn($a, $b) => strlen($b) - strlen($a));

    foreach ($types as $type) {
        if ($type === 'Generic') continue;
        if (stripos($folderName, $type) !== false) {
            return $configs[$type];
        }
    }

    return 'Generic';
}

/**
 * Extract and log a concise summary from the classifier's stdout.
 */
function logSummary(string $rawOutput): void
{
    // Phase distribution
    if (preg_match('/Phase Distribution.*?(?=─{3}|\z)/s', $rawOutput, $m)) {
        $lines = array_filter(
            explode("\n", trim($m[0])),
            fn($l) => trim($l) !== '' && !str_starts_with(trim($l), '─')
        );
        foreach ($lines as $line) {
            logMessage("      " . trim($line));
        }
    }

    // Special events
    if (preg_match('/Special Events.*?(?=─{3}|\z)/s', $rawOutput, $m)) {
        $lines = array_filter(
            explode("\n", trim($m[0])),
            fn($l) => trim($l) !== '' && !str_starts_with(trim($l), '─') && trim($l) !== 'Special Events'
        );
        foreach ($lines as $line) {
            logMessage("      " . trim($line));
        }
    }

    // Confidence / stability
    if (preg_match('/Mean confidence\s*:\s*([\d.]+)/', $rawOutput, $mc)) {
        logMessage("      Mean confidence : {$mc[1]}");
    }
    if (preg_match('/Mean stability\s*:\s*([\d.]+)/', $rawOutput, $ms)) {
        logMessage("      Mean stability  : {$ms[1]}");
    }
}

/**
 * Append a timestamped message to the log file and echo it.
 */
function logMessage(string $message): void
{
    $timestamp  = date('Y-m-d H:i:s');
    $logMessage = "[$timestamp] $message\n";
    echo $logMessage;
    @file_put_contents(LOG_FILE, $logMessage, FILE_APPEND | LOCK_EX);
}

/**
 * Release the exclusive lock.
 */
function releaseLock($handle): void
{
    flock($handle, LOCK_UN);
    fclose($handle);
}
