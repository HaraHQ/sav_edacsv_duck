<?php

namespace App\Models;

class ProcessJob
{
    public static function create($fileName, $status = 'created')
    {
        $jobId = uniqid('job_');
        $job = [
            'id' => $jobId,
            'fileName' => $fileName,
            'status' => $status,
            'created_at' => date('Y-m-d H:i:s'),
            'updated_at' => date('Y-m-d H:i:s')
        ];
        
        $jobsFile = storage_path('jobs.json');
        $jobs = self::getAll();
        $jobs[$jobId] = $job;
        
        file_put_contents($jobsFile, json_encode($jobs, JSON_PRETTY_PRINT));
        return $jobId;
    }
    
    public static function updateStatus($jobId, $status)
    {
        $jobs = self::getAll();
        if (isset($jobs[$jobId])) {
            $jobs[$jobId]['status'] = $status;
            $jobs[$jobId]['updated_at'] = date('Y-m-d H:i:s');
            
            $jobsFile = storage_path('jobs.json');
            file_put_contents($jobsFile, json_encode($jobs, JSON_PRETTY_PRINT));
        }
    }
    
    public static function getAll()
    {
        $jobsFile = storage_path('jobs.json');
        if (!file_exists($jobsFile)) {
            return [];
        }
        
        $content = file_get_contents($jobsFile);
        return json_decode($content, true) ?: [];
    }
    
    public static function getStatusCounts()
    {
        $jobs = self::getAll();
        $counts = ['created' => 0, 'success' => 0, 'failed' => 0];
        
        foreach ($jobs as $job) {
            if (isset($counts[$job['status']])) {
                $counts[$job['status']]++;
            }
        }
        
        return $counts;
    }
}