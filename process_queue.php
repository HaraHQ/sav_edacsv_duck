<?php
require_once __DIR__ . '/vendor/autoload.php';

// Load environment
(new Laravel\Lumen\Bootstrap\LoadEnvironmentVariables(
    __DIR__
))->bootstrap();

// Also try direct .env loading as fallback
if (file_exists(__DIR__ . '/.env')) {
    $lines = file(__DIR__ . '/.env', FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
    foreach ($lines as $line) {
        if (strpos($line, '=') !== false && !str_starts_with($line, '#')) {
            list($key, $value) = explode('=', $line, 2);
            $_ENV[trim($key)] = trim($value);
        }
    }
}

$queueDir = __DIR__ . '/storage/queue';
$processedDir = __DIR__ . '/storage/processed';

if (!is_dir($queueDir)) {
    mkdir($queueDir, 0755, true);
}
if (!is_dir($processedDir)) {
    mkdir($processedDir, 0755, true);
}

echo "[" . date('Y-m-d H:i:s') . "] Queue processor started...\n";
echo "Watching directory: $queueDir\n";
echo "EDA_FILES_PATH: " . ($_ENV['EDA_FILES_PATH'] ?? getenv('EDA_FILES_PATH') ?: 'Not set') . "\n\n";

while (true) {
    $files = glob($queueDir . '/*.json');
    
    if (count($files) > 0) {
        echo "[" . date('Y-m-d H:i:s') . "] Found " . count($files) . " job(s)\n";
    }
    
    foreach ($files as $jobFile) {
        $jobData = json_decode(file_get_contents($jobFile), true);
        
        if (!$jobData) {
            echo "[" . date('Y-m-d H:i:s') . "] Invalid job file: $jobFile\n";
            continue;
        }
        
        echo "[" . date('Y-m-d H:i:s') . "] Processing job: " . $jobData['id'] . " (" . $jobData['file_name'] . ")\n";
        
        try {
            processFile($jobData);
            
            rename($jobFile, $processedDir . '/' . basename($jobFile));
            echo "[" . date('Y-m-d H:i:s') . "] ✓ Job completed: " . $jobData['id'] . "\n\n";
            
        } catch (Exception $e) {
            echo "[" . date('Y-m-d H:i:s') . "] ✗ Job failed: " . $jobData['id'] . " - " . $e->getMessage() . "\n\n";
        }
    }
    
    sleep(2);
}

function processFile($jobData) {
    $zipPath = $jobData['file_path'];
    $basePath = $_ENV['EDA_FILES_PATH'] ?? getenv('EDA_FILES_PATH') ?: 'C:\\Users\\Rizky\\Downloads\\EDA_FILES\\FILES';
    
    echo "  - Zip file: $zipPath\n";
    echo "  - Extract to: $basePath\n";
    
    if (!file_exists($zipPath)) {
        throw new Exception('Zip file not found: ' . $zipPath);
    }
    
    $zip = new ZipArchive();
    $result = $zip->open($zipPath);
    if ($result !== TRUE) {
        throw new Exception('Cannot open zip file (error code: ' . $result . ')');
    }
    
    echo "  - Extracting " . $zip->numFiles . " files...\n";
    
    if (!$zip->extractTo($basePath)) {
        $zip->close();
        throw new Exception('Cannot extract zip file to: ' . $basePath);
    }
    
    $zip->close();
    unlink($zipPath);
    
    echo "  - Extraction completed, temp file cleaned\n";
}
?>