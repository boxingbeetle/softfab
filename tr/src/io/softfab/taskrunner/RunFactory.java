// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner;

import java.io.File;
import java.io.FilenameFilter;
import java.io.IOException;
import java.lang.reflect.InvocationTargetException;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.logging.Logger;

import io.softfab.taskrunner.config.ConfigFactory;
import io.softfab.taskrunner.config.OutputConfig;
import io.softfab.taskrunner.config.TaskRunnerConfig;
import io.softfab.taskrunner.config.WrappersConfig;

abstract public class RunFactory {

    protected final Logger logger;
    protected final TaskRunInfo runInfo;

    protected final OutputConfig outputConfig;
    private final List<WrappersConfig> wrappersBaseDirList;

    public RunFactory(Logger logger, TaskRunInfo info) {
        this.logger = logger;
        final TaskRunnerConfig config = ConfigFactory.getConfig();
        outputConfig = config.output;
        wrappersBaseDirList = config.wrappers;
        runInfo = info;
    }

    /**
     * Setups up the working environment for the run.
     * @throws TaskRunException
     */
    abstract protected void createWorkEnv(File outputDir)
    throws TaskRunException;

    /**
     * Returns the file name of the Task Runner log for this type of run.
     */
    abstract protected String getLogFileName();

    /**
     * Reports a task result to the web server.
     */
    abstract protected void reportResult(Result result);

    abstract protected String getStartupFileBaseName();

    /**
     * Returns the file name of the results file used by this run type.
     * @return File name, or null if this run type does not write result files.
     */
    abstract protected String getResultFileName();

    /**
     * Gets the part of the file name that defines wrappers of this type.
     * For example, if wrappers are called "wrapper.sh", "wrapper.bat" etc,
     * this method should return "wrapper".
     */
    abstract protected String getWrapperFileNameBase();

    protected String getWrapperName() {
        return runInfo.task.parameters.get("sf.wrapper");
    }

    private static class TaskRunFactory {

        private final String fileExtension;

        private final Class<? extends TaskRun> wrapperClass;

        public TaskRunFactory(String ext, Class<? extends TaskRun> cls) {
            fileExtension = ext;
            wrapperClass = cls;
        }

        public TaskRun createTaskRun(String[] wrappers, File wrapperDir,
                File outputDir, RunFactory factory, Logger runLogger)
        throws TaskRunException {
            for (final String wrapper : wrappers) {
                if (wrapper.endsWith(fileExtension)) {
                    Throwable throwable = null;
                    try {
                        return (TaskRun)wrapperClass.getConstructor(
                            new Class<?>[] {
                                File.class, File.class,
                                RunFactory.class, Logger.class
                            }
                        ).newInstance(new Object[] {
                            new File(wrapperDir, wrapper),
                            outputDir, factory, runLogger
                        });
                    } catch (SecurityException e) {
                        throwable = e;
                    } catch (NoSuchMethodException e) {
                        throwable = e;
                    } catch (IllegalArgumentException e) {
                        throwable = e;
                    } catch (InstantiationException e) {
                        throwable = e;
                    } catch (IllegalAccessException e) {
                        throwable = e;
                    } catch (InvocationTargetException e) {
                        throwable = e.getCause();
                    }
                    if (throwable != null) {
                        throw new TaskRunException("Failed to instantiate " +
                            "generic wrapper factory class", throwable);
                    }
                }
            }
            return null;
        }
    }

    private static final List<TaskRunFactory> factories;
    static {
        factories = new ArrayList<>();
        final boolean windows = File.separatorChar == '\\';
        if (windows) {
            factories.add(new TaskRunFactory(".bat", BatchRun.class));
        }
        factories.add(new TaskRunFactory(".sh", ScriptRun.class));
        factories.add(new TaskRunFactory(".mk", MakeRun.class));
        factories.add(new TaskRunFactory(".pl", PerlRun.class));
        factories.add(new TaskRunFactory(".py", PythonRun.class));
        factories.add(new TaskRunFactory(".rb", RubyRun.class));
        factories.add(new TaskRunFactory(".xml", AntRun.class));
        factories.add(new TaskRunFactory(".build", NAntRun.class));
        if (windows) {
            for (final String extension : WshRun.LANGUAGES.keySet()) {
                factories.add(new TaskRunFactory(extension, WshRun.class));
            }
        }
    }

    /**
     * Prepares execution of a wrapper.
     * @param outputDir Report directory.
     * @param runLogger Logger of this task run.
     * @return TaskRun object corresponding to the wrapper type,
     *   or null if no matching wrapper was found.
     * @throws TaskRunException If the TaskRun object could not be created.
     */
    public final TaskRun createWrapper(File outputDir, Logger runLogger)
    throws TaskRunException {
        final String wrapper = getWrapperName();
        for (final WrappersConfig wrappersConfig : wrappersBaseDirList) {
            File wrapperDir = new File(wrappersConfig.dir, wrapper);
            if (wrapperDir.isDirectory()) {
                try {
                    wrapperDir = wrapperDir.getCanonicalFile();
                } catch (IOException e) {
                    throw new TaskRunException(
                        "Error canonicalizing wrappers dir", e
                        );
                }
                final String wrappers[] = wrapperDir.list(new FilenameFilter() {
                    private String WRAPPER_BASE = getWrapperFileNameBase();
                    public boolean accept(File dir, String name) {
                        return name.lastIndexOf('.') == WRAPPER_BASE.length()
                            && name.startsWith(WRAPPER_BASE);
                    }
                });
                for (final TaskRunFactory factory : factories) {
                    final TaskRun newRun = factory.createTaskRun(
                        wrappers, wrapperDir, outputDir, this, runLogger
                        );
                    if (newRun != null) {
                        return newRun;
                    }
                }
            }
        }
        // Wrappers can be optional (for example the abort wrapper),
        // so returning null is better than throwing an exception.
        return null;
    }

}
