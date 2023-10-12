using System.Windows;
using AForge.Video.DirectShow;
using GamletCV.Capture.Abstractions;

namespace GamletCV.Windows
{
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
        }
        
        
        private void buttonGetWebCameraCollection(object sender, RoutedEventArgs e)
        {
            var videoDevices = new FilterInfoCollection(FilterCategory.VideoInputDevice);
            
            var webCameraCollection = webCamera.GetWebCameraCollection();

            foreach (var webCamera in webCameraCollection)
            {
                ComboBoxWebCamera.Items.Add(webCamera);
            }
            
            var b = 123;
            // do something
        }
    }
}