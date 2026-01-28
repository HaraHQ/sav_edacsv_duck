<?php

namespace App\Services;

use Carbon\Carbon;
use Illuminate\Support\Facades\DB;

class EdaServiceV2
{
    private $edaFilesPath;

    public function __construct()
    {
        $this->edaFilesPath = env('EDA_FILES_PATH');
    }

    public function getTorqueLimitByAfml($acReg, $dateStart, $dateEnd, $torqueLimit)
    {
        // Step 1: Get aircraft ID
        $aircraft = DB::table('aircraft')
            ->select('id')
            ->where('reg_code', $acReg)
            ->first();
            
        if (!$aircraft) {
            return ['error' => 'Aircraft not found'];
        }

        // Step 2: Get AFML records for date range
        $afmlRecords = DB::table('afml')
            ->select('id', 'date', 'page_no')
            ->where('aircraft_id', $aircraft->id)
            ->whereBetween('date', [$dateStart, $dateEnd])
            ->orderBy('date')
            ->get();

        if ($afmlRecords->isEmpty()) {
            return ['flights' => []];
        }

        $results = [];

        // Step 3: For each AFML, get flight details
        foreach ($afmlRecords as $afml) {
            $flights = DB::table('afml_detail as ad')
                ->select([
                    'ad.id',
                    'ad.to as takeoff_time',
                    'it_from.code as from_code',
                    'it_from.icao_code as from_icao',
                    'it_to.code as to_code'
                ])
                ->leftJoin('iata as it_from', 'it_from.id', '=', 'ad.iata_id_from')
                ->leftJoin('iata as it_to', 'it_to.id', '=', 'ad.iata_id_to')
                ->where('ad.afml_id', $afml->id)
                ->get();

            // Step 4: For each flight, find matching CSV and calculate torque
            foreach ($flights as $flight) {
                $csvFile = $this->findCsvForFlight($acReg, $afml->date, $flight->takeoff_time, $flight->from_icao);
                
                if ($csvFile) {
                    $torqueData = $this->calculateTorqueForCsv($csvFile, $torqueLimit);
                    
                    if ($torqueData['total_overlimit_events'] > 0) {
                        // Get crew info from AFML
                        $crewInfo = DB::table('afml as a')
                            ->select([
                                'tu_1.full_name as captain',
                                'tu_2.full_name as copilot',
                                'tu_3.full_name as engineer'
                            ])
                            ->leftJoin('tb_user as tu_1', 'tu_1.id', '=', 'a.captain_user_id')
                            ->leftJoin('tb_user as tu_2', 'tu_2.id', '=', 'a.copilot_user_id')
                            ->leftJoin('tb_user as tu_3', 'tu_3.id', '=', 'a.engineer_user_id')
                            ->where('a.id', $afml->id)
                            ->first();
                        
                        $results[] = [
                            'afml_id' => $afml->id,
                            'page_no' => $afml->page_no,
                            'date' => $afml->date,
                            'from' => $flight->from_code,
                            'to' => $flight->to_code,
                            'takeoff_time' => $flight->takeoff_time,
                            'csv_file' => basename($csvFile),
                            'overlimit_events' => $torqueData['total_overlimit_events'],
                            'overlimit_duration' => $torqueData['total_overlimit_duration'],
                            'captain' => $crewInfo->captain ?? '',
                            'copilot' => $crewInfo->copilot ?? '',
                            'engineer' => $crewInfo->engineer ?? '',
                            'details' => $torqueData['details']
                        ];
                    }
                }
            }
        }

        return [
            'acReg' => $acReg,
            'torque_limit' => $torqueLimit,
            'total_flights_with_overlimit' => count($results),
            'flights' => $results
        ];
    }

