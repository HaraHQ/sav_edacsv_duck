<?php

namespace App\Services;

use Carbon\Carbon;

class EdaService
{
    private $edaFilesPath;
    private $duckdbPath;

    public function __construct()
    {
        $this->edaFilesPath = env('EDA_FILES_PATH');
        $this->duckdbPath = env('DUCKDB_PATH');
    }

    public function queryData(array $fields, array $filters, $includeMetadata = false)
    {
        $folders = $this->getFilteredFolders($filters);
        $csvFiles = $this->getFilteredCsvFiles($folders, $filters);
        
        if (empty($csvFiles)) {
            return [];
        }

        $totalFiles = count($csvFiles);
        $page = isset($filters['page']) ? (int)$filters['page'] : 1;
        $filesPerPage = 50;
        
        $data = $this->queryDuckDb($csvFiles, $fields, $filters, $page, $filesPerPage);
        
        if ($includeMetadata && !empty($csvFiles)) {
            return [
                'data' => $data,
                'metadata' => $this->extractMetadata($csvFiles[0]['path']),
                'filters' => $filters,
                'pagination' => [
                    'total_files' => $totalFiles,
                    'files_per_page' => $filesPerPage,
                    'current_page' => $page,
                    'total_pages' => ceil($totalFiles / $filesPerPage),
                    'is_complete' => $totalFiles <= $filesPerPage
                ]
            ];
        }
        
        if (is_array($data) && !isset($data['debug'])) {
            return [
                'data' => $data,
                'pagination' => [
                    'total_files' => $totalFiles,
                    'files_per_page' => $filesPerPage,
                    'current_page' => $page,
                    'total_pages' => ceil($totalFiles / $filesPerPage),
                    'is_complete' => $totalFiles <= $filesPerPage
                ]
            ];
        }
        
        return $data;
    }

    private function getFilteredFolders(array $filters)
    {
        $folders = glob($this->edaFilesPath . '\\*', GLOB_ONLYDIR);
        
        if (isset($filters['acReg'])) {
            $folders = array_filter($folders, function($folder) use ($filters) {
                $folderName = basename($folder);
                // Try both patterns: direct aircraft name and EDA format
                return strcasecmp($folderName, $filters['acReg']) === 0 || 
                       preg_match('/^EDA\s+' . preg_quote($filters['acReg'], '/') . '\s+/i', $folderName);
            });
        }
        
        return $folders;
    }

    private function getFilteredCsvFiles(array $folders, array $filters)
    {
        $csvFiles = [];
        
        foreach ($folders as $folder) {
            $files = glob($folder . '\\*.csv');
            
            foreach ($files as $file) {
                $fileName = basename($file);
                
                if ($this->matchesFilters($fileName, $filters)) {
                    $csvFiles[] = [
                        'path' => $file,
                        'acReg' => $this->extractAcRegFromFolder($folder)
                    ];
                }
            }
        }
        
        return $csvFiles;
    }
    
    private function extractAcRegFromFolder($folderPath)
    {
        $folderName = basename($folderPath);
        // Try EDA pattern first: EDA {AIRCRAFT_REG} {DD} {MMM} {YYYY}
        if (preg_match('/^EDA\s+([A-Z0-9-]+)\s+/i', $folderName, $matches)) {
            return $matches[1];
        }
        // Try direct aircraft name pattern: PK-XXX
        if (preg_match('/^([A-Z0-9-]+)$/i', $folderName, $matches)) {
            return $matches[1];
        }
        return 'UNKNOWN';
    }
    
