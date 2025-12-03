<?php

/** @var \Laravel\Lumen\Routing\Router $router */

/*
|--------------------------------------------------------------------------
| Application Routes
|--------------------------------------------------------------------------
|
| Here is where you can register all of the routes for an application.
| It is a breeze. Simply tell Lumen the URIs it should respond to
| and give it the Closure to call when that URI is requested.
|
*/

$router->get('/', function () use ($router) {
    return $router->app->version();
});

$router->group(['middleware' => 'jwt'], function () use ($router) {
    $router->post('/eda/query', 'EdaController@query');
    $router->get('/eda/query', 'EdaController@query');
    $router->post('/eda/upload', 'EdaController@upload');
    $router->get('/eda/upload-test', function() {
        return response()->json(['test' => 'Upload endpoint accessible', 'php_version' => phpversion()]);
    });
    $router->post('/eda/upload-debug', function(Illuminate\Http\Request $request) {
        try {
            return response()->json([
                'has_file' => $request->hasFile('file'),
                'files' => $request->allFiles(),
                'content_length' => $request->header('Content-Length'),
                'method' => $request->method()
            ]);
        } catch (Exception $e) {
            return response()->json(['error' => $e->getMessage()]);
        }
    });
    $router->get('/test', 'TestController@test');
});

// Temporary unprotected debug endpoint
$router->post('/eda/upload-debug-noauth', function(Illuminate\Http\Request $request) {
    return response()->json(['status' => 'received', 'has_file' => $request->hasFile('file')]);
});
