// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner;

import java.io.File;
import java.io.PrintWriter;
import java.util.Collection;
import java.util.Iterator;
import java.util.Map;
import java.util.logging.Logger;

public class PerlRun extends TaskRun {

    public PerlRun(File wrapperFile,
            File outputDir, RunFactory factory, Logger runLogger
        ) {
        super(wrapperFile, outputDir, factory, runLogger);
        runLogger.info("PerlRun: " + scriptPath);
    }

    protected void writeStartupScript(PrintWriter out)
    throws TaskRunException {
        out.println("no warnings 'once';");

        generateWrapperVariables(new PerlStartupScriptWriter(out));

        out.println("use warnings 'once';");
        out.println("$! = undef; $@ = '???';");
        out.println("if (!defined(do " + quoteString(scriptPath) + ")) {");
        out.println("    my $msg = undef;");
        out.println("    if ($@ eq '???') {");
        out.println("        $msg = $!;");
        out.println("    } elsif ($@) {");
        out.println("        $msg = $@;");
        out.println("    }");
        out.println("    if (defined($msg)) {");
        out.println("        chomp($msg);");
        out.println("        die $msg, \"\\n\";");
        out.println("    }");
        out.println("}");
    }

    private class PerlStartupScriptWriter
    implements StartupScriptGenerator {

        private final PrintWriter out;

        PerlStartupScriptWriter(PrintWriter out) {
            this.out = out;
        }

        public boolean encodeCollectionOpen(Context context, Collection value) {
            if (context.isFirstLevel()) {
                boolean allStrings = true;
                for (final Iterator i = value.iterator(); allStrings && i.hasNext(); ) {
                    allStrings &= i.next() instanceof String;
                }
                if (allStrings) {
                    out.println(
                        "our $" + context.getLastName() + "=" +
                        quoteParameter(join(value, ' '))
                        );
                }
                out.print("our @" + context.getLastName() + "=(");
            } else {
                if (context.isInsideMap()) {
                    out.print(quoteString(context.getLastName()) + "=>");
                }
                out.print('[');
            }
            return true;
        }

        public void encodeCollectionClose(Context context, Collection value) {
            if (context.isFirstLevel()) {
                out.println(");");
            } else {
                out.print("],");
            }
        }

        public boolean encodeMapOpen(Context context, Map value) {
            if (context.isFirstLevel()) {
                out.print("our %" + context.getLastName() + "=(");
            } else {
                if (context.isInsideMap()) {
                    out.print(quoteString(context.getLastName()) + "=>");
                }
                out.print('{');
            }
            return true;
        }

        public void encodeMapClose(Context context, Map value) {
            if (context.isFirstLevel()) {
                out.println(");");
            } else {
                out.print("},");
            }
        }

        public void encodeString(Context context, String value) {
            if (context.isFirstLevel()) {
                out.println("our $" + context.getLastName() + "=" + quoteParameter(value));
            } else {
                if (context.isInsideMap()) {
                    out.print(quoteString(context.getLastName()) + "=>");
                }
                out.print(quoteString(value) + ',');
            }
        }

    }

    private static String quoteString(String value) {
        return '\'' + value.replaceAll("'", "'.\"'\".'") + "'";
    }

    protected String quoteParameter(String value) {
        return quoteString(value) + ';';
    }

    protected String[] getStartupCommand(String startupScriptPath) {
        return new String[] { "perl", "-w", startupScriptPath };
    }

    protected void updateEnvironment(Map<String, String> env) {
        // https://perldoc.perl.org/perlrun.html#PERL_UNICODE
        env.put("PERL_UNICODE", "SDA");
    }

}
