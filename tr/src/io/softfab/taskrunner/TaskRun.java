// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.File;
import java.io.FileReader;
import java.io.FileWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.util.Collection;
import java.util.Collections;
import java.util.HashMap;
import java.util.IdentityHashMap;
import java.util.Iterator;
import java.util.Map;
import java.util.Stack;
import java.util.TreeSet;
import java.util.logging.Level;
import java.util.logging.Logger;

import io.softfab.taskrunner.config.ConfigFactory;
import io.softfab.taskrunner.config.TaskRunnerConfig;

/**
 * A task run is one particular execution of a task.
 * The relevant job properties are kept here as well.
 */
public abstract class TaskRun {

    /**
     * Concatenates the string representations of the given objects,
     * separated by the given character.
     * @param items Objects whose string representation will be joined.
     * @param separator Character to place inbetween the items.
     * @return The joined string.
     */
    public static String join(Collection<?> items, char separator) {
        final StringBuffer buffer = new StringBuffer();
        boolean first = true;
        for (final Object item : items) {
            if (first) {
                first = false;
            } else {
                buffer.append(separator);
            }
            buffer.append(item.toString());
        }
        return buffer.toString();
    }

    /**
     * Factory that was responsible for creating this object
     */
    protected final RunFactory factory;

    /**
     * Task run information obtained form the Control Center
     */
    private final TaskRunInfo runInfo;

    private final File wrapperFile;

    /**
     * Base directory where output of this run will be written.
     */
    protected final File outputDir;

    /**
     * Logger that gathers all messages for this task run.
     */
    protected final Logger runLogger;

    /**
     * Indicates whether the task should be/has been aborted.
     */
    private boolean aborted;

    /**
     * Keeps reference to the process being executed, used for aborting.
     */
    private final Map<ExternalProcess, Void> processes;

    /**
     * The absolute path to the wrapper file
     */
    protected final String scriptPath;

    private Thread abortThread;

    /**
     * Reads task run parameters from a Config.
     */
    protected TaskRun(File wrapperFile, File outputDir, RunFactory factory,
            Logger runLogger
        ) {
        this.wrapperFile = wrapperFile;
        this.factory = factory;
        this.runInfo = factory.runInfo;
        this.outputDir = outputDir;
        this.runLogger = runLogger;

        processes = new IdentityHashMap<>();
        aborted = false;

        scriptPath = wrapperFile.getAbsolutePath();
    }

    /**
     * Gets the command to start the startup script.
     * @return The command line elements before the startup script path.
     */
    protected abstract String[] getStartupCommand(String startupScriptPath);

    /**
     * Customize the environment variables for the wrapper process.
     * The default implementation does nothing.
     */
    protected void updateEnvironment(Map<String, String> env) {
    }

    /**
     * Get the file name of the startup script.
     * This script defines several variables and then invokes the wrapper.
     */
    protected String getStartupFileName() {
        final String wrapperName = wrapperFile.getName();
        final int index = wrapperName.lastIndexOf('.');
        final String extension = wrapperName.substring(index);
        return factory.getStartupFileBaseName() + extension;
    }

    protected static final class Context {

        private final Stack<Object> nameStack;
        private Object customData;

        public Context() {
            nameStack = new Stack<>();
            customData = null;
        }

        public Collection<Object> getNames() {
            return Collections.unmodifiableCollection(nameStack);
        }

        public boolean isFirstLevel() {
            return nameStack.size() == 1;
        }

        public boolean isInsideCollection() {
            return nameStack.size() > 1 && nameStack.lastElement() instanceof Integer;
        }

        public boolean isInsideMap() {
            return nameStack.size() > 1 && nameStack.lastElement() instanceof String;
        }

        public String getLastName() {
            return (String)nameStack.lastElement();
        }

        public Object getCustomData() {
            return customData;
        }

        public void setCustomData(Object data) {
            customData = data;
        }

        private void pushName(Object name) {
            nameStack.push(name);
        }

        private void popName() {
            nameStack.pop();
        }
    }

    private void encodeValue(StartupScriptGenerator gen, Context context, Object value) {
        if (value instanceof Collection) {
            final Collection<Object> collection = (Collection<Object>)value;
            if (gen.encodeCollectionOpen(context, collection)) {
                int index = 0;
                for (final Object object : collection) {
                    context.pushName(index++);
                    encodeValue(gen, context, object);
                    context.popName();
                }
                gen.encodeCollectionClose(context, collection);
            }
        } else if (value instanceof Map) {
            final Map<Object, Object> map = (Map<Object, Object>)value;
            if (gen.encodeMapOpen(context, map)) {
                for (final Map.Entry<Object, Object> entry : map.entrySet()) {
                    context.pushName(entry.getKey());
                    encodeValue(gen, context, entry.getValue());
                    context.popName();
                }
                gen.encodeMapClose(context, map);
            }
        } else {
            gen.encodeString(context, value.toString());
        }
    }

