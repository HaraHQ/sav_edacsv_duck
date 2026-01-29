<?php

namespace App\Http\Controllers;

use App\Services\EdaServiceV2;
use Illuminate\Http\Request;
use Laravel\Lumen\Routing\Controller as BaseController;

class EdaV2Controller extends BaseController
{
    private $edaService;

    public function __construct(EdaServiceV2 $edaService)
    {
        $this->edaService = $edaService;
    }

    public function torqueLimitByAfml(Request $request)
    {
        try {
            $acReg = $request->input('acReg');
            $dateStart = $request->input('dateStart');
            $dateEnd = $request->input('dateEnd');
            $torqueLimit = $request->input('torqueLimit');
            $withEmpty = $request->input('withEmpty', false);

            if (!$acReg || !$dateStart || !$dateEnd || !$torqueLimit) {
                return response()->json([
                    'success' => false,
                    'error' => 'acReg, dateStart, dateEnd, and torqueLimit are required'
                ], 400);
            }

            $result = $this->edaService->getTorqueLimitByAfml($acReg, $dateStart, $dateEnd, $torqueLimit, $withEmpty);

            return response()->json([
                'success' => true,
                'data' => $result
            ]);
        } catch (\Exception $e) {
            error_log('EdaV2Controller error: ' . $e->getMessage() . ' in ' . $e->getFile() . ':' . $e->getLine());
            
            return response()->json([
                'success' => false,
                'error' => $e->getMessage()
            ], 500);
        }
    }
}
