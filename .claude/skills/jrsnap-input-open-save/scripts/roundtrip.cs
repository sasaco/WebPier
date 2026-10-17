using System;
using System.IO;
using System.Reflection;
using System.Runtime.Serialization;
using System.Windows.Forms;

#if V52
[assembly: AssemblyVersion("5.2.3.1")]
#else
[assembly: AssemblyVersion("5.3.1.3")]
#endif

internal static class RoundTrip
{
    [STAThread]
    private static int Main(string[] args)
    {
        try
        {
            if (args.Length != 3)
                throw new ArgumentException("Expected: JRSNAP_Input.exe input.ndu output.ndu");

            string executable = Path.GetFullPath(args[0]);
            string input = Path.GetFullPath(args[1]);
            string output = Path.GetFullPath(args[2]);
            if (!File.Exists(executable) || !File.Exists(input) || File.Exists(output))
                throw new IOException("Executable or input missing, or output already exists.");

            Directory.SetCurrentDirectory(Path.GetDirectoryName(output));
            AppDomain.CurrentDomain.AssemblyResolve += delegate(object sender, ResolveEventArgs e)
            {
                string dependency = Path.Combine(
                    Path.GetDirectoryName(executable),
                    new AssemblyName(e.Name).Name + ".dll");
                return File.Exists(dependency) ? Assembly.LoadFrom(dependency) : null;
            };

            Assembly assembly = Assembly.LoadFrom(executable);
            if (assembly.GetName().Version != Assembly.GetExecutingAssembly().GetName().Version)
                throw new InvalidOperationException("The helper and JRSNAP assembly versions differ.");

            Type global2 = assembly.GetType("DataInputTool.mdlGlobal2", true);
            global2.GetField("G_intSNAP_FLG").SetValue(null, (short)1);
            short[] flags = (short[])global2.GetField("G_intViewFlg").GetValue(null);
            // MDmain.Main JRSNAP branch (Left=1), plus mdlInitData.mdl_Get_INIFile [22].
            short[] values = { 1, 0, 1, 1, 1, 2, 2, 1, 1, 1, 0, 1, 1, 1, 0,
                               1, 0, 1, 0, 0, 1, 1, 1, 1, 0, 1, 0 };
            Array.Copy(values, flags, values.Length);
            global2.GetField("G_blnVerKanri").SetValue(null, true);

            // mdl_Get_NDUDataFile updates only this menu item in the main form.
            // An uninitialized stub avoids starting the UI or changing its INI files.
            Type formType = assembly.GetType("DataInputTool.frmMain", true);
            Form form = (Form)FormatterServices.GetUninitializedObject(formType);
            formType.GetField("_mnuOTFLink", BindingFlags.Instance | BindingFlags.NonPublic)
                    .SetValue(form, new ToolStripMenuItem());
            assembly.GetType("DataInputTool.mdlGlobal", true)
                    .GetField("G_MainFrm").SetValue(null, form);

            assembly.GetType("DataInputTool.mdlInitData", true)
                    .GetMethod("mdl_SystemInitialize").Invoke(null, null);
            Type dataFile = assembly.GetType("DataInputTool.mdlDataFile", true);
            object[] readArgs = { input };
            int readCode = Convert.ToInt32(dataFile.GetMethod("mdl_Get_NDUDataFile")
                .Invoke(null, readArgs));
            if (readCode != 0)
                throw new InvalidOperationException("JRSNAP read code: " + readCode);

            object[] writeArgs = { output };
            int writeCode = Convert.ToInt32(dataFile.GetMethod("mdl_Wrt_NDUDataFile")
                .Invoke(null, writeArgs));
            if (writeCode != 0 || !File.Exists(output))
                throw new InvalidOperationException("JRSNAP write code: " + writeCode);

            Console.WriteLine("read=0 write=0 " + output);
            return 0;
        }
        catch (Exception error)
        {
            Console.Error.WriteLine(error);
            return 1;
        }
    }
}
