<?php

namespace App\Console\Commands;

use Illuminate\Console\Command;
use Illuminate\Support\Facades\Log;

class ProcessEdaFileCommand extends Command
{
    protected $signature = 'process-eda-file {zipPath} {fileName} {jobId}';
    protected $description = 'Process EDA file in background';

    public function handle()
    {
        $zipPath = $this->argument('zipPath');
        $fileName = $this->argument('fileName');
        $jobId = $this->argument('jobId');

        try {
            Log::info('Processing EDA file', ['job_id' => $jobId, 'file' => $fileName]);

            $this->processZipFile($zipPath);

            Log::info('EDA file processing completed', ['job_id' => $jobId]);

            if (file_exists($zipPath)) {
                unlink($zipPath);
            }

        } catch (\Exception $e) {
            Log::error('EDA file processing failed', [
                'job_id' => $jobId,
                'error' => $e->getMessage(),
                'file' => $fileName
            ]);

            if (file_exists($zipPath)) {
                unlink($zipPath);
            }
        }
    }

    private function processZipFile($zipPath)
    {
        $basePath = env('EDA_FILES_PATH');
        if (!$basePath) {
            throw new \Exception('EDA_FILES_PATH not configured');
        }

        $zip = new \ZipArchive();
        if ($zip->open($zipPath) !== TRUE) {
            throw new \Exception('Cannot open zip file');
        }

        if (!$zip->extractTo($basePath)) {
            $zip->close();
            throw new \Exception('Cannot extract zip file');
        }

        $zip->close();
    }
}