<?php

namespace App\Console\Commands;

use Illuminate\Console\Command;

class ProcessEdaCommand extends Command
{
    protected $signature = 'eda:process {jobId} {zipFile} {basePath}';
    protected $description = 'Process EDA zip file in background';

    public function handle()
    {
        $jobId = $this->argument('jobId');
        $zipFile = $this->argument('zipFile');
        $basePath = $this->argument('basePath');
        
        \App\Models\ProcessJob::updateStatus($jobId, 'processing');
        
        try {
            $zip = new \ZipArchive();
            if ($zip->open($zipFile) !== TRUE) {
                throw new \Exception('Cannot open zip file');
            }
            
            $tempExtractPath = sys_get_temp_dir() . '\\' . uniqid('eda_extract_');
            mkdir($tempExtractPath, 0755, true);
            
            $zip->extractTo($tempExtractPath);
            $zip->close();
            
            $extractedFolders = glob($tempExtractPath . '\\*', GLOB_ONLYDIR);
            foreach ($extractedFolders as $folder) {
                $folderName = basename($folder);
                $targetPath = $basePath . '\\' . $folderName;
                
                if (!is_dir($targetPath)) {
                    mkdir($targetPath, 0755, true);
                }
                
                $csvFiles = glob($folder . '\\*.csv');
                foreach ($csvFiles as $csvFile) {
                    $csvName = basename($csvFile);
                    $targetCsvPath = $targetPath . '\\' . $csvName;
                    
                    if (file_exists($targetCsvPath)) {
                        unlink($targetCsvPath);
                    }
                    
                    rename($csvFile, $targetCsvPath);
                }
            }
            
            $this->removeDirectory($tempExtractPath);
            unlink($zipFile);
            
            \App\Models\ProcessJob::updateStatus($jobId, 'success');
            
        } catch (\Exception $e) {
            error_log('Background EDA processing error: ' . $e->getMessage());
            \App\Models\ProcessJob::updateStatus($jobId, 'failed');
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