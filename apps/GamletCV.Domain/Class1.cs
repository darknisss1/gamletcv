using System.Drawing;

namespace GamletCV.Domain;


public class SampleEventArgs
{
    public SampleEventArgs(Bitmap bitmap) { Bitmap = bitmap; }
    
    public Bitmap Bitmap { get; } // readonly
}