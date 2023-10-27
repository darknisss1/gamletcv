using AForge.Video;
using AForge.Video.DirectShow;
using AForge.Vision.Motion;
using GamletCV.Domain.Delegates;
using GamletCV.Services.Abstractions;

namespace GamletCV.Services;

public class WebCamera : IWebCamera
{
    private readonly FilterInfoCollection filterInfoCollection;
    private VideoCaptureDevice camera;
    private readonly MotionDetector detector = new(
        new TwoFramesDifferenceDetector(), 
        new MotionAreaHighlighting());
    
    public WebCamera()
    {
        filterInfoCollection = new FilterInfoCollection(FilterCategory.VideoInputDevice);
    }

    public IEnumerable<string> GetCameraNames()
    {
        return from FilterInfo filterInfo in filterInfoCollection select filterInfo.Name;
    }

    public void SetCurrentCamera(string name)
    {
        camera?.Stop();

        foreach (FilterInfo filterInfo in filterInfoCollection)
        {
            if (filterInfo.Name != name)
            {
                continue;
            }
            
            camera = new VideoCaptureDevice(filterInfo.MonikerString);
                
            return;
        }

        camera = null;
    }

    public void Start()
    {
        if (camera == null)
        {
            return;
        }

        camera.NewFrame += NewFrame;

        if (!camera.IsRunning)
        {
            camera.Start();
        }
    }

    public void Stop()
    {
        if (camera == null)
        {
            return;
        }

        camera.NewFrame -= NewFrame;

        if (camera.IsRunning)
        {
            camera.SignalToStop();
        }
    }

    public event WebCameraFrameEventHandler WebCameraFrameEvent;

    private void NewFrame(object sender, NewFrameEventArgs eventArgs)
    {
        WebCameraFrameEvent?.Invoke(this, new WebCameraFrameEventArgs
        {
            IsMotion = detector.ProcessFrame(eventArgs.Frame) > 0.05,
            Bitmap = eventArgs.Frame
        });
    }
}