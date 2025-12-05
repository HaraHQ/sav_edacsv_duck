<?php

namespace App\Console\Commands;

use App\Jobs\ProcessEdaFileJob;
use App\Services\RedisQueueService;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\Log;

class ProcessEdaQueue extends Command
{
    protected $signature = 'eda:queue-worker';
    protected $description = 'Process EDA file upload queue';

    private $queueService;

    public function __construct(RedisQueueService $queueService)
    {
        parent::__construct();
        $this->queueService = $queueService;
    }

    public function handle()
    {
        $this->info('Starting EDA queue worker...');

        while (true) {
            try {
                // Pop job from queue (blocking)
                $jobData = $this->queueService->popJob();
                
                if ($jobData) {
                    $this->info("Processing job: {$jobData['id']}");
                    
                    // Create and handle job
                    $job = new ProcessEdaFileJob(
                        $jobData['zip_file_path'],
                        $jobData['base_path'],
                        $jobData['id']
                    );
                    
                    $job->handle();
                    
                    $this->info("Job completed: {$jobData['id']}");
                }
                
            } catch (\Exception $e) {
                Log::error('Queue worker error: ' . $e->getMessage());
                $this->error('Error: ' . $e->getMessage());
                sleep(5); // Wait before retrying
            }
        }
    }
}