    private function matchesFilters($fileName, $filters)
    {
        if (preg_match('/______\.csv$/', $fileName)) {
            return false;
        }
        
        if (preg_match('/log_(\d{6})_\d{6}_([A-Z]{4})\.csv$/', $fileName, $matches)) {
            $fileDate = $matches[1];
            $icaoCode = $matches[2];
            
            if (isset($filters['icaoCode']) && $icaoCode !== $filters['icaoCode']) {
                return false;
            }
            
            // Handle single date filter
            if (isset($filters['date'])) {
                $filterDate = Carbon::parse($filters['date'])->format('ymd');
                if ($fileDate !== $filterDate) {
                    return false;
                }
            }
            
            // Handle date range filters
            if (isset($filters['dateStart']) || isset($filters['dateEnd'])) {
                // Parse YYMMDD format: 251126 = 2025-11-26
                $year = 2000 + intval(substr($fileDate, 0, 2));
                $month = intval(substr($fileDate, 2, 2));
                $day = intval(substr($fileDate, 4, 2));
                $fileDateCarbon = Carbon::create($year, $month, $day);
                
                if (isset($filters['dateStart'])) {
                    $startDate = Carbon::parse($filters['dateStart']);
                    if ($fileDateCarbon->lt($startDate)) {
                        return false;
                    }
                }
                
                if (isset($filters['dateEnd'])) {
                    $endDate = Carbon::parse($filters['dateEnd']);
                    if ($fileDateCarbon->gt($endDate)) {
                        return false;
                    }
                }
            }
            
            return true;
        }
        
        return false;
    }

    private function queryDuckDb(array $csvFiles, array $fields, array $filters, $page = 1, $filesPerPage = 50)
    {
        if (empty($csvFiles)) {
            return [];
        }

        // Paginate files to prevent memory issues
        $offset = ($page - 1) * $filesPerPage;
        $csvFiles = array_slice($csvFiles, $offset, $filesPerPage);

        // Get column names from all files and use the one with most columns
        $allColumnNames = [];
        foreach ($csvFiles as $csvFileInfo) {
            $cols = $this->getColumnNames($csvFileInfo['path']);
            if (count($cols) > count($allColumnNames)) {
                $allColumnNames = $cols;
            }
        }
        
        if (empty($allColumnNames)) {
            return ['debug' => 'No columns found'];
        }
        
        // Create UNION ALL query
        $unionQueries = [];
        foreach ($csvFiles as $csvFileInfo) {
            $escapedPath = str_replace('\\', '/', $csvFileInfo['path']);
            $fileColumns = $this->getColumnNames($csvFileInfo['path']);
            $columnCount = count($fileColumns);
            
            // Extract ICAO code from filename
            $fileName = basename($csvFileInfo['path']);
            $icaoCode = 'UNKNOWN';
            if (preg_match('/log_\d{6}_\d{6}_([A-Z]{4})\.csv$/', $fileName, $matches)) {
                $icaoCode = $matches[1];
            }
            
            $columnList = [];
            foreach ($allColumnNames as $i => $name) {
                if ($i < $columnCount) {
                    $columnList[] = "column" . sprintf('%02d', $i) . " AS \"$name\"";
                } else {
                    $columnList[] = "NULL AS \"$name\"";
                }
            }
            $columnList[] = "'" . $csvFileInfo['acReg'] . "' AS \"AcReg\"";
            $columnList[] = "'" . $icaoCode . "' AS \"ICAO\"";
            $unionQueries[] = "SELECT " . implode(', ', $columnList) . " FROM read_csv('$escapedPath', skip=3, header=false, delim=',', quote='\"', ignore_errors=true, null_padding=true)";
        }
        
        $unionQuery = implode(' UNION ALL ', $unionQueries);
        
        $selectClause = empty($fields) ? '*' : implode(', ', array_map(function($field) {
            $fieldMap = [
                'Lcl_Date' => 'Lcl Date',
                'Lcl_Time' => 'Lcl Time',
                'E1_FFlow' => 'E1 FFlow',
                'E1_OilT' => 'E1 OilT',
                'E1_OilP' => 'E1 OilP',
                'E1_Torq' => 'E1 Torq',
                'E1_NP' => 'E1 NP',
                'E1_NG' => 'E1 NG',
                'E1_ITT' => 'E1 ITT'
            ];
            $actualField = isset($fieldMap[$field]) ? $fieldMap[$field] : $field;
            return '"' . trim($actualField) . '"';
        }, $fields));
        
        $dataLimit = env('EDA_DATA_LIMIT', 100);
        $sql = "SELECT $selectClause FROM ($unionQuery) AS combined_data LIMIT $dataLimit;";
        
        $whereConditions = [];
        foreach ($filters as $key => $value) {
            if (!in_array($key, ['dateStart', 'dateEnd', 'acReg', 'icaoCode', 'includeMetadata', 'page']) && !empty($value)) {
                $whereConditions[] = "\"$key\" = '$value'";
            }
        }
        
        if (!empty($whereConditions)) {
            $sql = str_replace(" LIMIT $dataLimit;", ' WHERE ' . implode(' AND ', $whereConditions) . " LIMIT $dataLimit;", $sql);
        }
        
        $tempSqlFile = tempnam(sys_get_temp_dir(), 'duckdb_query') . '.sql';
        $memoryLimit = env('DUCKDB_MEMORY', '12GB');
        $threads = env('DUCKDB_VCPU', 4);
        $fullSql = "PRAGMA memory_limit='$memoryLimit';\nPRAGMA threads=$threads;\n" . $sql;
        file_put_contents($tempSqlFile, $fullSql);
        
        $command = '"' . $this->duckdbPath . '" -json < "' . $tempSqlFile . '"';
        $output = shell_exec($command . ' 2>&1');
        
        unlink($tempSqlFile);
        
        if (empty($output)) {
            return ['debug' => 'Empty output', 'sql' => $sql];
        }
        
        $result = $this->parseDuckDbOutput($output);
        
        // Force garbage collection to free memory
        gc_collect_cycles();
        
        return $result;
    }

