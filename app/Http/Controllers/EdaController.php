<?php

namespace App\Http\Controllers;

use App\Services\EdaService;
use App\Models\ProcessJob;
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

    public function jobStatus()
    {
        try {
            $counts = ProcessJob::getStatusCounts();
            
            return response()->json([
                'success' => true,
                'status' => $counts
            ]);
        } catch (\Exception $e) {
            return response()->json([
                'success' => false,
                'error' => $e->getMessage()
            ], 500);
        }
    }

    public function chart(Request $request)
    {
        try {
            $acReg = $request->input('acReg');
            $torqueLimit = $request->input('torqueLimit', 100);
            $filters = $request->except(['torqueLimit']);
            
            error_log('Chart request - acReg: ' . $acReg . ', torqueLimit: ' . $torqueLimit . ', filters: ' . json_encode($filters));
            
            $result = $this->edaService->getTorqueLimitChart($filters, $torqueLimit);
            
            error_log('Chart result count: ' . (is_array($result) ? count($result) : 'not array'));
            
            return response()->json([
                'success' => true,
                'acReg' => $acReg,
                'torqueLimit' => $torqueLimit,
                'data' => $result
            ]);
        } catch (\Exception $e) {
            error_log('Chart error: ' . $e->getMessage() . ' in ' . $e->getFile() . ':' . $e->getLine());
            
            return response()->json([
                'success' => false,
                'error' => $e->getMessage()
            ], 500);
        }
    }
    
    private function processInBackground($jobId, $zipFile, $basePath)
    {
        $command = 'php ' . base_path('artisan') . ' eda:process "' . $jobId . '" "' . $zipFile . '" "' . $basePath . '" > nul 2>&1 &';
        exec($command);
    }

    public function upload(Request $request)
    {
        ini_set('log_errors', 1);
        ini_set('error_log', storage_path('logs/upload_errors.log'));
        ini_set('post_max_size', '256M');
        ini_set('upload_max_filesize', '256M');
        ini_set('memory_limit', '384M');

        $startTime = microtime(true);

        try {
            if (!$request->hasFile('file') && !$request->hasFile('uploadFile')) {
                throw new \Exception('No file uploaded');
            }

            $file = $request->hasFile('file') ? $request->file('file') : $request->file('uploadFile');
            $fileName = $file->getClientOriginalName();

            if (pathinfo($fileName, PATHINFO_EXTENSION) !== 'zip') {
                throw new \Exception('Only ZIP files are allowed');
            }

            // Save file quickly and create job
            $tempFilePath = sys_get_temp_dir() . '\\' . uniqid('eda_upload_') . '.zip';
            $file->move(dirname($tempFilePath), basename($tempFilePath));

            // Create job with status tracking
            $jobId = ProcessJob::create($fileName, 'created');
            
            // Process in background
            $this->processInBackground($jobId, $tempFilePath, env('EDA_FILES_PATH'));
            
            $elapsed = round(microtime(true) - $startTime, 2);

            return response()->json([
                'success' => true,
                'jobId' => $jobId,
                'elapsed' => $elapsed,
                'message' => 'File uploaded successfully, processing in background'
            ]);

        } catch (\Exception $e) {
            error_log('Upload error: ' . $e->getMessage() . ' in ' . $e->getFile() . ':' . $e->getLine());

            return response()->json([
                'success' => false,
                'error' => $e->getMessage()
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

    public function torqueLimitData(Request $request)
    {
        try {
            $torqueLimit = $request->input('torqueLimit');
            if (!$torqueLimit) {
                return response()->json([
                    'success' => false,
                    'error' => 'torqueLimit is required'
                ], 400);
            }

            $filters = $request->except(['torqueLimit']);
            $result = $this->edaService->getTorqueLimitData($filters, $torqueLimit);

            return response()->json([
                'success' => true,
                'data' => $result,
                'torqueLimit' => $torqueLimit
            ]);
        } catch (\Exception $e) {
            return response()->json([
                'success' => false,
                'error' => $e->getMessage()
            ], 500);
        }
    }

    public function testFiles(Request $request)
    {
        try {
            $filters = $request->all();
            $result = $this->edaService->getFilteredFiles($filters);

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

    public function torqueLimitChart(Request $request)
    {
        try {
            $torqueLimit = $request->input('torqueLimit');
            if (!$torqueLimit) {
                return response()->json([
                    'success' => false,
                    'error' => 'torqueLimit is required'
                ], 400);
            }

            // Support both single value and object format
            if (!is_array($torqueLimit)) {
                $torqueLimit = ['general' => $torqueLimit];
            }

            $filters = $request->except(['torqueLimit']);
            $result = $this->edaService->getTorqueLimitChart($filters, $torqueLimit);

            return response()->json([
                'success' => true,
                'data' => $result,
                'torqueLimit' => $torqueLimit
            ]);
        } catch (\Exception $e) {
            return response()->json([
                'success' => false,
                'error' => $e->getMessage()
            ], 500);
        }
    }
}
