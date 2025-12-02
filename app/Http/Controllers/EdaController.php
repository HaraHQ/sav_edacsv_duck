<?php

namespace App\Http\Controllers;

use App\Services\EdaService;
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
}