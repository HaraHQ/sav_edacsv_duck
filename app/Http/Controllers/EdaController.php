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

            // Save file to storage/files
            $filesDir = storage_path('files');
            if (!is_dir($filesDir)) {
                mkdir($filesDir, 0755, true);
            }
            
            $savedFileName = uniqid('eda_') . '_' . $fileName;
            $filePath = $filesDir . DIRECTORY_SEPARATOR . $savedFileName;
            $file->move($filesDir, $savedFileName);

            // Create job ID
            $jobId = uniqid('job_');
            
            // Create job JSON for queue processor
            $queueDir = storage_path('queue');
            if (!is_dir($queueDir)) {
                mkdir($queueDir, 0755, true);
            }
            
            $jobData = [
                'id' => $jobId,
                'file_name' => $fileName,
                'file_path' => $filePath,
                'status' => 'pending',
                'created_at' => date('Y-m-d H:i:s')
            ];
            
            file_put_contents(
                $queueDir . DIRECTORY_SEPARATOR . $jobId . '.json',
                json_encode($jobData, JSON_PRETTY_PRINT)
            );
            
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
            $path = $dir . DIRECTORY_SEPARATOR . $file;
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
            $originalFilters = $filters; // Keep original for result filtering
            
            // Adjust dateStart by subtracting 1 day to account for timezone overlaps
            if (isset($filters['dateStart'])) {
                $originalDate = \Carbon\Carbon::parse($filters['dateStart']);
                $adjustedDate = $originalDate->subDay();
                $filters['dateStart'] = $adjustedDate->format('Y-m-d');
            }
            
            $result = $this->edaService->getTorqueLimitData($filters, $torqueLimit, $originalFilters);

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

    public function engineRpmLimitData(Request $request)
    {
        try {
            $rpmLimit = $request->input('rpmLimit');
            if (!$rpmLimit) {
                return response()->json([
                    'success' => false,
                    'error' => 'rpmLimit is required'
                ], 400);
            }

            $filters = $request->except(['rpmLimit']);
            $originalFilters = $filters;
            
            if (isset($filters['dateStart'])) {
                $originalDate = \Carbon\Carbon::parse($filters['dateStart']);
                $adjustedDate = $originalDate->subDay();
                $filters['dateStart'] = $adjustedDate->format('Y-m-d');
            }
            
            $result = $this->edaService->getEngineRpmLimitData($filters, $rpmLimit, $originalFilters);

            return response()->json([
                'success' => true,
                'data' => $result,
                'rpmLimit' => $rpmLimit
            ]);
        } catch (\Exception $e) {
            return response()->json([
                'success' => false,
                'error' => $e->getMessage()
            ], 500);
        }
    }

    public function engineGasLimitData(Request $request)
    {
        try {
            $percentageLimit = $request->input('percentageLimit');
            if (!$percentageLimit) {
                return response()->json([
                    'success' => false,
                    'error' => 'percentageLimit is required'
                ], 400);
            }

            $filters = $request->except(['percentageLimit']);
            $originalFilters = $filters;
            
            if (isset($filters['dateStart'])) {
                $originalDate = \Carbon\Carbon::parse($filters['dateStart']);
                $adjustedDate = $originalDate->subDay();
                $filters['dateStart'] = $adjustedDate->format('Y-m-d');
            }
            
            $result = $this->edaService->getEngineGasLimitData($filters, $percentageLimit, $originalFilters);

            return response()->json([
                'success' => true,
                'data' => $result,
                'percentageLimit' => $percentageLimit
            ]);
        } catch (\Exception $e) {
            return response()->json([
                'success' => false,
                'error' => $e->getMessage()
            ], 500);
        }
    }

    public function classifyPhases(Request $request)
    {
        try {
            $scriptPath = base_path('classify_phases_cron.php');
            
            if (!file_exists($scriptPath)) {
                return response()->json([
                    'success' => false,
                    'error' => 'Classification script not found'
                ], 404);
            }

            // Execute in background
            $command = 'php "' . $scriptPath . '" > NUL 2>&1 &';
            exec($command);

            return response()->json([
                'success' => true,
                'message' => 'Phase classification started in background'
            ]);
        } catch (\Exception $e) {
            return response()->json([
                'success' => false,
                'error' => $e->getMessage()
            ], 500);
        }
    }

    public function classifyPhasesStatus(Request $request)
    {
        try {
            $logFile = storage_path('logs/phase_classification.log');
            
            if (!file_exists($logFile)) {
                return response()->json([
                    'success' => true,
                    'status' => 'No classification runs yet',
                    'log' => []
                ]);
            }

            // Read last 50 lines
            $lines = file($logFile);
            $lastLines = array_slice($lines, -50);

            return response()->json([
                'success' => true,
                'log' => $lastLines
            ]);
        } catch (\Exception $e) {
            return response()->json([
                'success' => false,
                'error' => $e->getMessage()
            ], 500);
        }
    }
}