    private function parseDuckDbOutput($output)
    {
        if (empty($output)) {
            return ['debug' => 'Empty output'];
        }
        
        if (strpos($output, 'Error') !== false || strpos($output, 'error') !== false) {
            return ['debug' => 'DuckDB Error: ' . $output];
        }
        
        $data = json_decode($output, true);
        
        if ($data === null) {
            return ['debug' => 'JSON parse error: ' . json_last_error_msg(), 'raw' => substr($output, 0, 500)];
        }
        
        return array_map(function($row) {
            return array_map(function($value) {
                if (is_string($value)) {
                    $trimmed = trim($value);
                    return $trimmed === '' ? '' : $trimmed;
                }
                return $value;
            }, $row);
        }, $data);
    }

    private function getColumnNames($csvFile)
    {
        $handle = fopen($csvFile, 'r');
        if (!$handle) {
            return [];
        }
        
        fgets($handle);
        fgets($handle);
        
        $headerLine = fgets($handle);
        fclose($handle);
        
        if (!$headerLine) {
            return [];
        }
        
        $columns = str_getcsv(trim($headerLine));
        return array_map('trim', $columns);
    }
    
    private function extractMetadata($csvFile)
    {
        $handle = fopen($csvFile, 'r');
        if (!$handle) {
            return [];
        }
        
        $firstLine = fgets($handle);
        fclose($handle);
        
        $metadata = [];
        if (preg_match_all('/(\w+)="([^"]+)"/', $firstLine, $matches, PREG_SET_ORDER)) {
            foreach ($matches as $match) {
                $metadata[$match[1]] = $match[2];
            }
        }
        
        return $metadata;
    }

    public function getFilteredFiles(array $filters)
    {
        $folders = $this->getFilteredFolders($filters);
        
        // Debug: Show all files in found folders
        $allFiles = [];
        foreach ($folders as $folder) {
            $files = glob($folder . '\\*.csv');
            foreach ($files as $file) {
                $fileName = basename($file);
                $allFiles[] = [
                    'filename' => $fileName,
                    'matches_pattern' => preg_match('/log_(\d{6})_\d{6}_([A-Z]{4})\.csv$/', $fileName),
                    'matches_filters' => $this->matchesFilters($fileName, $filters)
                ];
            }
        }
        
        $csvFiles = $this->getFilteredCsvFiles($folders, $filters);
        
        return [
            'filters' => $filters,
            'folders_found' => array_map('basename', $folders),
            'all_files_in_folders' => $allFiles,
            'total_files' => count($csvFiles),
            'files' => array_map(function($file) {
                return [
                    'path' => $file['path'],
                    'filename' => basename($file['path']),
                    'acReg' => $file['acReg']
                ];
            }, $csvFiles)
        ];
    }

