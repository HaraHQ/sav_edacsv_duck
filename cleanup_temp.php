<?php
/**
 * DuckDB Temp File Cleanup Script
 * Run this periodically via cron/scheduler to clean orphaned temp files
 * 
 * Usage: php cleanup_temp.php
 * Cron: Run every 5 minutes - php /path/to/cleanup_temp.php
 */

$tempDir = sys_get_temp_dir();
$maxAge = 300; // 5 minutes

$patterns = [
    'duckdb_temp_storage_*.tmp',
    'duckdb_temp_*.db',
    'duckdb_query*.sql',
    'php*.tmp' // PHP temp files from tempnam()
];

$cleaned = 0;
$errors = 0;

echo "[" . date('Y-m-d H:i:s') . "] Starting temp file cleanup...\n";
echo "Temp directory: $tempDir\n";

foreach ($patterns as $pattern) {
    $files = glob($tempDir . DIRECTORY_SEPARATOR . $pattern);
    
    if ($files) {
        foreach ($files as $file) {
            if (!file_exists($file)) continue;
            
            $age = time() - filemtime($file);
            
            if ($age > $maxAge) {
                if (@unlink($file)) {
                    $cleaned++;
                    echo "  ✓ Cleaned: " . basename($file) . " (age: {$age}s)\n";
                } else {
                    $errors++;
                    echo "  ✗ Failed: " . basename($file) . "\n";
                }
            }
        }
    }
}

echo "[" . date('Y-m-d H:i:s') . "] Cleanup complete: $cleaned files cleaned, $errors errors\n";
