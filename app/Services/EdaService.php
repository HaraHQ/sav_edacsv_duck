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

        $data = $this->queryDuckDb($csvFiles, $fields, $filters);
        
        if ($includeMetadata && !empty($csvFiles)) {
            return [
                'data' => $data,
                'metadata' => $this->extractMetadata($csvFiles[0]),
                'filters' => $filters
            ];
        }
        
        return $data;
    }

    private function getFilteredFolders(array $filters)
    {
        $folders = glob($this->edaFilesPath . '\\EDA*', GLOB_ONLYDIR);
        
        if (isset($filters['dateStart']) || isset($filters['dateEnd']) || isset($filters['acReg'])) {
            $folders = array_filter($folders, function($folder) use ($filters) {
                $folderName = basename($folder);
                
                // Extract acReg and date from folder name: "EDA PK-SNP 22 NOV 2025"
                if (!preg_match('/EDA\s+([A-Z]{2}-[A-Z0-9]+)\s+(\d{1,2}\s+[A-Z]{3}\s+\d{4})/', $folderName, $matches)) {
                    return false;
                }
                
                $folderAcReg = $matches[1];
                $folderDateStr = $matches[2];
                $folderDate = Carbon::createFromFormat('j M Y', $folderDateStr);
                
                // Filter by acReg
                if (isset($filters['acReg']) && $folderAcReg !== $filters['acReg']) {
                    return false;
                }
                
                // Filter by date range
                if (isset($filters['dateStart'])) {
                    $dateStart = Carbon::parse($filters['dateStart']);
                    if ($folderDate->lt($dateStart)) {
                        return false;
                    }
                }
                
                if (isset($filters['dateEnd'])) {
                    $dateEnd = Carbon::parse($filters['dateEnd'])->addDay()->startOfDay();
                    if ($folderDate->gte($dateEnd)) {
                        return false;
                    }
                }
                
                return true;
            });
        }
        
        return $folders;
    }

    private function getFilteredCsvFiles(array $folders, array $filters)
    {
        $csvFiles = [];
        
        foreach ($folders as $folder) {
            $files = glob($folder . '\\log_*.csv');
            
            foreach ($files as $file) {
                $fileName = basename($file);
                
                // Skip files without ICAO code (ending with ______.csv)
                if (preg_match('/log_\d{6}_\d{6}______\.csv$/', $fileName)) {
                    continue;
                }
                
                // Extract ICAO code from filename: log_251122_082756_WALL.csv
                if (preg_match('/log_\d{6}_\d{6}_([A-Z]{4})\.csv$/', $fileName, $matches)) {
                    $icaoCode = $matches[1];
                    
                    // Filter by ICAO code if specified
                    if (isset($filters['icaoCode']) && $icaoCode !== $filters['icaoCode']) {
                        continue;
                    }
                    
                    $csvFiles[] = $file;
                }
            }
        }
        
        return $csvFiles;
    }

    private function queryDuckDb(array $csvFiles, array $fields, array $filters)
    {
        if (empty($csvFiles)) {
            return [];
        }

        // First, get column names from the first file
        $columnNames = $this->getColumnNames($csvFiles[0]);
        
        // Create UNION ALL query for all CSV files, skipping first 3 lines
        $unionQueries = [];
        foreach ($csvFiles as $csvFile) {
            $escapedPath = str_replace('\\', '/', $csvFile);
            $columnList = implode(', ', array_map(function($i, $name) {
                return "column" . sprintf('%02d', $i) . " AS \"$name\"";
            }, array_keys($columnNames), $columnNames));
            $unionQueries[] = "SELECT $columnList FROM read_csv('$escapedPath', skip=3, header=false, delim=',', quote='\"', ignore_errors=true, null_padding=true)";
        }
        
        $unionQuery = implode(' UNION ALL ', $unionQueries);
        
        // Build SELECT clause - use exact column names from CSV
        $selectClause = empty($fields) ? '*' : implode(', ', array_map(function($field) {
            // Map common field name variations
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
        
        $sql = "SELECT $selectClause FROM ($unionQuery) AS combined_data LIMIT 100;";
        
        // Add WHERE clause for additional field-based filters
        $whereConditions = [];
        foreach ($filters as $key => $value) {
            if (!in_array($key, ['dateStart', 'dateEnd', 'acReg', 'icaoCode', 'includeMetadata']) && !empty($value)) {
                $whereConditions[] = "\"$key\" = '$value'";
            }
        }
        
        if (!empty($whereConditions)) {
            $sql = str_replace(' LIMIT 100;', ' WHERE ' . implode(' AND ', $whereConditions) . ' LIMIT 100;', $sql);
        }
        
        // Execute DuckDB query with JSON output using temp file
        $tempSqlFile = tempnam(sys_get_temp_dir(), 'duckdb_query') . '.sql';
        file_put_contents($tempSqlFile, $sql);
        
        $command = '"' . $this->duckdbPath . '" -json < "' . $tempSqlFile . '"';
        $output = shell_exec($command . ' 2>&1');
        
        unlink($tempSqlFile);
        
        // Add debug info
        if (empty($output)) {
            return ['debug' => 'Empty output', 'sql' => $sql];
        }
        
        return $this->parseDuckDbOutput($output);
    }

    private function parseDuckDbOutput($output)
    {
        if (empty($output)) {
            return ['debug' => 'Empty output'];
        }
        
        // Check for errors first
        if (strpos($output, 'Error') !== false || strpos($output, 'error') !== false) {
            return ['debug' => 'DuckDB Error: ' . $output];
        }
        
        // DuckDB JSON output is array format, parse directly
        $data = json_decode($output, true);
        
        if ($data === null) {
            return ['debug' => 'JSON parse error: ' . json_last_error_msg(), 'raw' => substr($output, 0, 500)];
        }
        
        // Clean up data - trim whitespace and convert empty strings
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
        
        // Skip first 2 lines (metadata and data types)
        fgets($handle);
        fgets($handle);
        
        // Third line contains column names
        $headerLine = fgets($handle);
        fclose($handle);
        
        if (!$headerLine) {
            return [];
        }
        
        // Parse column names, handling spaces and special characters
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
}