    public function getTorqueLimitData(array $filters, $torqueLimit)
    {
        error_log('getTorqueLimitData called with filters: ' . json_encode($filters) . ', torqueLimit: ' . $torqueLimit);
        
        $folders = $this->getFilteredFolders($filters);
        error_log('Found folders: ' . json_encode(array_map('basename', $folders)));
        
        // Debug: List all folders to see actual structure
        $allFolders = glob($this->edaFilesPath . '\\*', GLOB_ONLYDIR);
        error_log('All available folders: ' . json_encode(array_map('basename', $allFolders)));
        
        $csvFiles = $this->getFilteredCsvFiles($folders, $filters);
        error_log('Found CSV files: ' . count($csvFiles) . ' files');
        error_log('CSV file paths: ' . json_encode(array_column($csvFiles, 'path')));
        
        if (empty($csvFiles)) {
            error_log('No CSV files found, returning empty array');
            return [];
        }

        $result = $this->calculateOverlimitEvents($csvFiles, $torqueLimit);
        error_log('Final result: ' . json_encode($result));
        
        return $result;
    }
    
    private function calculateOverlimitEvents($csvFiles, $torqueLimit)
    {
        $results = [];
        $overlimitDetails = [];
        
        foreach ($csvFiles as $csvFileInfo) {
            $acReg = $csvFileInfo['acReg'];
            
            // Extract ICAO from filename
            $fileName = basename($csvFileInfo['path']);
            $icaoCode = 'UNKNOWN';
            if (preg_match('/log_\d{6}_\d{6}_([A-Z]{4})\.csv$/', $fileName, $matches)) {
                $icaoCode = $matches[1];
            }
            
            if (!isset($results[$acReg])) {
                $results[$acReg] = [
                    'AcReg' => $acReg,
                    'torque_limit' => $torqueLimit,
                    'total_overlimit_events' => 0,
                    'total_overlimit_duration' => '00:00'
                ];
            }
            
            $fileData = $this->getFileOverlimitEvents($csvFileInfo['path'], $torqueLimit, $acReg, $icaoCode);
            $results[$acReg]['total_overlimit_events'] += $fileData['events'];
            $results[$acReg]['total_overlimit_duration'] = $this->addDurations(
                $results[$acReg]['total_overlimit_duration'], 
                $fileData['duration']
            );
            
            // Collect overlimit details
            $overlimitDetails = array_merge($overlimitDetails, $fileData['details']);
        }
        
        return [
            'summary' => array_values($results),
            'overlimit_details' => $overlimitDetails
        ];
    }
    
    private function getFileOverlimitEvents($filePath, $limit, $acReg, $icaoCode)
    {
        $handle = fopen($filePath, 'r');
        if (!$handle) return ['events' => 0, 'duration' => '00:00', 'details' => []];
        
        // Skip metadata and get headers
        fgets($handle); fgets($handle);
        $headerLine = fgets($handle);
        $headers = str_getcsv(trim($headerLine));
        
        // Find column indices
        $torqueColumnIndex = -1;
        $dateColumnIndex = -1;
        $timeColumnIndex = -1;
        
        foreach ($headers as $index => $header) {
            $header = trim($header);
            if ($header === 'E1 Torq') $torqueColumnIndex = $index;
            if ($header === 'Lcl Date') $dateColumnIndex = $index;
            if ($header === 'Lcl Time') $timeColumnIndex = $index;
        }
        
        if ($torqueColumnIndex === -1 || $dateColumnIndex === -1 || $timeColumnIndex === -1) {
            fclose($handle);
            return ['events' => 0, 'duration' => '00:00', 'details' => []];
        }
        
        $events = 0;
        $totalSeconds = 0;
        $inOverlimit = false;
        $overlimitStartTime = null;
        $overlimitDetails = [];
        $rowCount = 0;
        $maxRows = env('EDA_DATA_LIMIT', 5000);
        
        while (($line = fgets($handle)) !== false && $rowCount < $maxRows) {
            $data = str_getcsv($line);
            if (count($data) <= max($torqueColumnIndex, $dateColumnIndex, $timeColumnIndex)) continue;
            
            $torque = floatval(trim($data[$torqueColumnIndex]));
            $date = trim($data[$dateColumnIndex]);
            $time = trim($data[$timeColumnIndex]);
            
            try {
                $currentTime = Carbon::createFromFormat('Y-m-d H:i:s', $date . ' ' . $time);
            } catch (Exception $e) {
                continue;
            }
            
            if ($torque > $limit && !$inOverlimit) {
                // Start of overlimit event - collect this data point
                $overlimitDetails[] = [
                    'date' => $date,
                    'time' => $time,
                    'acReg' => $acReg,
                    'icao' => $icaoCode,
                    'torque' => $torque,
                    'limit' => $limit
                ];
                
                $inOverlimit = true;
                $overlimitStartTime = $currentTime;
                $events++;
            } elseif ($torque <= $limit && $inOverlimit) {
                // End of overlimit event
                $inOverlimit = false;
                if ($overlimitStartTime) {
                    $duration = $currentTime->diffInSeconds($overlimitStartTime);
                    $totalSeconds += $duration;
                }
            }
            
            $rowCount++;
        }
        
        fclose($handle);
        
        $totalMinutes = intval($totalSeconds / 60);
        $hours = intval($totalMinutes / 60);
        $minutes = $totalMinutes % 60;
        $duration = sprintf('%02d:%02d', $hours, $minutes);
        
        return ['events' => $events, 'duration' => $duration, 'details' => $overlimitDetails];
    }
    
