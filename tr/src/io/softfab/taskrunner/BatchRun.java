// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner;

import java.io.File;
import java.io.PrintWriter;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Iterator;
import java.util.logging.Logger;
import java.util.regex.Pattern;

/**
Generic wrapper for running shell scripts.
*/
public class BatchRun extends ScalarRun {

    /**
     * Regular expression used to quote special characters.
     */
    private final static Pattern SPECIAL_CHARACTERS = Pattern.compile(
        "[&|><^]"
        );

    public BatchRun(File wrapperFile,
            File outputDir, RunFactory factory, Logger runLogger
        ) {
        super(wrapperFile, outputDir, factory, runLogger);
        runLogger.info("BatchRun: " + scriptPath);
    }

    protected String quoteParameter(String value) {
        // In theory, we can escape with "^" too, but that has the problem
        // that the special characters will regain their special function
        // when the variable is used. That can be worked around with multiple
        // levels of escaping, but only if we know the number of times an
        // expression is evaluated, which we do not know in general.
        return SPECIAL_CHARACTERS.matcher(value).find()
            ? '"' + value + '"' : value;
    }

    protected String getParameterLinePrefix() {
        return "set ";
    }

    protected void printProlog(PrintWriter out) {
        out.println("@echo off");
    }

    protected void printEpilog(PrintWriter out) {
        out.println('"' + scriptPath + '"');
    }

    protected String[] getStartupCommand(String startupScriptPath) {
        return new String[] { startupScriptPath };
    }

    protected String encodeSequence(Collection col) {
        final Collection encoded = new ArrayList(col.size());
        for (final Iterator i = col.iterator(); i.hasNext(); ) {
            final String strVal =  i.next().toString();
            encoded.add(
                // Quotes have to be explicitly removed in the batch file, so
                // do not use them if not necessary, to allow batch files that
                // never get values containing spaces or special characters to
                // ignore quoting.
                  strVal.indexOf(' ') == -1
                ? quoteParameter(strVal)
                : '"' + strVal + '"'
                );
        }
        return join(encoded, ' ');
    }

}
