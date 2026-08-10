using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;

internal static class SuperToolsLauncher
{
    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    private static extern IntPtr LoadLibrary(string path);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern IntPtr GetProcAddress(IntPtr module, string name);

    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate int PyBytesMain(int argc, IntPtr argv);

    private static IntPtr AllocUtf8(string value)
    {
        byte[] bytes = Encoding.UTF8.GetBytes(value + "\0");
        IntPtr memory = Marshal.AllocHGlobal(bytes.Length);
        Marshal.Copy(bytes, 0, memory, bytes.Length);
        return memory;
    }

    public static int Main()
    {
        string root = Path.GetFullPath(AppDomain.CurrentDomain.BaseDirectory);
        string appRoot = Path.Combine(root, "app");
        string runtimeRoot = Path.Combine(root, "runtime");
        string libraryRoot = Path.Combine(runtimeRoot, "lib");
        string mainScript = Path.Combine(appRoot, "main.py");
        string pythonDll = Path.Combine(runtimeRoot, "python314.dll");
        string launcher = Path.Combine(root, "SuperTools.exe");

        if (!File.Exists(mainScript) || !File.Exists(pythonDll))
        {
            return 3;
        }

        Directory.SetCurrentDirectory(appRoot);
        string currentPath = Environment.GetEnvironmentVariable("PATH") ?? "";
        Environment.SetEnvironmentVariable(
            "PATH",
            runtimeRoot + ";" + libraryRoot + ";"
                + Path.Combine(libraryRoot, "PyQt6", "Qt6", "bin") + ";"
                + currentPath
        );
        Environment.SetEnvironmentVariable("PYTHONHOME", runtimeRoot);
        Environment.SetEnvironmentVariable(
            "PYTHONPATH",
            appRoot + ";" + libraryRoot + ";"
                + Path.Combine(libraryRoot, "library.zip")
        );
        Environment.SetEnvironmentVariable("PYTHONUTF8", "1");
        Environment.SetEnvironmentVariable("PYTHONDONTWRITEBYTECODE", "1");
        Environment.SetEnvironmentVariable("PYTHONNOUSERSITE", "1");
        Environment.SetEnvironmentVariable(
            "QT_PLUGIN_PATH",
            Path.Combine(libraryRoot, "PyQt6", "Qt6", "plugins")
        );
        Environment.SetEnvironmentVariable("DESKTOP_TOOLKIT_LAUNCHER", launcher);

        IntPtr module = LoadLibrary(pythonDll);
        if (module == IntPtr.Zero)
        {
            return 4;
        }
        IntPtr entry = GetProcAddress(module, "Py_BytesMain");
        if (entry == IntPtr.Zero)
        {
            return 5;
        }

        var pythonArgs = new List<string> { launcher, "-B", mainScript };
        IntPtr[] strings = new IntPtr[pythonArgs.Count];
        IntPtr argv = IntPtr.Zero;
        try
        {
            for (int i = 0; i < pythonArgs.Count; i++)
            {
                strings[i] = AllocUtf8(pythonArgs[i]);
            }
            argv = Marshal.AllocHGlobal(IntPtr.Size * strings.Length);
            Marshal.Copy(strings, 0, argv, strings.Length);
            var pyMain = (PyBytesMain)Marshal.GetDelegateForFunctionPointer(
                entry, typeof(PyBytesMain)
            );
            return pyMain(strings.Length, argv);
        }
        finally
        {
            if (argv != IntPtr.Zero)
            {
                Marshal.FreeHGlobal(argv);
            }
            foreach (IntPtr value in strings)
            {
                if (value != IntPtr.Zero)
                {
                    Marshal.FreeHGlobal(value);
                }
            }
        }
    }
}
