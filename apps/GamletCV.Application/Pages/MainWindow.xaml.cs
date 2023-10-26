using System.Drawing;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using GamletCV.Domain;
using GamletCV.Services.Abstractions;

namespace GamletCV.Application.Pages;

/// <summary>
/// Interaction logic for MainWindow.xaml
/// </summary>
public partial class MainWindow : Window
{
    private readonly IWebCamera webCamera; 
    private Thread myUIthred;
 
    public MainWindow(IWebCamera webCamera)
    {
        myUIthred = Thread.CurrentThread;
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
        webCamera.SampleEvent += WebCameraOnSampleEvent;
        webCamera.Start();
    }

    private void WebCameraOnSampleEvent(object sender, SampleEventArgs e)
    {
        if (Thread.CurrentThread != myUIthred) //Tell the UI thread to invoke me if its not him who is running me.
        {
            return;
        }
        
        Task.Run(() => mainImage.Source = BitmapToImageSource(new Bitmap(e.Bitmap)));
    }

    private void ButtonStopCamera(object sender, RoutedEventArgs e)
    {
        webCamera.SampleEvent -= WebCameraOnSampleEvent;
        webCamera.Stop();
    }

    private BitmapImage BitmapToImageSource(Bitmap bitmap)
    {
        using (var memory = new MemoryStream())
        {
            bitmap.Save(memory, System.Drawing.Imaging.ImageFormat.Bmp);
            memory.Position = 0;
            var bitmapimage = new BitmapImage();
            bitmapimage.BeginInit();
            bitmapimage.StreamSource = memory;
            bitmapimage.CacheOption = BitmapCacheOption.OnLoad;
            bitmapimage.EndInit();

            return bitmapimage;
        }
    }
}