    private function findCsvForFlight($acReg, $date, $takeoffTime, $icao)
    {
        // Find aircraft folder
        $folders = glob($this->edaFilesPath . '/*', GLOB_ONLYDIR);
        $targetFolder = null;
        
        foreach ($folders as $folder) {
            $folderName = basename($folder);
            if (stripos($folderName, $acReg) !== false) {
                $targetFolder = $folder;
                break;
            }
        }

        if (!$targetFolder) {
            return null;
        }

        // Search for CSV files across ±1 day from AFML date to handle flights spanning multiple days
        $dateCarbon = Carbon::parse($date);
        $datesToSearch = [
            $dateCarbon->copy()->subDay()->format('ymd'),
            $dateCarbon->format('ymd'),
            $dateCarbon->copy()->addDay()->format('ymd')
        ];
        
        foreach ($datesToSearch as $dateStr) {
            $csvFiles = glob($targetFolder . '/log_' . $dateStr . '_*.csv');
            
            foreach ($csvFiles as $csvFile) {
                $fileName = basename($csvFile);
                if (preg_match('/log_\d{6}_(\d{6})_([A-Z]{4})\.csv$/', $fileName, $matches)) {
                    $fileTime = $matches[1];
                    $fileIcao = $matches[2];
                    
                    if ($fileIcao === $icao) {
                        // Check if time is within ±5 minutes
                        $fileHour = intval(substr($fileTime, 0, 2));
                        $fileMin = intval(substr($fileTime, 2, 2));
                        $fileMinutes = $fileHour * 60 + $fileMin;
                        
                        if (abs($fileMinutes - $takeoffTime) <= 5) {
                            return $csvFile;
                        }
                    }
                }
            }
        }

        return null;
    }

    private function calculateTorqueForCsv($filePath, $limit)
    {
        $handle = fopen($filePath, 'r');
        if (!$handle) {
            return ['total_overlimit_events' => 0, 'total_overlimit_duration' => '00:00:00', 'details' => []];
        }

        // Skip metadata and get headers
        fgets($handle); fgets($handle);
        $headerLine = fgets($handle);
        $headers = str_getcsv(trim($headerLine));
        
        $torqueColumnIndex = -1;
        $dateColumnIndex = -1;
        $timeColumnIndex = -1;
        
        foreach ($headers as $index => $header) {
            $header = trim($header);
            if ($header === 'E1 Torq') $torqueColumnIndex = $index;
            if ($header === 'Lcl Date') $dateColumnIndex = $index;
            if ($header === 'Lcl Time') $timeColumnIndex = $index;
        }
        
        if ($torqueColumnIndex === -1) {
            fclose($handle);
            return ['total_overlimit_events' => 0, 'total_overlimit_duration' => '00:00:00', 'details' => []];
        }

        $events = 0;
        $totalSeconds = 0;
        $inOverlimit = false;
        $overlimitStartTime = null;
        $details = [];
        
        while (($line = fgets($handle)) !== false) {
            $data = str_getcsv($line);
            if (count($data) <= $torqueColumnIndex) continue;
            
            $torque = floatval(trim($data[$torqueColumnIndex]));
            $date = $dateColumnIndex >= 0 && isset($data[$dateColumnIndex]) ? trim($data[$dateColumnIndex]) : '';
            $time = $timeColumnIndex >= 0 && isset($data[$timeColumnIndex]) ? trim($data[$timeColumnIndex]) : '';
            
            try {
                $currentTime = Carbon::parse($date . ' ' . $time);
            } catch (\Exception $e) {
                continue;
            }
            
            if ($torque > $limit && !$inOverlimit) {
                $inOverlimit = true;
                $overlimitStartTime = $currentTime;
                $events++;
            } elseif ($torque <= $limit && $inOverlimit) {
                $inOverlimit = false;
                if ($overlimitStartTime) {
                    $duration = $currentTime->diffInSeconds($overlimitStartTime);
                    $totalSeconds += $duration;
                    
                    $hours = intval($duration / 3600);
                    $minutes = intval(($duration % 3600) / 60);
                    $seconds = $duration % 60;
                    
                    $details[] = [
                        'start_time' => $overlimitStartTime->format('Y-m-d H:i:s'),
                        'end_time' => $currentTime->format('Y-m-d H:i:s'),
                        'duration' => sprintf('%02d:%02d:%02d', $hours, $minutes, $seconds)
                    ];
                }
            }
        }
        
        fclose($handle);
        
        $hours = intval($totalSeconds / 3600);
        $minutes = intval(($totalSeconds % 3600) / 60);
        $seconds = $totalSeconds % 60;
        
        return [
            'total_overlimit_events' => $events,
            'total_overlimit_duration' => sprintf('%02d:%02d:%02d', $hours, $minutes, $seconds),
            'details' => $details
        ];
    }
}
