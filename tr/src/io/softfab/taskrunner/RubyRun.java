// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner;

import java.io.File;
import java.io.PrintWriter;
import java.util.Collection;
import java.util.Map;
import java.util.logging.Logger;

public class RubyRun extends TaskRun {

    public RubyRun(File wrapperFile,
            File outputDir, RunFactory factory, Logger runLogger
        ) {
        super(wrapperFile, outputDir, factory, runLogger);
        runLogger.info("RubyRun: " + scriptPath);
    }

    protected void writeStartupScript(PrintWriter out)
    throws TaskRunException {
        generateWrapperVariables(new RubyStartupScriptWriter(out));
        out.println("load " + quoteParameter(scriptPath));
    }

    private class RubyStartupScriptWriter
    implements StartupScriptGenerator {

        private final PrintWriter out;

        RubyStartupScriptWriter(PrintWriter out) {
            this.out = out;
        }

        public boolean encodeCollectionOpen(Context context, Collection value) {
            if (context.isFirstLevel()) {
                out.print("$" + context.getLastName() + '=');
            } else {
                if (context.isInsideMap()) {
                    out.print(quoteParameter(context.getLastName()) + "=>");
                }
            }
            out.print('[');
            return true;
        }

        public void encodeCollectionClose(Context context, Collection value) {
            if (context.isFirstLevel()) {
                out.println(']');
            } else {
                out.print("],");
            }
        }

        public boolean encodeMapOpen(Context context, Map value) {
            if (context.isFirstLevel()) {
                out.print("$" + context.getLastName() + '=');
            } else {
                if (context.isInsideMap()) {
                    out.print(quoteParameter(context.getLastName()) + "=>");
                }
            }
            out.print('{');
            return true;
        }

        public void encodeMapClose(Context context, Map value) {
            if (context.isFirstLevel()) {
                out.println('}');
            } else {
                out.print("},");
            }
        }

        public void encodeString(Context context, String value) {
            if (context.isFirstLevel()) {
                out.println("$" + context.getLastName() + "=" + quoteParameter(value));
            } else {
                if (context.isInsideMap()) {
                    out.print(quoteParameter(context.getLastName()) + "=>");
                }
                out.print(quoteParameter(value) + ',');
            }
        }

    }

    protected String quoteParameter(String value) {
        return "'" + value.replaceAll("'", "\\\\'") + "'";
    }

    protected String[] getStartupCommand(String startupScriptPath) {
        return new String[] {
            "ruby", "--external-encoding=UTF-8", startupScriptPath
        };
    }

}
