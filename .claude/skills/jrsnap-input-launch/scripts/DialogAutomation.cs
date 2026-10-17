using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;

public static class JrsnapDialogAutomation
{
    public sealed class WindowInfo
    {
        public IntPtr Handle;
        public int ProcessId;
        public string Title;
        public string ClassName;
        public bool Visible;
    }

    private delegate bool EnumWindowsProc(IntPtr hwnd, IntPtr lParam);

    [DllImport("user32.dll")]
    private static extern bool EnumWindows(EnumWindowsProc callback, IntPtr lParam);
    [DllImport("user32.dll")]
    private static extern bool EnumChildWindows(IntPtr parent, EnumWindowsProc callback, IntPtr lParam);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int GetWindowText(IntPtr hwnd, StringBuilder text, int maxCount);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int GetClassName(IntPtr hwnd, StringBuilder text, int maxCount);
    [DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(IntPtr hwnd, out int processId);
    [DllImport("user32.dll")]
    private static extern bool IsWindowVisible(IntPtr hwnd);
    [DllImport("user32.dll")]
    private static extern int GetDlgCtrlID(IntPtr hwnd);
    [DllImport("user32.dll", SetLastError = true)]
    private static extern IntPtr SendMessageTimeout(IntPtr hwnd, uint message, IntPtr wParam,
        IntPtr lParam, uint flags, uint timeout, out IntPtr result);

    private static WindowInfo Describe(IntPtr hwnd)
    {
        int processId;
        GetWindowThreadProcessId(hwnd, out processId);
        var title = new StringBuilder(1024);
        var className = new StringBuilder(256);
        GetWindowText(hwnd, title, title.Capacity);
        GetClassName(hwnd, className, className.Capacity);
        return new WindowInfo {
            Handle = hwnd, ProcessId = processId, Title = title.ToString(),
            ClassName = className.ToString(), Visible = IsWindowVisible(hwnd)
        };
    }

    public static WindowInfo[] TopLevelWindows(int processId)
    {
        var result = new List<WindowInfo>();
        EnumWindows((hwnd, ignored) => {
            var item = Describe(hwnd);
            if (item.ProcessId == processId) result.Add(item);
            return true;
        }, IntPtr.Zero);
        return result.ToArray();
    }

    public static WindowInfo[] ChildWindows(IntPtr parent)
    {
        var result = new List<WindowInfo>();
        EnumChildWindows(parent, (hwnd, ignored) => {
            result.Add(Describe(hwnd));
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

    public static void ClickDialogButton(IntPtr dialog, IntPtr button)
    {
        int id = GetDlgCtrlID(button);
        if (id <= 0) throw new InvalidOperationException("Dialog button has no control ID");
        IntPtr ignored;
        if (SendMessageTimeout(dialog, 0x0111, new IntPtr(id), button,
            0x0002, 5000, out ignored) == IntPtr.Zero)
            throw new InvalidOperationException("WM_COMMAND failed or timed out");
    }

}
