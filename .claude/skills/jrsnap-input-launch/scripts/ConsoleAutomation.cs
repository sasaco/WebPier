using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text;

public static class JrsnapConsoleAutomation
{
    [StructLayout(LayoutKind.Sequential)]
    private struct KeyEventRecord
    {
        [MarshalAs(UnmanagedType.Bool)] public bool KeyDown;
        public ushort RepeatCount;
        public ushort VirtualKeyCode;
        public ushort VirtualScanCode;
        public char UnicodeChar;
        public uint ControlKeyState;
    }

    [StructLayout(LayoutKind.Explicit)]
    private struct InputRecord
    {
        [FieldOffset(0)] public ushort EventType;
        [FieldOffset(4)] public KeyEventRecord KeyEvent;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct Coord { public short X; public short Y; }
    [StructLayout(LayoutKind.Sequential)]
    private struct SmallRect { public short Left, Top, Right, Bottom; }
    [StructLayout(LayoutKind.Sequential)]
    private struct ConsoleScreenBufferInfo
    {
        public Coord Size;
        public Coord CursorPosition;
        public ushort Attributes;
        public SmallRect Window;
        public Coord MaximumWindowSize;
    }

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool AttachConsole(uint processId);
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool FreeConsole();
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern IntPtr CreateFile(string name, uint access, uint share,
        IntPtr security, uint creation, uint flags, IntPtr template);
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool WriteConsoleInput(IntPtr handle, InputRecord[] records,
        uint length, out uint written);
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool CloseHandle(IntPtr handle);
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool GetConsoleScreenBufferInfo(IntPtr handle,
        out ConsoleScreenBufferInfo info);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool ReadConsoleOutputCharacter(IntPtr handle,
        StringBuilder buffer, uint length, Coord coordinate, out uint read);

    public static string ReadTail(int processId, int lines)
    {
        FreeConsole();
        if (!AttachConsole((uint)processId))
            throw new Win32Exception(Marshal.GetLastWin32Error(), "AttachConsole failed");
        IntPtr handle = IntPtr.Zero;
        try
        {
            handle = CreateFile("CONOUT$", 0x80000000, 3, IntPtr.Zero, 3, 0, IntPtr.Zero);
            if (handle == new IntPtr(-1))
                throw new Win32Exception(Marshal.GetLastWin32Error(), "Open CONOUT$ failed");
            ConsoleScreenBufferInfo info;
            if (!GetConsoleScreenBufferInfo(handle, out info))
                throw new Win32Exception(Marshal.GetLastWin32Error(), "GetConsoleScreenBufferInfo failed");
            int first = Math.Max(0, info.CursorPosition.Y - Math.Max(1, lines) + 1);
            var output = new StringBuilder();
            for (int y = first; y <= info.CursorPosition.Y; y++)
            {
                var row = new StringBuilder(info.Size.X);
                uint read;
                if (!ReadConsoleOutputCharacter(handle, row, (uint)info.Size.X,
                    new Coord { X = 0, Y = (short)y }, out read))
                    throw new Win32Exception(Marshal.GetLastWin32Error(), "ReadConsoleOutputCharacter failed");
                output.AppendLine(row.ToString().TrimEnd());
            }
            return output.ToString();
        }
        finally
        {
            if (handle != IntPtr.Zero && handle != new IntPtr(-1)) CloseHandle(handle);
            FreeConsole();
        }
    }

    public static void SendEnter(int processId)
    {
        FreeConsole();
        if (!AttachConsole((uint)processId))
            throw new Win32Exception(Marshal.GetLastWin32Error(), "AttachConsole failed");
        IntPtr handle = IntPtr.Zero;
        try
        {
            handle = CreateFile("CONIN$", 0xC0000000, 3, IntPtr.Zero, 3, 0, IntPtr.Zero);
            if (handle == new IntPtr(-1))
                throw new Win32Exception(Marshal.GetLastWin32Error(), "Open CONIN$ failed");
            var records = new InputRecord[2];
            records[0].EventType = 1;
            records[0].KeyEvent = new KeyEventRecord {
                KeyDown = true, RepeatCount = 1, VirtualKeyCode = 13, UnicodeChar = '\r'
            };
            records[1].EventType = 1;
            records[1].KeyEvent = new KeyEventRecord {
                KeyDown = false, RepeatCount = 1, VirtualKeyCode = 13, UnicodeChar = '\r'
            };
            uint written;
            if (!WriteConsoleInput(handle, records, 2, out written) || written != 2)
                throw new Win32Exception(Marshal.GetLastWin32Error(), "WriteConsoleInput failed");
        }
        finally
        {
            if (handle != IntPtr.Zero && handle != new IntPtr(-1)) CloseHandle(handle);
            FreeConsole();
        }
    }
}
