<?php

namespace App\Http\Controllers;

use Illuminate\Support\Facades\DB;
use Laravel\Lumen\Routing\Controller as BaseController;

class TestController extends BaseController
{
    public function test()
    {
        // Test database connection
        $dbConnected = false;
        $dbError = null;
        try {
            DB::connection()->getPdo();
            $dbConnected = true;
        } catch (\Exception $e) {
            $dbError = $e->getMessage();
        }

        // Check if CSV files exist
        $edaFilesPath = env('EDA_FILES_PATH');
        $csvFilesExist = false;
        $csvFileCount = 0;
        if ($edaFilesPath && is_dir($edaFilesPath)) {
            $csvFiles = glob($edaFilesPath . '/*/*.csv');
            $csvFileCount = count($csvFiles);
            $csvFilesExist = $csvFileCount > 0;
        }

        // Check DuckDB
        $duckdbPath = env('DUCKDB_PATH');
        $duckdbExists = file_exists($duckdbPath);

        return response()->json([
            'message' => 'EDA API is working',
            'database' => [
                'connected' => $dbConnected,
                'error' => $dbError,
                'host' => env('DB_HOST'),
                'database' => env('DB_DATABASE')
            ],
            'files' => [
                'eda_files_path' => $edaFilesPath,
                'path_exists' => is_dir($edaFilesPath),
                'csv_files_found' => $csvFilesExist,
                'csv_file_count' => $csvFileCount
            ],
            'duckdb' => [
                'path' => $duckdbPath,
                'exists' => $duckdbExists,
                'executable' => $duckdbExists && is_executable($duckdbPath)
            ],
            'php_version' => phpversion(),
            'memory_limit' => ini_get('memory_limit'),
            'max_execution_time' => ini_get('max_execution_time')
        ]);
    }
}