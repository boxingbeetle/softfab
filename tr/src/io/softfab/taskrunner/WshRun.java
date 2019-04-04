// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner;

import java.io.File;
import java.io.FilenameFilter;
import java.io.IOException;
import java.io.PrintWriter;
import java.util.Collection;
import java.util.Collections;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.logging.Logger;

import io.softfab.taskrunner.config.ConfigFactory;
import io.softfab.taskrunner.config.TaskRunnerConfig;
import io.softfab.taskrunner.config.WrappersConfig;

/**
 * Generic wrapper for running scripts in Windows Scripting Host.
 */
public class WshRun extends TaskRun {

    public static final Map LANGUAGES;
    static {
        final Map map = new LinkedHashMap();
        map.put(".vbs", "VBScript");
        map.put(".js", "JScript");
        LANGUAGES = Collections.unmodifiableMap(map);
    }

    /**
     * Gets the file name extension (if any).
     * @param fileName File name to get the extension of.
     * @return The extension including the dot,
     *   or empty string if the file has no extension.
     */
    private static String getExtension(String fileName) {
        final int lastDot = fileName.lastIndexOf('.');
        return lastDot == -1 ? "" : fileName.substring(lastDot).toLowerCase();
    }

    /**
     * Determines the language of a script by looking at the file name.
     * @param fileName Name of the script file.
     * @return Language name as recognised by WSH.
     * @throws TaskRunException If the extension is unsupported.
     */
    private static String getLanguage(String fileName)
    throws TaskRunException {
        final String ext = getExtension(fileName);
        final String language = (String)LANGUAGES.get(ext);
        if (language == null) {
            throw new TaskRunException(
                "Unsupported script extension \"" + ext + "\""
                );
        }
        return language;
    }

    /**
     * Scripting language used by the wrapper.
     */
    private final String wrapperLanguage;

    /**
     * XML fragment for including scripts from the common directory.
     */
    private final String includeXML;

    public WshRun(File wrapperFile,
            File outputDir, RunFactory factory, Logger runLogger)
    throws TaskRunException {
        super(wrapperFile, outputDir, factory, runLogger);
        wrapperLanguage = getLanguage(wrapperFile.getName());
        runLogger.info("WshRun: " + scriptPath);

        // Scan 'common' dir for scripts to include.
        final StringBuffer includeBuf = new StringBuffer(100);
        final TaskRunnerConfig config = ConfigFactory.getConfig();
        final List wrappersBaseDirList = config.wrappers;
        for (final Iterator w = wrappersBaseDirList.iterator(); w.hasNext(); ) {
            final WrappersConfig wrappersConfig = (WrappersConfig)w.next();
            final File commonDir = new File((File)wrappersConfig.dir, "common");
            if (commonDir.isDirectory()) {
                final File[] commonScripts = commonDir.listFiles(
                    new FilenameFilter() {
                        public boolean accept(File dir, String name) { // NOPMD
                            return LANGUAGES.containsKey(getExtension(name));
                        }
                    });
                for (int i = 0; i < commonScripts.length; i++) {
                    final File script = commonScripts[i];
                    String filePath;
                    try {
                        filePath = script.getCanonicalPath();
                    } catch (IOException e) {
                        throw new TaskRunException(
                            "Error getting canonical path for included script", e
                            );
                    }
                    includeBuf.append(
                        "    <script language=\"" + getLanguage(filePath) +    "\" " +
                        "src=\"" + filePath + "\"/>\r\n"
                        );
                }
            }
        }
        includeXML = includeBuf.toString();
    }

    protected void writeStartupScript(PrintWriter out)
    throws TaskRunException {
        printProlog(out);
        generateWrapperVariables(new WshStartupScriptWriter(out));
        printEpilog(out);
    }

