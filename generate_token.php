<?php

function createJwtToken($secret, $expirationMinutes = 30) {
    $header = json_encode(['typ' => 'JWT', 'alg' => 'HS256']);
    $payload = json_encode(['exp' => time() + ($expirationMinutes * 60)]);
    
    $headerEncoded = rtrim(strtr(base64_encode($header), '+/', '-_'), '=');
    $payloadEncoded = rtrim(strtr(base64_encode($payload), '+/', '-_'), '=');
    
    $signature = hash_hmac('sha256', "$headerEncoded.$payloadEncoded", $secret, true);
    $signatureEncoded = rtrim(strtr(base64_encode($signature), '+/', '-_'), '=');
    
    return "$headerEncoded.$payloadEncoded.$signatureEncoded";
}

$secret = getenv('JWT_SECRET') ?: 'potash_copper_coal';
$expirationMinutes = getenv('JWT_EXPIRATION_MINUTES') ?: 30;

$token = createJwtToken($secret, $expirationMinutes);
echo "JWT Token (expires in {$expirationMinutes} minutes):\n\n";
echo $token . "\n\n";
echo "Expires: " . date('Y-m-d H:i:s', time() + ($expirationMinutes * 60)) . "\n";
