using System;
using GamletCV.Application.Pages;
using GamletCV.Services;
using GamletCV.Services.Abstractions;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;

namespace GamletCV.Application;

public static class Program
{
    [STAThread]
    public static void Main()
    {
        Host.CreateDefaultBuilder()
            .ConfigureServices(services =>
            {
                services.AddSingleton<Startup>();
                services.AddSingleton<MainWindow>();
                services.AddSingleton<IWebCamera, WebCamera>();
            })
            .Build()
            .Services.GetService<Startup>()?
            .Run();
    }
}