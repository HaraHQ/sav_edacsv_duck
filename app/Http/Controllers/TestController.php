<?php

namespace App\Http\Controllers;

use Laravel\Lumen\Routing\Controller as BaseController;

class TestController extends BaseController
{
    public function test()
    {
        return response()->json([
            'message' => 'EDA API is working',
            'eda_files_path' => env('EDA_FILES_PATH'),
            'duckdb_path' => env('DUCKDB_PATH'),
            'php_version' => phpversion()
        ]);
    }
}