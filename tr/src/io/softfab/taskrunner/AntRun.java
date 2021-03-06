// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.PrintWriter;
import java.util.Collection;
import java.util.Iterator;
import java.util.Map;
import java.util.Properties;
import java.util.logging.Logger;

public class AntRun extends TaskRun {

    public AntRun(File wrapperFile,
            File outputDir, RunFactory factory, Logger runLogger
        ) {
        super(wrapperFile, outputDir, factory, runLogger);
        runLogger.info("AntRun: " + scriptPath);
    }

    protected void writeStartupScript(PrintWriter out)
    throws TaskRunException {
        final File propertiesFile = new File(
            outputDir, factory.getStartupFileBaseName() + ".properties"
            );
        out.println("<project>");
        out.println("  <property file=\"" + propertiesFile.getAbsolutePath() + "\"/>");
        out.println("  <ant antfile=\"" + scriptPath + "\"/>");
        out.println("</project>");

        final WrapperVariableFlattener collector = new WrapperVariableFlattener('.');
        generateWrapperVariables(collector);
        final Properties properties = new Properties();
        for (final Iterator it = collector.getVariables(); it.hasNext(); ) {
            final Map.Entry entry = (Map.Entry)it.next();
            final String name = (String)entry.getKey();
            final Object value = entry.getValue();
            properties.put(
                name,
                value instanceof Collection
                ? join((Collection)value, ' ')
                : (String)value
                );
        }

        try {
            final FileOutputStream propOut = new FileOutputStream(propertiesFile);
            try {
                properties.store(propOut, "Generated by SoftFab Task Runner");
            } finally {
                propOut.close();
            }
        } catch (IOException e) {
            throw new TaskRunException(
                "Error writing \"" + propertiesFile.getName() + "\"", e
                );
        }
    }

    protected String[] getStartupCommand(String startupScriptPath) {
        return new String[] { "ant", "-f", startupScriptPath };
    }

}
