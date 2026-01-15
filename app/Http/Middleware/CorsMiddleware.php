<?php

namespace App\Http\Middleware;

use Closure;

class CorsMiddleware
{
    public function handle($request, Closure $next)
    {
        $allowedOrigins = env('CORS_ALLOWED_ORIGINS', '*');
        
        // Convert comma-separated string to array
        if ($allowedOrigins !== '*') {
            $originsArray = array_map('trim', explode(',', $allowedOrigins));
            $origin = $request->header('Origin');
            
            if (in_array($origin, $originsArray)) {
                $allowedOrigins = $origin;
            } else {
                $allowedOrigins = $originsArray[0] ?? '*';
            }
        }

        $headers = [
            'Access-Control-Allow-Origin' => $allowedOrigins,
            'Access-Control-Allow-Methods' => 'GET, POST, PUT, DELETE, OPTIONS',
            'Access-Control-Allow-Headers' => 'Content-Type, Authorization, X-Requested-With',
            'Access-Control-Allow-Credentials' => 'true',
            'Access-Control-Max-Age' => '86400',
        ];

        if ($request->isMethod('OPTIONS')) {
            return response()->json(['status' => 'OK'], 200, $headers);
        }

        $response = $next($request);

        foreach ($headers as $key => $value) {
            $response->header($key, $value);
        }

        return $response;
    }
}
