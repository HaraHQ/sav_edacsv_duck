<?php

function createJwtToken($secret, $expirationMinutes = 1) {
    $header = json_encode(['typ' => 'JWT', 'alg' => 'HS256']);
    $payload = json_encode(['exp' => time() + ($expirationMinutes * 60)]);
    
    $headerEncoded = rtrim(strtr(base64_encode($header), '+/', '-_'), '=');
    $payloadEncoded = rtrim(strtr(base64_encode($payload), '+/', '-_'), '=');
    
    $signature = hash_hmac('sha256', "$headerEncoded.$payloadEncoded", $secret, true);
    $signatureEncoded = rtrim(strtr(base64_encode($signature), '+/', '-_'), '=');
    
    return "$headerEncoded.$payloadEncoded.$signatureEncoded";
}

// 48 hours = 2880 minutes
$token = createJwtToken('potash_copper_coal', 2880);
echo "48-hour JWT Token:\n\n";
echo $token . "\n\n";
echo "Expires: " . date('Y-m-d H:i:s', time() + (2880 * 60)) . "\n";
