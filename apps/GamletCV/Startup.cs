using System.Windows;
using GamletCV.Windows;

public class Startup : Application
{
    readonly MainWindow mainWindow;
 
    public Startup(MainWindow mainWindow)
    {
        this.mainWindow = mainWindow;
    }
    
    protected override void OnStartup(StartupEventArgs e)
    {
        mainWindow.Show();  // отображаем главное окно на экране
        
        base.OnStartup(e);
    }
}