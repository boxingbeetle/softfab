// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner;

import java.io.File;
import java.io.PrintWriter;
import java.util.Collection;
import java.util.Iterator;
import java.util.Map;
import java.util.logging.Logger;

public abstract class ScalarRun extends TaskRun {

    protected ScalarRun(File wrapperFile,
            File outputDir, RunFactory factory, Logger runLogger
        ) {
        super(wrapperFile, outputDir, factory, runLogger);
    }

    protected String getParameterLinePrefix() {
        return "";
    }

    /**
     * Handles parameter value quoting necessary for the parameter file.
     * Default implementation does nothing and returns the original value.
     */
    protected String quoteParameter(String value) {
        return value;
    }

    protected void writeStartupScript(PrintWriter out)
    throws TaskRunException {
        // Collect variables.
        final WrapperVariableFlattener collector = new WrapperVariableFlattener('_');
        generateWrapperVariables(collector);

        // Write script.
        printProlog(out);
        final String prefix = getParameterLinePrefix();
        for (final Iterator it = collector.getVariables(); it.hasNext(); ) {
            final Map.Entry entry = (Map.Entry)it.next();
            final String name = (String)entry.getKey();
            final Object value = entry.getValue();
            out.println(
                prefix + name + "=" + (
                    value instanceof Collection
                    ? encodeSequence((Collection)value)
                    : quoteParameter((String)value)
                    )
                );
        }
        printEpilog(out);
    }

    /**
     * Writes a fragment of code to the start of the startup script.
     * The default implementation writes nothing.
     */
    protected void printProlog(PrintWriter out) {
        // No prolog by default.
    }

    /**
     * Writes a fragment of code to the end of the startup script.
     * Note: Unlike printProlog, this method has no default since the startup
     *       script must start the wrapper and that can only be done in a
     *       language specific way.
     */
    protected abstract void printEpilog(PrintWriter out);

    /**
     * Encodes a sequence into a single expression.
     * @param col Collection of objects to take the string value of.
     * @return The expression representing the sequence.
     */
    abstract protected String encodeSequence(Collection col);

}
