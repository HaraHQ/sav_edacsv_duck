<?php

namespace App\Http\Controllers;

use App\Services\EdaService;
use Illuminate\Http\Request;
use Laravel\Lumen\Routing\Controller as BaseController;

class EdaController extends BaseController
{
    private $edaService;

    public function __construct(EdaService $edaService)
    {
        $this->edaService = $edaService;
    }

    public function query(Request $request)
    {
        try {
            $fields = $request->input('fields', []);
            $filters = $request->except(['fields', 'includeMetadata']);
            $includeMetadata = $request->input('includeMetadata', false);
            
            $result = $this->edaService->queryData($fields, $filters, $includeMetadata);
            
            return response()->json([
                'success' => true,
                'result' => $result
            ]);
        } catch (\Exception $e) {
            return response()->json([
                'success' => false,
                'error' => $e->getMessage()
            ], 500);
        }
    }

    public function upload(Request $request)
    {
        // Enable error logging
        ini_set('log_errors', 1);
        ini_set('error_log', storage_path('logs/upload_errors.log'));
        ini_set('post_max_size', '128M');
        ini_set('upload_max_filesize', '128M');
        ini_set('memory_limit', '256M');
        
        $startTime = microtime(true);
        $extractedPath = null;
        
        try {
            if (!$request->hasFile('file')) {
                throw new \Exception('No file uploaded');
            }
            
            $file = $request->file('file');
            $fileName = $file->getClientOriginalName();
            
            // Validate file name format: EDA {aircraft} {DD} {MMM} {YYYY}.zip
            if (!preg_match('/^EDA\s+([A-Z]{2}-[A-Z0-9]+)\s+(\d{1,2}\s+[A-Z]{3}\s+\d{4})\.zip$/i', $fileName, $matches)) {
                throw new \Exception('Invalid file name format. Expected: EDA {AIRCRAFT} {DD} {MMM} {YYYY}.zip');
            }
            
            $folderName = str_replace('.zip', '', $fileName);
            $targetPath = env('EDA_FILES_PATH') . '\\' . $folderName;
            
            // Check if folder already exists
            if (is_dir($targetPath)) {
                throw new \Exception('Folder already exists: ' . $folderName);
            }
            
            // Save uploaded file temporarily using native PHP
            $tempFilePath = sys_get_temp_dir() . '\\' . uniqid('eda_upload_') . '.zip';
            if (!$file->move(dirname($tempFilePath), basename($tempFilePath))) {
                throw new \Exception('Cannot save uploaded file');
            }
            
            // Extract zip file
            $zip = new \ZipArchive();
            if ($zip->open($tempFilePath) !== TRUE) {
                throw new \Exception('Cannot open zip file');
            }
            
            // Check if target parent directory exists and is writable
            $parentDir = dirname($targetPath);
            if (!is_dir($parentDir)) {
                throw new \Exception('Parent directory does not exist: ' . $parentDir);
            }
            if (!is_writable($parentDir)) {
                throw new \Exception('Parent directory not writable: ' . $parentDir);
            }
            
            // Create target directory
            if (!mkdir($targetPath, 0755, true)) {
                throw new \Exception('Cannot create target directory: ' . $targetPath . ' (parent: ' . $parentDir . ')');
            }
            
            $extractedPath = $targetPath;
            
            // Extract to target path
            if (!$zip->extractTo($targetPath)) {
                throw new \Exception('Cannot extract zip file to: ' . $targetPath);
            }
            
            $zip->close();
            unlink($tempFilePath);
            
            $elapsed = round(microtime(true) - $startTime, 2);
            
            return response()->json([
                'success' => true,
                'elapsed' => $elapsed
            ]);
            
        } catch (\Exception $e) {
            // Cleanup on failure
            if ($extractedPath && is_dir($extractedPath)) {
                $this->removeDirectory($extractedPath);
            }
            
            // Log the full error for debugging
            error_log('Upload error: ' . $e->getMessage() . ' in ' . $e->getFile() . ':' . $e->getLine());
            
            return response()->json([
                'success' => false,
                'error' => $e->getMessage(),
                'debug' => [
                    'file' => $e->getFile(),
                    'line' => $e->getLine(),
                    'trace' => $e->getTraceAsString()
                ]
            ], 500);
        }
    }
    
    private function removeDirectory($dir)
    {
        if (!is_dir($dir)) return;
        
        $files = array_diff(scandir($dir), ['.', '..']);
        foreach ($files as $file) {
            $path = $dir . '\\' . $file;
            is_dir($path) ? $this->removeDirectory($path) : unlink($path);
        }
        rmdir($dir);
    }
}