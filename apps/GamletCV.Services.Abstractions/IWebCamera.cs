using System.Drawing;

namespace GamletCV.Services.Abstractions;

/// <summary>
/// Работа с камерой
/// </summary>
public interface IWebCamera
{
    /// <summary>
    /// Возвращает список всех доступных камер
    /// </summary>
    IEnumerable<string> GetCameraNames();

    /// <summary>
    /// Выставляем текущую камеру
    /// </summary>
    void SetCurrentCamera(string name);

    /// <summary>
    /// Запуск камеры
    /// </summary>
    void Start();

    /// <summary>
    /// Остановка камеры
    /// </summary>
    void Stop();
    
}