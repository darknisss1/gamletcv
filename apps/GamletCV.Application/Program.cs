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
        // создаем хост приложения
        var host = Host.CreateDefaultBuilder()
            // внедряем сервисы
            .ConfigureServices(services =>
            {
                services.AddSingleton<Startup>();
                services.AddSingleton<MainWindow>();
                services.AddSingleton<IWebCamera, WebCamera>();
            })
            .Build();
        // получаем сервис - объект класса Startup
        var app = host.Services.GetService<Startup>();
        // запускаем приложения
        app?.Run();
    }
}