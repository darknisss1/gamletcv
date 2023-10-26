﻿using AForge.Video.DirectShow;
using GamletCV.Domain.Delegates;
using GamletCV.Services.Abstractions;

namespace GamletCV.Services;

public class WebCamera : IWebCamera
{
    private readonly FilterInfoCollection filterInfoCollection;
    private VideoCaptureDevice camera;

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

    private void NewFrame(object sender, AForge.Video.NewFrameEventArgs eventArgs)
    {
        WebCameraFrameEvent?.Invoke(this, new WebCameraFrameEventArgs(eventArgs.Frame));
    }
}