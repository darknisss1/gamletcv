using System.Windows;
using System.Windows.Controls;
using GamletCV.Application.Mappers;
using GamletCV.Domain.Delegates;
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
            СomboBoxCameraName.Items.Add(cameraName);
        }
    }

    private void ComboBoxCameraNameSelectionChanged(object sender, RoutedEventArgs e)
    {
        webCamera.SetCurrentCamera(((ComboBox)sender).SelectedValue.ToString());
    }
        
    private void ButtonStartCamera(object sender, RoutedEventArgs e)
    {
        webCamera.WebCameraFrameEvent += WebCameraFrameEvent;
        webCamera.Start();
        ButtonStart.IsEnabled = false;
        ButtonStop.IsEnabled = true;
    }

    private void ButtonStopCamera(object sender, RoutedEventArgs e)
    {
        webCamera.WebCameraFrameEvent -= WebCameraFrameEvent;
        webCamera.Stop();
        ButtonStart.IsEnabled = true;
        ButtonStop.IsEnabled = false;
    }
    
    private void WebCameraFrameEvent(object sender, WebCameraFrameEventArgs e)
    {
        Dispatcher.Invoke(() => mainImage.Source = BitmapImageMapper.Map(e.Bitmap));
    }
}