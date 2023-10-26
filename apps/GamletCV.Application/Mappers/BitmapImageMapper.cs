using System.Drawing;
using System.IO;
using System.Windows.Media.Imaging;

namespace GamletCV.Application.Mappers;

public static class BitmapImageMapper
{
    public static BitmapImage Map(Bitmap bitmap)
    {
        using var memory = new MemoryStream();
        
        bitmap.Save(memory, System.Drawing.Imaging.ImageFormat.Bmp);
        memory.Position = 0;
            
        var bitmapImage = new BitmapImage();
            
        bitmapImage.BeginInit();
        bitmapImage.StreamSource = memory;
        bitmapImage.CacheOption = BitmapCacheOption.OnLoad;
        bitmapImage.EndInit();

        return bitmapImage;
    }
}