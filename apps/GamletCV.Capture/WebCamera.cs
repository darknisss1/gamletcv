using AForge.Video.DirectShow;

namespace GamletCV.Capture;

public class WebCamera
{
    // private FilterInfoCollection videoDevices; 
    //
    // private void EnumerateVideoDevices()
    // {
    //     // enumerate video devices
    //     videoDevices = new FilterInfoCollection(FilterCategory.VideoInputDevice);
    //     
    //     if (videoDevices.Count != 0)
    //     {
    //         // add all devices to combo
    //         foreach (FilterInfo device in videoDevices)
    //             ComboBoxSources.Items.Add(device.Name);
    //     }
    //     else
    //         ComboBoxSources.Items.Add("No DirectShow devices found");
    //     ComboBoxSources.SelectedIndex = 0;
    // }
    //
    // private void EnumerateVideoModes(VideoCaptureDevice device)
    // {
    //     // get resolutions for selected video source
    //     this.Cursor = Cursors.WaitCursor;
    //     ComboBoxModes.Items.Clear();
    //     try
    //     {
    //         videoCapabilities = videoDevice.VideoCapabilities;
    //         foreach (VideoCapabilities capabilty in videoCapabilities)
    //         {
    //             if (!ComboBoxModes.Items.Contains(capabilty.FrameSize))
    //                 ComboBoxModes.Items.Add(capabilty.FrameSize);
    //         }
    //         if (videoCapabilities.Length == 0)
    //             ComboBoxModes.Items.Add("Not supported");
    //         ComboBoxModes.SelectedIndex = 0;
    //     }
    //     finally
    //     {
    //         this.Cursor = Cursors.Default;
    //     }
    // }
    //
    // private void CameraStart()
    // {
    //     if (videoDevice != null)
    //     {
    //         if ((videoCapabilities != null) && (videoCapabilities.Length != 0))
    //             videoDevice.DesiredFrameSize = (Size)ComboBoxModes.SelectedItem;
    //         VideoSourcePlayer1.VideoSource = videoDevice;
    //         VideoSourcePlayer1.Start();
    //     }
    // }
    //
    // private void CameraStop()
    // {
    //     if (VideoSourcePlayer1.VideoSource != null)
    //     {
    //         // stop video device
    //         VideoSourcePlayer1.SignalToStop();
    //         VideoSourcePlayer1.WaitForStop();
    //         VideoSourcePlayer1.VideoSource = null;
    //     }
    // }
}