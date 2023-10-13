using System.Windows;
using System.Windows.Controls;
using GamletCV.Services.Abstractions;

namespace GamletCV.Application.Pages;

/// <summary>
/// Interaction logic for MainWindow.xaml
/// </summary>
public partial class MainWindow : Window
{
    private readonly IWebCamera webCamera; 
        
    public MainWindow(IWebCamera webCamera)
    {
        this.webCamera = webCamera;
            
        InitializeComponent();
            
        foreach (var cameraName in this.webCamera.GetCameraNames())
        {
            ComboBoxCameraName.Items.Add(cameraName);
        }
    }

    private void ComboBoxCameraNameSelectionChanged(object sender, RoutedEventArgs e)
    {
        webCamera.SetCurrentCamera(((ComboBox)sender).SelectedValue.ToString());
    }
        
    private void ButtonStartCamera(object sender, RoutedEventArgs e)
    {
        webCamera.Start();
    }
        
    private void ButtonStopCamera(object sender, RoutedEventArgs e)
    {
        webCamera.Stop();
    }
}