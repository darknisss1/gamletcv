﻿using System.Drawing;

namespace GamletCV.Domain.Delegates;

/// <summary>
/// Событие на каждый кадр камеры
/// </summary>
public delegate void WebCameraFrameEventHandler(object sender, WebCameraFrameEventArgs e);

/// <summary>
/// Аргументы события на каждый кадр камеры
/// </summary>
public class WebCameraFrameEventArgs : EventArgs
{
    public Bitmap Bitmap { get; set; }

    public bool IsMotion { get; set; }
}