    protected final void generateWrapperVariables(StartupScriptGenerator gen)
    throws TaskRunException {
        final Context context = new Context();
        for (final Map.Entry<String, Object> entry : createTaskEnvironment().entrySet()) {
            context.pushName(entry.getKey());
            encodeValue(gen, context, entry.getValue());
            context.popName();
        }
    }

    interface StartupScriptGenerator {

        boolean encodeCollectionOpen(Context context, Collection value);

        void encodeCollectionClose(Context context, Collection value);

        boolean encodeMapOpen(Context context, Map value);

        void encodeMapClose(Context context, Map value);

        void encodeString(Context context, String value);

    }

    protected abstract void writeStartupScript(PrintWriter out)
    throws TaskRunException;

    /**
     * Writes the task parameters to a file.
     */
    private void writeParameters(String startupScriptPath)
    throws TaskRunException {
        try {
            final PrintWriter out = new PrintWriter(
                new BufferedWriter(new FileWriter(startupScriptPath))
                );
            try {
                writeStartupScript(out);
            } finally {
                out.close();
            }
            if (out.checkError()) {
                throw new IOException("Error writing content; Disc full?");
            }
        } catch (IOException e) {
            throw new TaskRunException(
                "Error writing \"" + getStartupFileName() + "\"", e
                );
        }
    }

    /**
     * Executes the associated task using the parameters of this run.
     * @return The result of the execution.
     * @throws TaskRunException If task execution was aborted because of an error.
     */
    public final Result execute()
    throws TaskRunException {
        final String startupScriptPath =
            new File(outputDir, getStartupFileName()).getAbsolutePath();
        writeParameters(startupScriptPath);
        final String[] command = getStartupCommand(startupScriptPath);
        final ExternalProcess process = new ExternalProcess(outputDir, command, runLogger);
        updateEnvironment(process.environment());
        return readResultFile(monitorProcess(process));
    }

    private TaskRun getAbortRun() {
        final AbortRunFactory abortRunFactory = new AbortRunFactory(factory);
        try {
            return abortRunFactory.createWrapper(outputDir, runLogger);
        } catch (TaskRunException e) {
            runLogger.log(Level.WARNING,
                "Exception during instantiating abort wrapper", e
                );
            return null;
        }
    }

    /**
     * Abort task execution in progress.
     */
    public final void abort() {
        synchronized (this) {
            if (aborted) {
                // Abort already in progress.
                return;
            }
            aborted = true;
        }
        final TaskRun abortRun = getAbortRun();
        if (abortRun == null) {
            abortExternal();
        } else {
            final Thread thread = new Thread(new Runnable() {
                public void run() {
                    try {
                        abortRun.execute();
                    } catch (TaskRunException e) {
                        runLogger.log(Level.WARNING,
                            "Exception during running abort wrapper", e
                            );
                    } finally {
                        abortExternal();
                    }
                }
            }, "abort");
            synchronized (this) {
                abortThread = thread;
            }
            thread.start();
        }
    }

    public final void waitForCompletion() {
        final Thread thread;
        synchronized (this) {
            thread = abortThread;
        }
        if (thread != null) {
            runLogger.info("Waiting for abort to complete");
            try {
                thread.join();
            } catch (InterruptedException ex) {
                runLogger.log(Level.WARNING, "Waiting interrupted", ex);
            }
        }
    }

    public final boolean isAborted() {
        synchronized (this) {
            return aborted;
        }
    }

    private void abortExternal() {
        synchronized (this) {
            if (processes != null) {
                runLogger.info("Aborting external processes");
                for (final Iterator<ExternalProcess> iter = processes.keySet().iterator();
                    iter.hasNext();
                    ) {
                    final ExternalProcess process = iter.next();
                    try {
                        process.abort();
                    } catch (RuntimeException e) {
                        runLogger.log(Level.WARNING,
                            "Exception when trying to abort external process", e);
                    }
                    iter.remove();
                }
            }
        }
    }

    /**
     * Converts an arbitrary string to a valid environment variable name
     * by replacing invalid characters with special character (underscore).
     * @param name the string to be converted
     * @return the converted string
     */
    private static final String convertName(String name) {
        return name.replaceAll("\\W", "_").replaceFirst("^(?=\\d)", "X");
    }

