<?php

namespace App\Jobs;

use Illuminate\Support\Facades\Log;

class ProcessEdaFileJob extends Job
{
    protected $zipFilePath;
    protected $fileName;
    protected $jobId;

    public function __construct($zipFilePath, $fileName, $jobId)
    {
        $this->zipFilePath = $zipFilePath;
        $this->fileName = $fileName;
        $this->jobId = $jobId;
    }

    public function handle()
    {
        try {
            Log::info('Processing EDA file', ['job_id' => $this->jobId, 'file' => $this->fileName]);

            $this->processZipFile();

            Log::info('EDA file processing completed', ['job_id' => $this->jobId]);

            // Cleanup temp file
            if (file_exists($this->zipFilePath)) {
                unlink($this->zipFilePath);
            }

        } catch (\Exception $e) {
            Log::error('EDA file processing failed', [
                'job_id' => $this->jobId,
                'error' => $e->getMessage(),
                'file' => $this->fileName
            ]);

            // Cleanup temp file on error
            if (file_exists($this->zipFilePath)) {
                unlink($this->zipFilePath);
            }

            throw $e;
        }
    }

    private function processZipFile()
    {
        $basePath = env('EDA_FILES_PATH');
        if (!$basePath) {
            throw new \Exception('EDA_FILES_PATH not configured');
        }

        $zip = new \ZipArchive();
        if ($zip->open($this->zipFilePath) !== TRUE) {
            throw new \Exception('Cannot open zip file');
        }

        // Extract directly to EDA_FILES_PATH
        if (!$zip->extractTo($basePath)) {
            $zip->close();
            throw new \Exception('Cannot extract zip file');
        }

        $zip->close();

        Log::info('Files extracted successfully', [
            'job_id' => $this->jobId, 
            'path' => $basePath,
            'file' => $this->fileName
        ]);
    }
}