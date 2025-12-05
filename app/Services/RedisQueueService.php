<?php

namespace App\Services;

use Illuminate\Support\Str;

class RedisQueueService
{
    private $redis;

    public function __construct()
    {
        $this->redis = app('redis');
    }

    public function pushJob($zipFilePath, $basePath)
    {
        $jobId = Str::uuid()->toString();
        
        // Create job data
        $jobData = [
            'id' => $jobId,
            'zip_file_path' => $zipFilePath,
            'base_path' => $basePath,
            'status' => 'queued',
            'created_at' => now()->toISOString()
        ];

        // Store job details in Redis hash
        $this->redis->hmset("eda_job:{$jobId}", $jobData);
        
        // Push job to queue
        $this->redis->lpush('eda_queue', json_encode($jobData));

        return $jobId;
    }

    public function getJobStatus($jobId)
    {
        return $this->redis->hgetall("eda_job:{$jobId}");
    }

    public function popJob()
    {
        $jobJson = $this->redis->brpop(['eda_queue'], 0)[1] ?? null;
        return $jobJson ? json_decode($jobJson, true) : null;
    }
}