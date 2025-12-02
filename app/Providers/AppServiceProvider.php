<?php

namespace App\Providers;

use Illuminate\Support\ServiceProvider;
use App\Services\EdaService;

class AppServiceProvider extends ServiceProvider
{
    /**
     * Register any application services.
     *
     * @return void
     */
    public function register()
    {
        $this->app->singleton(EdaService::class, function ($app) {
            return new EdaService();
        });
    }
}
