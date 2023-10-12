namespace GamletCV.Capture.Abstractions;

public interface IWebCamera
{
    IEnumerable<string> GetWebCameraCollection();
}