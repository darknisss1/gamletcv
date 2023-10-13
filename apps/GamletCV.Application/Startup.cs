using System.Windows;
using GamletCV.Application.Pages;

public class Startup : Application
{
    readonly MainWindow mainWindow;
 
    public Startup(MainWindow mainWindow)
    {
        this.mainWindow = mainWindow;
    }
    
    protected override void OnStartup(StartupEventArgs e)
    {
        mainWindow.Show();  
        
        base.OnStartup(e);
    }
}