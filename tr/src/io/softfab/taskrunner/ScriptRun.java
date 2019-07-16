// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileReader;
import java.io.IOException;
import java.io.PrintWriter;
import java.util.Collection;
import java.util.logging.Logger;
import java.util.regex.Pattern;

/**
 * Generic wrapper for running shell scripts.
 */
public class ScriptRun extends ScalarRun {

    /**
     * Regular expression used to quote special characters.
     */
    private final static Pattern SPECIAL_CHARACTERS = Pattern.compile(
        "([*|&;()<>~`\"'\\\\!$ \t?])"
        );
    private final String shell;

    public ScriptRun(File wrapperFile,
            File outputDir, RunFactory factory, Logger runLogger
        ) {
        super(wrapperFile, outputDir, factory, runLogger);
        runLogger.info("ScriptRun: " + scriptPath);

        String firstLine = null;
        try {
            final BufferedReader in =
                new BufferedReader(new FileReader(wrapperFile));
            firstLine = in.readLine();
            in.close();
        } catch (IOException e) {
            runLogger.warning(
                "Could not open wrapper to detect shell used: " + e);
        }
        String shell;
        if (firstLine != null && firstLine.startsWith("#!")) {
            shell = firstLine.substring(2).trim();
        } else {
            shell = "/bin/sh";
            runLogger.info("Wrapper script does not start with \"#!\", "
                + "using default shell \"" + shell + "\"");
        }
        final boolean windows = File.separatorChar == '\\';
        if (windows) {
            // Absolute paths will only work within MSYS or other shell ports,
            // not when started from Java. As a workaround, use the shell name
            // only, so it will be looked up in the PATH.
            shell = shell.substring(shell.lastIndexOf('/') + 1);
        }
        this.shell = shell;
    }

    protected String quoteParameter(String value) {
        return SPECIAL_CHARACTERS.matcher(value).replaceAll("\\\\$1");
    }

    protected void printEpilog(PrintWriter out) {
        out.println(". " + scriptPath);
    }

    protected String[] getStartupCommand(String startupScriptPath) {
        return new String[] { shell, startupScriptPath };
    }

    protected String encodeSequence(Collection col) {
        return quoteParameter(join(col, ' '));
    }

}
