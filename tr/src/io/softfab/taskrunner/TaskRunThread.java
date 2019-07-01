// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner;

import java.io.File;
import java.io.IOException;
import java.util.logging.FileHandler;
import java.util.logging.Level;
import java.util.logging.Logger;

import io.softfab.taskrunner.config.ConfigFactory;

/**
 * Controls the execution a single task on a worker thread.
 * As much as possible, the setup is done on the main thread; this simplifies
 * things by reducing the amount of parallelism.
 */
final class TaskRunThread implements Runnable {

    /**
     * Specifies the running task.
     */
    private final TaskRunInfo runInfo;

    /**
     * Log of the Task Runner itself.
     */
    private final Logger logger;

    /**
     * Log of the task run and its external processes.
     */
    private Logger runLogger;

    /**
     * Handler which writes the messages of runLogger to file.
     * TODO: Do we really have to close the handler explicitly?
     */
    private FileHandler fileHandler;

    private final RunStatus runStatus;

    private final RunFactory factory;

    private TaskRun taskRun;

    public TaskRunThread(
            TaskRunInfo runInfo, Logger logger, RunStatus runStatus
        ) {
        logger.info(
            "Task \"" + runInfo.run.taskId + "\": starting " +
            runInfo.getActionText()
            );
        this.runInfo = runInfo;
        this.logger = logger;
        this.runStatus = runStatus;
        factory = runInfo.getRunFactory(logger);

        start();
    }

    /**
     * Called on the main thread to abort the currently executing run.
     * The abort will be handled asynchronously.
     */
    public void abortTask() {
        final TaskRun run;
        synchronized (this) {
            run = taskRun;
        }
        // The run will be null if already finished.
        if (run != null) {
            run.abort();
        }
    }

    /**
     * Starts execution of the task run.
     * If all goes well, a worker thread will be spawned that deals with the
     * execution while the main thread returns to the sync loop.
     * In any case, finish() will be called eventually.
     */
    private void start() {
        try {
            startHelper();
        } catch (TaskRunException e) {
            // Worker thread not started, so we should report the result here
            // in the main thread.
            finish(e.toResult());
            return;
        }
        runStatus.runStarted(this, runInfo);
        new Thread(this, "task run").start();
    }

    private void startHelper()
    throws TaskRunException {
        final File outputDir = new File(
            ConfigFactory.getConfig().output.reportBaseDir,
            runInfo.run.getJobPath() + "/" + runInfo.run.taskId + "/"
            );
        factory.createWorkEnv(outputDir);

        // Create new logger for this task run.
        runLogger = Logger.getAnonymousLogger();
        // Do not send messages to root logger.
        // The user who started the task will not be looking at the console,
        // so printing there only wastes performance and hides the messages
        // that are important to the operator.
        runLogger.setUseParentHandlers(false);
        // TODO: Fixed level?
        //       Use Task Runner's own logger level?
        //       Separate configurable level?
        runLogger.setLevel(Level.INFO);

        // Send logger output to file.
        try {
            final File logFile = new File(outputDir, factory.getLogFileName());
            fileHandler = new FileHandler(logFile.getAbsolutePath());
        } catch (IOException e) {
            throw new TaskRunException("Could not create log file", e);
        }
        fileHandler.setFormatter(new PlainFormatter());
        runLogger.addHandler(fileHandler);
        // TODO: Make SEVERE messages fall through to main task runner log?
        runLogger.info("Task Runner version " + Version.getVersion());

        final TaskRun run;
        try {
            run = factory.createWrapper(outputDir, runLogger);
        } catch (TaskRunException ex) {
            final Throwable cause = ex.getCause();
            if (cause != null) {
                logger.log(
                    Level.WARNING,
                    "Error creating wrapper for " +
                    "\"" + factory.getWrapperName() + "\"",
                    cause
                    );
            }
            throw ex;
        }
        if (run == null) {
            final String message =
                "No wrapper implementation found for " +
                "wrapper \"" + factory.getWrapperName() + "\"";
            runLogger.info(message);
            throw new TaskRunException(message);
        }
        synchronized (this) {
            taskRun = run;
        }
    }

    public void run() {
        Result result;
        try {
            // Actual execution.
            result = taskRun.execute();
            logger.info(
                "Task \"" + runInfo.run.taskId + "\": finished " +
                runInfo.getActionText()
                );
        } catch (AbortedException e) {
            runLogger.info("Task run aborted");
            result = e.toResult();
        } catch (TaskRunException e) {
            runLogger.log(Level.WARNING, "Task run terminated", e);
            result = e.toResult();
        } catch (Exception e) {
            logger.log(
                Level.SEVERE, "Internal error occurred in " +
                "task run \"" + runInfo.run.taskId + "\" " +
                "of job " + runInfo.run.jobId + ":", e
                );
            result = new Result(
                Result.ERROR,
                "Task run failed because of error in Task Runner: " + e
                );
        }
        String summary = result.getSummary();
        if (summary == null) {
            summary = "(no summary)";
        }
        if (result.getCode() == Result.ERROR) {
            logger.warning("Task run failed: " + summary);
        } else {
            logger.info("Task run finished: " + summary);
        }
        finish(result);
    }

    private void finish(Result result) {
        // First, set taskRun field to null to indicate run is finished and can
        // no longer be aborted.
        final TaskRun run;
        synchronized (this) {
            run = taskRun;
            taskRun = null;
        }

        // The run object does not exist if starting failed at an early stage.
        if (run != null) {
            // Wait for abort thread (if any) to end.
            run.waitForCompletion();
        }

        // Close log file, if it was opened.
        if (fileHandler != null) {
            fileHandler.close();
        }

        // Inform Control Center and sync thread.
        runStatus.runFinished(factory, result);
    }

}
