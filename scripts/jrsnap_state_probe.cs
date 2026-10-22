// What JRSNAP 5.2-L03 holds after reading an NDU: its counts and its combinations (SNAPConb), as one JSON line.
//
// Built and run by scripts/accept_jrsnap_ndu.py. It initialises JRSNAP_Input as the open/save helper of the skill
// jrsnap-input-open-save does (.claude/skills/jrsnap-input-open-save/scripts/roundtrip.cs), reads the NDU with
// mdlDataFile.mdl_Get_NDUDataFile and reports the static fields of DataInputTool.mdlGlobal. It writes nothing.
// Reading is not an analysis.
using System;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Runtime.Serialization;
using System.Text;
using System.Windows.Forms;

[assembly: AssemblyVersion("5.2.3.1")]

internal static class StateProbe
{
    private static readonly string[] Counts = {
        "G_intJointNum", "G_intMemberNum", "G_intElementNum", "G_intSectNum", "G_intSuppotNum", "G_intLoadNum",
        "G_intMLoadNum", "G_intJLoadNum", "G_intConbNum" };

    private static string Number(object value)
    {
        return Convert.ToString(value, CultureInfo.InvariantCulture);
    }

    [STAThread]
    private static int Main(string[] args)
    {
        try
        {
            if (args.Length != 2)
                throw new ArgumentException("Expected: JRSNAP_Input.exe input.ndu");
            string executable = Path.GetFullPath(args[0]);
            string input = Path.GetFullPath(args[1]);
            if (!File.Exists(executable) || !File.Exists(input))
                throw new IOException("Executable or input missing.");

            Directory.SetCurrentDirectory(Path.GetDirectoryName(input));
            AppDomain.CurrentDomain.AssemblyResolve += delegate(object sender, ResolveEventArgs e)
            {
                string dependency = Path.Combine(Path.GetDirectoryName(executable), new AssemblyName(e.Name).Name + ".dll");
                return File.Exists(dependency) ? Assembly.LoadFrom(dependency) : null;
            };
            Assembly assembly = Assembly.LoadFrom(executable);
            if (assembly.GetName().Version != Assembly.GetExecutingAssembly().GetName().Version)
                throw new InvalidOperationException("The probe and JRSNAP assembly versions differ.");

            Type global2 = assembly.GetType("DataInputTool.mdlGlobal2", true);
            global2.GetField("G_intSNAP_FLG").SetValue(null, (short)1);
            short[] flags = (short[])global2.GetField("G_intViewFlg").GetValue(null);
            short[] values = { 1, 0, 1, 1, 1, 2, 2, 1, 1, 1, 0, 1, 1, 1, 0,
                               1, 0, 1, 0, 0, 1, 1, 1, 1, 0, 1, 0 };
            Array.Copy(values, flags, values.Length);
            global2.GetField("G_blnVerKanri").SetValue(null, true);
            Type formType = assembly.GetType("DataInputTool.frmMain", true);
            Form form = (Form)FormatterServices.GetUninitializedObject(formType);
            formType.GetField("_mnuOTFLink", BindingFlags.Instance | BindingFlags.NonPublic)
                    .SetValue(form, new ToolStripMenuItem());
            Type global = assembly.GetType("DataInputTool.mdlGlobal", true);
            global.GetField("G_MainFrm").SetValue(null, form);
            assembly.GetType("DataInputTool.mdlInitData", true).GetMethod("mdl_SystemInitialize").Invoke(null, null);

            object[] readArgs = { input };
            int readCode = Convert.ToInt32(assembly.GetType("DataInputTool.mdlDataFile", true)
                .GetMethod("mdl_Get_NDUDataFile").Invoke(null, readArgs));
            if (readCode != 0)
                throw new InvalidOperationException("JRSNAP read code: " + readCode);

            StringBuilder json = new StringBuilder("{\"read_code\":0,\"counts\":{");
            for (int i = 0; i < Counts.Length; i++)
                json.Append(i == 0 ? "" : ",").Append('"').Append(Counts[i]).Append("\":")
                    .Append(Number(global.GetField(Counts[i]).GetValue(null)));
            json.Append("},\"combinations\":[");
            int combinations = Convert.ToInt32(global.GetField("G_intConbNum").GetValue(null));
            short[] caseCounts = (short[])global.GetField("G_intConbBca").GetValue(null);
            short[,] cases = (short[,])global.GetField("G_intConbBaNo").GetValue(null);
            float[,] alpha = (float[,])global.GetField("G_sngConbAlph").GetValue(null);
            float[] rho = (float[])global.GetField("G_sngConbRouM").GetValue(null);
            float[] af = (float[])global.GetField("G_sngConbAf").GetValue(null);
            short[] directions = (short[])global.GetField("G_intConbHoko").GetValue(null);  // 0 正向, 1 逆向
            for (int c = 1; c <= combinations; c++)
            {
                json.Append(c == 1 ? "" : ",").Append("{\"rho_m\":").Append(Number(rho[c]))
                    .Append(",\"alpha_f\":").Append(Number(af[c])).Append(",\"direction\":").Append(Number(directions[c]))
                    .Append(",\"cases\":[");
                for (int k = 1; k <= caseCounts[c]; k++)
                    json.Append(k == 1 ? "" : ",").Append(Number(cases[c, k]));
                json.Append("],\"coefficients\":[");
                for (int k = 1; k <= caseCounts[c]; k++)
                    json.Append(k == 1 ? "" : ",").Append(Number(alpha[c, k]));
                json.Append("]}");
            }
            Console.WriteLine(json.Append("]}").ToString());
            return 0;
        }
        catch (Exception error)
        {
            Console.Error.WriteLine(error);
            return 1;
        }
    }
}