    private function addDurations($duration1, $duration2)
    {
        list($h1, $m1) = explode(':', $duration1);
        list($h2, $m2) = explode(':', $duration2);
        
        $totalMinutes = ($h1 * 60 + $m1) + ($h2 * 60 + $m2);
        $hours = intval($totalMinutes / 60);
        $minutes = $totalMinutes % 60;
        
        return sprintf('%02d:%02d', $hours, $minutes);
    }

    public function getTorqueLimitChart(array $filters, $torqueLimit)
    {
        $folders = $this->getFilteredFolders($filters);
        $csvFiles = $this->getFilteredCsvFiles($folders, $filters);
        
        if (empty($csvFiles)) {
            return [];
        }

        $sql = $this->buildTorqueChartQuery($csvFiles, $torqueLimit);
        $result = $this->executeDuckDbQuery($sql);
        
        return $result;
    }

    private function buildTorqueLimitQuery($csvFiles, $torqueLimit)
    {
        // Sample files from each aircraft to ensure all are represented
        $filesByAircraft = [];
        foreach ($csvFiles as $file) {
            $acReg = $file['acReg'];
            if (!isset($filesByAircraft[$acReg])) {
                $filesByAircraft[$acReg] = [];
            }
            $filesByAircraft[$acReg][] = $file;
        }
        
        // Take up to 5 files per aircraft, max 100 total
        $sampledFiles = [];
        foreach ($filesByAircraft as $files) {
            $sampledFiles = array_merge($sampledFiles, array_slice($files, 0, 5));
            if (count($sampledFiles) >= 100) break;
        }
        $csvFiles = array_slice($sampledFiles, 0, 100);
        
        $allColumnNames = [];
        foreach ($csvFiles as $csvFileInfo) {
            $cols = $this->getColumnNames($csvFileInfo['path']);
            if (count($cols) > count($allColumnNames)) {
                $allColumnNames = $cols;
            }
        }

        $unionQueries = [];
        foreach ($csvFiles as $csvFileInfo) {
            $escapedPath = str_replace('\\', '/', $csvFileInfo['path']);
            $fileColumns = $this->getColumnNames($csvFileInfo['path']);
            $columnCount = count($fileColumns);
            
            $columnList = [];
            foreach ($allColumnNames as $i => $name) {
                if ($i < $columnCount) {
                    $columnList[] = "column" . sprintf('%02d', $i) . " AS \"$name\"";
                } else {
                    $columnList[] = "NULL AS \"$name\"";
                }
            }
            $columnList[] = "'" . $csvFileInfo['acReg'] . "' AS \"AcReg\"";
            $unionQueries[] = "SELECT " . implode(', ', $columnList) . " FROM read_csv('$escapedPath', skip=3, header=false, delim=',', quote='\"', ignore_errors=true, null_padding=true)";
        }
        
        $unionQuery = implode(' UNION ALL ', $unionQueries);
        
        // Build CASE statement for per-aircraft limits
        $generalLimit = isset($torqueLimit['general']) ? $torqueLimit['general'] : 100;
        $caseConditions = [];
        foreach ($torqueLimit as $acReg => $limit) {
            if ($acReg !== 'general') {
                $caseConditions[] = "WHEN \"AcReg\" = '$acReg' THEN $limit";
            }
        }
        $limitCase = empty($caseConditions) 
            ? $generalLimit 
            : "CASE " . implode(' ', $caseConditions) . " ELSE $generalLimit END";
        
        return "SELECT \"AcReg\", 
                $limitCase as torque_limit,
                COUNT(*) as total_overlimit,
                ROUND(COUNT(*) / 60.0, 2) as total_overlimit_minutes
                FROM ($unionQuery) AS data
                WHERE TRY_CAST(\"E1 Torq\" AS DOUBLE) > $limitCase
                GROUP BY \"AcReg\"";
    }

    private function buildTorqueChartQuery($csvFiles, $torqueLimit)
    {
        // For chart queries, process all files from the specific aircraft folder
        // No artificial limit since we're targeting specific acReg + date range
        // $csvFiles = array_slice($csvFiles, 0, 10); // Removed limit
        $allColumnNames = [];
        foreach ($csvFiles as $csvFileInfo) {
            $cols = $this->getColumnNames($csvFileInfo['path']);
            if (count($cols) > count($allColumnNames)) {
                $allColumnNames = $cols;
            }
        }

        $unionQueries = [];
        foreach ($csvFiles as $csvFileInfo) {
            $escapedPath = str_replace('\\', '/', $csvFileInfo['path']);
            $fileColumns = $this->getColumnNames($csvFileInfo['path']);
            $columnCount = count($fileColumns);
            
            $columnList = [];
            foreach ($allColumnNames as $i => $name) {
                if ($i < $columnCount) {
                    $columnList[] = "column" . sprintf('%02d', $i) . " AS \"$name\"";
                } else {
                    $columnList[] = "NULL AS \"$name\"";
                }
            }
            $columnList[] = "'" . $csvFileInfo['acReg'] . "' AS \"AcReg\"";
            $unionQueries[] = "SELECT " . implode(', ', $columnList) . " FROM read_csv('$escapedPath', skip=3, header=false, delim=',', quote='\"', ignore_errors=true, null_padding=true)";
        }
        
        $unionQuery = implode(' UNION ALL ', $unionQueries);
        
        // Build CASE statement for per-aircraft limits
        $generalLimit = is_array($torqueLimit) && isset($torqueLimit['general']) ? $torqueLimit['general'] : (is_numeric($torqueLimit) ? $torqueLimit : 100);
        $caseConditions = [];
        if (is_array($torqueLimit)) {
            foreach ($torqueLimit as $acReg => $limit) {
                if ($acReg !== 'general') {
                    $caseConditions[] = "WHEN \"AcReg\" = '$acReg' THEN $limit";
                }
            }
        }
        $limitCase = empty($caseConditions) 
            ? $generalLimit 
            : "CASE " . implode(' ', $caseConditions) . " ELSE $generalLimit END";
        
        $whereClause = "WHERE TRY_CAST(\"E1 Torq\" AS DOUBLE) IS NOT NULL";
        
        $dataLimit = env('EDA_DATA_LIMIT', 2000);
        
        return "SELECT \"AcReg\", 
                \"Lcl Date\" as date,
                \"Lcl Time\" as time,
                TRY_CAST(\"E1 Torq\" AS DOUBLE) as torque,
                $limitCase as torque_limit
                FROM (
                    SELECT *, ROW_NUMBER() OVER (PARTITION BY \"Lcl Date\" ORDER BY \"Lcl Time\") as rn
                    FROM ($unionQuery) AS data
                    $whereClause
                ) ranked
                WHERE rn <= $dataLimit
                ORDER BY \"Lcl Date\", \"Lcl Time\"";
    }

    private function executeDuckDbQuery($sql)
    {
        $tempSqlFile = tempnam(sys_get_temp_dir(), 'duckdb_query') . '.sql';
        $memoryLimit = env('DUCKDB_MEMORY', '12GB');
        $threads = env('DUCKDB_VCPU', 4);
        $fullSql = "PRAGMA memory_limit='$memoryLimit';\nPRAGMA threads=$threads;\n" . $sql;
        file_put_contents($tempSqlFile, $fullSql);
        
        $command = '"' . $this->duckdbPath . '" -json < "' . $tempSqlFile . '"';
        $output = shell_exec($command . ' 2>&1');
        
        unlink($tempSqlFile);
        
        if (empty($output)) {
            return ['debug' => 'Empty output', 'sql' => $sql];
        }
        
        $result = $this->parseDuckDbOutput($output);
        
        // Force garbage collection to free memory
        gc_collect_cycles();
        
        return $result;
    }
}
