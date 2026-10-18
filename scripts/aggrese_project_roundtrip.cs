// Read an Aggre-SE project XML and save it again as Aggre-SE itself does (decision 49), without the screen.
//
// Usage: AggreSeProjectRoundtrip.exe <folder of Batch.exe> <project.xml> <saved.xml>
//
// The steps are those of MDIParentForm: open reads the file as Shift-JIS, Input.SetXmData and Input.applyVersion;
// save writes Input.GetXmlData() with a Shift-JIS StreamWriter (no BOM, no trailing newline). The forms' own
// DataSave/DataLoad are not run: what is checked is the serializer's reading and writing of the file. Batch.exe and
// its libraries are loaded from the given folder; nothing there is changed. Prints the saved Version as JSON.
using System;
using System.IO;
using System.Reflection;
using System.Text;

internal static class AggreSeProjectRoundtrip
{
    private static string batchFolder;

    private static int Main(string[] args)
    {
        if (args.Length != 3)
        {
            Console.Error.WriteLine("usage: AggreSeProjectRoundtrip.exe <folder of Batch.exe> <project.xml> <saved.xml>");
            return 2;
        }
        batchFolder = Path.GetFullPath(args[0]);
        AppDomain.CurrentDomain.AssemblyResolve += Resolve;
        try
        {
            return Run(args[1], args[2]);
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine(ex.ToString());
            return 1;
        }
    }

    private static Assembly Resolve(object sender, ResolveEventArgs args)
    {
        string name = new AssemblyName(args.Name).Name;
        foreach (string suffix in new[] { ".dll", ".exe" })
        {
            string path = Path.Combine(batchFolder, name + suffix);
            if (File.Exists(path))
                return Assembly.LoadFrom(path);
        }
        return null;
    }

    private static int Run(string source, string target)
    {
        Assembly batch = Assembly.LoadFrom(Path.Combine(batchFolder, "Batch.exe"));
        Type input = batch.GetType("Aggre.Input", true);
        Encoding shiftJis = Encoding.GetEncoding("shift_jis");
        BindingFlags shared = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static;

        input.GetMethod("Clear", shared).Invoke(null, null);
        input.GetMethod("SetXmData", shared).Invoke(null, new object[] { File.ReadAllText(source, shiftJis) });
        input.GetField("FileName", shared).SetValue(null, Path.GetFullPath(source));
        input.GetMethod("applyVersion", shared).Invoke(null, null);
        string saved = (string)input.GetMethod("GetXmlData", shared).Invoke(null, null);
        using (var writer = new StreamWriter(target, false, shiftJis))
            writer.Write(saved);

        object data = input.GetField("Data", shared).GetValue(null);
        string version = (string)data.GetType().GetField("Version").GetValue(data);
        Console.WriteLine("{\"version\":\"" + version + "\"}");
        return 0;
    }
}
