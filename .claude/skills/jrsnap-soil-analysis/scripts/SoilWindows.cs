using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;

public static class SoilWindows
{
    public sealed class WindowInfo
    {
        public IntPtr Handle;
        public int ProcessId;
        public string Title;
        public string ClassName;
        public bool Visible;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct Rect { public int Left, Top, Right, Bottom; }

    private delegate bool EnumWindowsProc(IntPtr handle, IntPtr unused);

    [DllImport("user32.dll")]
    private static extern bool EnumWindows(EnumWindowsProc callback, IntPtr unused);
    [DllImport("user32.dll")]
    private static extern bool EnumChildWindows(IntPtr parent, EnumWindowsProc callback, IntPtr unused);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int GetWindowText(IntPtr handle, StringBuilder text, int maxCount);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int GetClassName(IntPtr handle, StringBuilder text, int maxCount);
    [DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(IntPtr handle, out int processId);
    [DllImport("user32.dll")]
    private static extern bool IsWindowVisible(IntPtr handle);
    [DllImport("user32.dll", SetLastError = true)]
    private static extern IntPtr SendMessageTimeout(IntPtr handle, uint message, IntPtr wParam,
        IntPtr lParam, uint flags, uint timeout, out IntPtr result);
    [DllImport("user32.dll")]
    private static extern bool GetWindowRect(IntPtr handle, out Rect rect);
    [DllImport("user32.dll")]
    private static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")]
    private static extern bool SetForegroundWindow(IntPtr handle);
    [DllImport("user32.dll")]
    private static extern void mouse_event(uint flags, uint x, uint y, uint data, IntPtr extra);

    private static WindowInfo Describe(IntPtr handle)
    {
        int processId;
        GetWindowThreadProcessId(handle, out processId);
        var title = new StringBuilder(1024);
        var className = new StringBuilder(256);
        GetWindowText(handle, title, title.Capacity);
        GetClassName(handle, className, className.Capacity);
        return new WindowInfo {
            Handle = handle, ProcessId = processId, Title = title.ToString(),
            ClassName = className.ToString(), Visible = IsWindowVisible(handle)
        };
    }

    public static WindowInfo[] TopLevelWindows(int processId)
    {
        var result = new List<WindowInfo>();
        EnumWindows((handle, unused) => {
            var item = Describe(handle);
            if (item.ProcessId == processId) result.Add(item);
            return true;
        }, IntPtr.Zero);
        return result.ToArray();
    }

    public static WindowInfo[] ChildWindows(IntPtr parent)
    {
        var result = new List<WindowInfo>();
        EnumChildWindows(parent, (handle, unused) => {
            result.Add(Describe(handle));
            return true;
        }, IntPtr.Zero);
        return result.ToArray();
    }

    public static void ClickButton(IntPtr handle)
    {
        IntPtr ignored;
        if (SendMessageTimeout(handle, 0x00F5, IntPtr.Zero, IntPtr.Zero,
            0x0002, 5000, out ignored) == IntPtr.Zero)
            throw new InvalidOperationException("BM_CLICK failed or timed out");
    }

    public static void Activate(IntPtr handle)
    {
        if (!SetForegroundWindow(handle))
            throw new InvalidOperationException("Could not activate the dialog");
    }

    // The calculation icon is at (171, 66) in this version's main window.
    public static void ClickCalculate(IntPtr mainWindow)
    {
        Rect rect;
        if (!GetWindowRect(mainWindow, out rect) || !SetCursorPos(rect.Left + 171, rect.Top + 66))
            throw new InvalidOperationException("Could not position the cursor on Calculate");
        mouse_event(0x0002, 0, 0, 0, IntPtr.Zero);
        mouse_event(0x0004, 0, 0, 0, IntPtr.Zero);
    }
}
