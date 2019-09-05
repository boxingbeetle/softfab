// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner;

import java.net.InetAddress;
import java.net.UnknownHostException;
import java.util.logging.Logger;

import io.softfab.taskrunner.config.ConfigFactory;
import io.softfab.taskrunner.config.TaskRunnerConfig;

/**
 * Synchronizes between SyncLoop and TaskRunThread.
 */
final class RunStatus {

    private final TaskRunnerConfig taskRunnerConfig;

    /**
     * TODO: This is more than a trigger, it also guards runInfo.
     */
    private final Object trigger = new Object();

    private final Logger logger;
    private TaskRunThread taskRunThread;
    private TaskRunInfo runInfo;

    public RunStatus(Logger logger) {
        this.logger = logger;

        // Get relevant configuration sections.
        taskRunnerConfig = ConfigFactory.getConfig();
    }

    /**
     * Wait until the current task ends or a timeout expires, whichever comes
     * first.
     * @param timeout Timeout in milliseconds.
     */
    public void delay(int timeout) {
        if (timeout != 0) {
            try {
                synchronized (trigger) {
                    trigger.wait(timeout);
                }
            } catch (InterruptedException e) {
                // Wake up!
            }
        }
    }

    /**
     * Called by TaskRunThread to indicate that a new task run has started.
     * This method should be called on the main thread, just before the
     * internal thread of TaskRunThread starts.
     */
    void runStarted(TaskRunThread newThread, TaskRunInfo newRun) {
        final boolean alreadyRunning;
        synchronized (trigger) {
            alreadyRunning = taskRunThread != null;
        }
        if (alreadyRunning) {
            logger.severe("Previous task was not yet done");
        }
        taskRunThread = newThread;
        runInfo = newRun;
    }

    /**
     * Called by TaskRunThread to indicate that the task run has finished.
     */
    void runFinished(RunFactory factory, Result result) {
        // The request should be created and queued as an atomic action, since
        // a Synchronize call made before the TaskDone call must report that
        // the task is still running and a Synchronize call made after the
        // TaskDone call must report that no task is running.
        synchronized (trigger) {
            taskRunThread = null;
            runInfo = null;
            // TODO: Try to remove duplication between reportResult
            //       implementations by moving code here or to TaskRunThread.
			if (result.getCode() != Result.IGNORE) {
				factory.reportResult(result);
			}
            trigger.notifyAll();
        }
    }

    /**
     * Starts a new task run.
     * @param newRunInfo Specification of the task to run.
     */
    public void startTask(TaskRunInfo newRunInfo) {
        new TaskRunThread(newRunInfo, logger, this);
    }

    /**
     * Aborts the task run in progress.
     */
    public void abortTask() {
        synchronized (trigger) {
            if (taskRunThread == null) {
                // The run already ended, no point in aborting.
                return;
            }
            taskRunThread.abortTask();
        }
    }

    public void submitSync(ServerReplyListener listener) {
        String hostName;
        try {
            hostName = InetAddress.getLocalHost().getHostName();
        } catch (UnknownHostException e) {
            hostName = "unknown-host";
        }
        // The request should be created and queued as an atomic action, since
        // a TaskDone call made after we create the request and before the
        // server receives it would invalidate the request that says the
        // run is still running.
        synchronized (trigger) {
            final StringBuffer request = new StringBuffer(200);
            request.append("<request host=\"").append(hostName)
                .append("\" runnerVersion=\"").append(Version.getVersion())
                .append("\">\r\n");
            if (runInfo != null) {
                request.append(runInfo.getRunIdAsXML()).append("\r\n");
            }
            request.append("</request>\r\n");
            ControlCenter.INSTANCE.submitRequest(
                new ServerXMLRequest("Synchronize", request.toString()),
                listener
                );
        }
    }

}
