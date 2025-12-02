<?php

namespace App\Http\Middleware;

use Closure;
use Exception;

class JwtMiddleware
{
    public function handle($request, Closure $next)
    {
        // Skip JWT validation if APP_DEBUG is true
        if (env('APP_DEBUG', false)) {
            return $next($request);
        }
        
        $token = $request->bearerToken() ?: $request->header('Authorization');
        
        if (!$token) {
            return response()->json(['error' => 'Token required'], 401);
        }
        
        // Remove 'Bearer ' prefix if present
        $token = str_replace('Bearer ', '', $token);
        
        try {
            $this->validateJwt($token, env('JWT_SECRET'));
            return $next($request);
        } catch (Exception $e) {
            return response()->json(['error' => 'Invalid or expired token'], 401);
        }
    }
    
    private function validateJwt($token, $secret)
    {
        $parts = explode('.', $token);
        if (count($parts) !== 3) {
            throw new Exception('Invalid token format');
        }
        
        [$header, $payload, $signature] = $parts;
        
        // Verify signature
        $validSignature = $this->base64UrlEncode(hash_hmac('sha256', "$header.$payload", $secret, true));
        if (!hash_equals($signature, $validSignature)) {
            throw new Exception('Invalid signature');
        }
        
        // Check expiration
        $payloadData = json_decode($this->base64UrlDecode($payload), true);
        if (isset($payloadData['exp']) && $payloadData['exp'] < time()) {
            throw new Exception('Token expired');
        }
    }
    
    private function base64UrlDecode($data)
    {
        return base64_decode(str_pad(strtr($data, '-_', '+/'), strlen($data) % 4, '=', STR_PAD_RIGHT));
    }
    
    private function base64UrlEncode($data)
    {
        return rtrim(strtr(base64_encode($data), '+/', '-_'), '=');
    }
}