    /**
     * Construct standard task environment consisting of special variables
     * starting with "SF_", input products (their locators) and task parameters
     * except those starting with "sf." (which are used internally).
     * @return Map containing standard task environment.
     */
    private final Map<String, Object> createTaskEnvironment() // NOPMD
    throws TaskRunException {
        final TaskRunnerConfig config = ConfigFactory.getConfig();
        final Map<String, Object> ret = new HashMap<>();
        ret.put("SF_REPORT_ROOT", outputDir.getAbsolutePath());
        ret.put("SF_PRODUCT_ROOT",
            new File(config.output.productBaseDir,
                runInfo.run.getJobPath() + "/").getAbsolutePath()
            );
        ret.put("SF_WRAPPER_ROOT",
            wrapperFile.getParentFile().getAbsolutePath());
        ret.put("SF_JOB_ID", runInfo.run.jobId);
        ret.put("SF_TASK_ID", runInfo.run.taskId);
        ret.put("SF_TARGET", runInfo.task.target);
        ret.put("SF_INPUTS", runInfo.inputs.keySet());
        final Map<String, Map<String, Map<String, String>>> combined = new HashMap<>();
        for (final InputInfo input : runInfo.inputs.values()) {
            ret.put(input.name, input.locator);
            if (input.isCombined()) {
                final Map<String, Map<String, String>> producers = new HashMap<>();
                for (final Map.Entry<String, ProducerInfo> entry : input.producers.entrySet()) {
                    final ProducerInfo info = entry.getValue();
                    final Map<String, String> producer = new HashMap<>();
                    producer.put("TASK", info.taskId);
                    producer.put("RESULT", info.result);
                    producer.put("LOCATOR", info.locator);
                    final String name = convertName(entry.getKey());
                    if (producers.put(name, producer) != null) {
                        throw new TaskRunException(
                            "Duplicate converted task name: " + name
                            );
                    }
                }
                combined.put(input.name, producers);
            }
        }
        if (!combined.isEmpty()) {
            ret.put("SF_PROD", combined);
        }
        // Conversion to TreeSet sorts the product names.
        // There are bound to be users who will expect the order to be the
        // same always even if our documentation does not promise that.
        ret.put("SF_OUTPUTS", new TreeSet<String>(runInfo.outputs));
        // TODO: There must be a better way of doing this.
        if (runInfo instanceof ExecuteRunInfo) {
            final ExecuteRunInfo execInfo = (ExecuteRunInfo)runInfo;
            ret.put("SF_RESOURCES", execInfo.resources.keySet());
            for (final ResourceInfo resource : execInfo.resources.values()) {
                ret.put(resource.ref, resource.locator);
            }
        }
        for (final Map.Entry<String, String> entry : runInfo.task.parameters.entrySet()) {
            final String name = entry.getKey();
            if (!name.startsWith("sf.")) {
                final String value = entry.getValue();
                ret.put(name, value);
            }
        }
        final String resultFileName = factory.getResultFileName();
        if (resultFileName != null) {
            ret.put("SF_RESULTS",
                new File(outputDir, resultFileName).getAbsolutePath()
                );
        }
        ret.put("SF_CC_URL",
            config.controlCenter.serverBaseURL.toExternalForm());
        ret.putAll(config.parameters);
        return ret;
    }

    /**
     * Standard handler for external processes.
     * Subclasses can use this for convenience.
     * @param process External process to monitor.
     * @return Exit value of the external process.
     */
    private int monitorProcess(ExternalProcess process)
    throws TaskRunException {
        synchronized (this) {
            processes.put(process, null);
        }
        try {
            try {
                process.start();
            } catch (IOException e) {
                throw new TaskRunException("Error executing wrapper", e);
            }
            try {
                final int result = process.waitFor();
                if (isAborted()) {
                    throw new AbortedException();
                }
                return result;
            } catch (InterruptedException e) {
                throw new TaskRunException(
                    "Interrupted while waiting for wrapper to finish", e
                    );
            }
        } finally {
            synchronized (this) {
                processes.remove(process);
            }
        }
    }

    /**
     * Read the result from a result file written by the framework or
     * from the framework exit code if the result file doesn't exist.
     * @param exitCode exit code do derive result from.
     */
    private Result readResultFile(int exitCode)
    throws TaskRunException {
        if (exitCode != 0) {
            return new Result(Result.ERROR, "wrapper exit code: " + exitCode);
        }
        final String resultFileName = factory.getResultFileName();
        if (resultFileName == null) {
            return new Result(Result.OK, null);
        }
        final File resultFile = new File(outputDir, resultFileName);
        if (!resultFile.exists()) {
            return new Result(
                Result.ERROR, "missing result file \"" + resultFileName + "\""
                );
        }
        try {
            return new Result(
                new BufferedReader(new FileReader(resultFile))
                );
        } catch (IOException e) {
            throw new TaskRunException(
                "Error reading result file \"" + resultFileName + "\": ", e
                );
        } catch (TaskRunException e) {
            throw new TaskRunException(
                "Error parsing result file \"" + resultFileName + "\": ", e
                );
        }
    }
}
