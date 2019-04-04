// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner;

import java.io.File;
import java.io.PrintWriter;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Iterator;
import java.util.logging.Logger;

/**
Generic wrapper for running Makefiles.
*/
public class MakeRun extends ScalarRun {

    public MakeRun(File wrapperFile,
            File outputDir, RunFactory factory, Logger runLogger
        ) {
        super(wrapperFile, outputDir, factory, runLogger);
        runLogger.info("MakeRun: " + wrapperFile.getAbsolutePath());
    }

    protected String quoteParameter(String value) {
        return value.replaceAll("\\$", "\\$\\$");
    }

    protected void printEpilog(PrintWriter out) {
        out.println("include " + scriptPath);
    }

    protected String[] getStartupCommand(String startupScriptPath) {
        // TODO: On what machines should we use "make" and on what machines
        //       should we use "gmake"?
        return new String[] { "make", "-C", outputDir.getAbsolutePath(), "-f", startupScriptPath };
    }

    protected String encodeSequence(Collection col) {
        final Collection encoded = new ArrayList(col.size());
        for (final Iterator i = col.iterator(); i.hasNext(); ) {
            final String strVal =  i.next().toString();
            encoded.add(quoteParameter(strVal));
        }
        return join(encoded, ' ');
    }

}
