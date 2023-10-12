using System;
using GamletCV.Capture;
using GamletCV.Capture.Abstractions;
using GamletCV.Windows;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;

namespace GamletCV;

public class Program1
{
    [STAThread]
    public static void Main()
    {
        // создаем хост приложения
        var host = Host.CreateDefaultBuilder()
            // внедряем сервисы
            .ConfigureServices(services =>
            {
                services.AddSingleton<StartUp>();
                services.AddSingleton<MainWindow>();
                services.AddSingleton<IWebCamera, WebCamera>();
            })
            .Build();
        // получаем сервис - объект класса StartUp
        var app = host.Services.GetService<StartUp>();
        // запускаем приложения
        app?.Run();
    }
}