    private class WshStartupScriptWriter
    implements StartupScriptGenerator {

        private final PrintWriter out;

        WshStartupScriptWriter(PrintWriter out) {
            this.out = out;
        }

        public boolean encodeCollectionOpen(Context context, Collection value) {
            if (context.isFirstLevel()) {
                out.print("var " + context.getLastName() + "=SF_WRAP(");
            } else {
                if (!((Boolean)context.getCustomData()).booleanValue()) {
                    out.print(',');
                }
                if (context.isInsideMap()) {
                    out.print(context.getLastName() + ':');
                }
            }
            out.print('[');
            context.setCustomData(Boolean.TRUE);
            return true;
        }

        public void encodeCollectionClose(Context context, Collection value) {
            out.print(']');
            if (context.isFirstLevel()) {
                out.println(");");
            }
            context.setCustomData(Boolean.FALSE);
        }

        public boolean encodeMapOpen(Context context, Map value) {
            if (context.isFirstLevel()) {
                out.print("var " + context.getLastName() + "=SF_WRAP(");
            } else {
                if (!((Boolean)context.getCustomData()).booleanValue()) {
                    out.print(',');
                }
                if (context.isInsideMap()) {
                    out.print(context.getLastName() + ':');
                }
            }
            out.print('{');
            context.setCustomData(Boolean.TRUE);
            return true;
        }

        public void encodeMapClose(Context context, Map value) {
            out.print('}');
            if (context.isFirstLevel()) {
                out.println(");");
            }
            context.setCustomData(Boolean.FALSE);
        }

        public void encodeString(Context context, String value) {
            if (context.isFirstLevel()) {
                out.println("var " + context.getLastName() + "=" + quoteParameter(value));
            } else {
                if (!((Boolean)context.getCustomData()).booleanValue()) {
                    out.print(',');
                }
                if (context.isInsideMap()) {
                    out.print(context.getLastName() + ':');
                }
                out.print(quoteString(value));
                context.setCustomData(Boolean.FALSE);
            }
        }

    }

    private static String quoteString(String value) {
        return '\'' + value.replaceAll("(['\\\\])", "\\\\$1") + "'";
    }

    protected String quoteParameter(String value) {
        return quoteString(value) + ';';
    }

    protected String getStartupFileName() {
        return factory.getStartupFileBaseName() + ".wsf";
    }

    private void printProlog(PrintWriter out) {
        out.println("<?xml version=\"1.0\" ?>");
        out.println("<package>");
        out.println("  <job id=\"WshRun\">");
        out.println("    <?job debug=\"false\" error=\"true\" ?>");
        //out.println("    <object id=\"WSShell\" progid=\"WScript.Shell\"/>");
        out.println("    <script language=\"JScript\"><![CDATA[");
        out.println("    function SF_WRAP(value) {");
        out.println("        if (typeof(value) == 'object') {");
        out.println("            if (value instanceof Array) {");
        out.println("                for (var i = 0; i < value.length; i++) {");
        out.println("                    SF_WRAP(value[i]);");
        out.println("                }");
        out.println("            } else {");
        out.println("                var list = new Array();");
        out.println("                for (var prop in value) {");
        out.println("                    if (value.hasOwnProperty(prop)) {");
        out.println("                        list.push(SF_WRAP(value[prop]));");
        out.println("                    }");
        out.println("                }");
        out.println("                value.__list__ = list;");
        out.println("                value.size = function() {");
        out.println("                    return this.__list__.length;");
        out.println("                };");
        out.println("                value.get = function(prop) {");
        out.println("                    var value = this[prop];");
        out.println("                    if (value == undefined) {");
        out.println("                        return this.__list__[prop];");
        out.println("                    } else {");
        out.println("                        return value;");
        out.println("                    }");
        out.println("                };");
        out.println("            }");
        out.println("        }");
        out.println("        return value;");
        out.println("    }");
    }

    private void printEpilog(PrintWriter out) {
        out.println("    ]]></script>");
        out.println(includeXML);
        out.println("    <script language=\"" + wrapperLanguage + "\" src=\"" + scriptPath + "\"/>");
        out.println("  </job>");
        out.println("</package>");
    }

    protected String[] getStartupCommand(String startupScriptPath) {
        return new String[] { "CScript", "//Nologo", startupScriptPath };
    }
}
