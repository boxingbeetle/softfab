// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner;

import java.io.BufferedReader;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.util.Arrays;
import java.util.logging.Level;
import java.util.logging.Logger;

import io.softfab.taskrunner.config.ConfigFactory;

/**
Utility class that reads stdout and stderr from an external process
and logs the lines that are read.
For every external process execution a new ExternalProcess object
should be created.
The life cycle is: construction ; ( start ; ( waitFor | abort ) )*,
a state transition occurs if the associated method returns successfully.
This class was not designed for concurrent use by multiple threads.
*/
public class ExternalProcess {

    private static final String processWrapper;

    static {
        final String wrapper =
            ConfigFactory.getConfig().generic.processWrapper.trim();
        if (wrapper.length() > 0) {
            processWrapper = wrapper;
        } else {
            processWrapper = null;
        }
    }

    private final String[] arguments;

    private Process process;

    private File workingDir;

    /**
    Tracks whether the external process is running right now.
    Used for life cycle checks.
    */
    private boolean running;

    /**
    Logger to which process status messages and process output is sent.
    This logger is intended for users.
    */
    protected Logger logger;

    /**
    Logger to which only raw process output is sent.
    This logger is intended for automatic process monitoring.
    */
    protected Logger rawLogger;

    private Forwarder errForwarder;
    private Forwarder outForwarder;

    /**
     * Creates an external process monitor.
     * @param args Command line arguments.
     * @param logger Logger to pass read lines to.
     */
    public ExternalProcess(File workingDir, String[] args, Logger logger) {
        this.workingDir = workingDir;
        this.logger = logger;
        rawLogger = Logger.getAnonymousLogger();
        rawLogger.setUseParentHandlers(false);
        rawLogger.setLevel(Level.INFO);
        running = false;

        final int destIndex;
        if (processWrapper == null) {
            arguments = new String[args.length];
            destIndex = 0;
        } else {
            arguments = new String[args.length + 1];
            arguments[0] = processWrapper;
            destIndex = 1;
        }
        System.arraycopy(args, 0, arguments, destIndex, args.length);
    }

    /**
    Start the external process and the logging of its output.
    @throws IOException If executing the command line failed.
    @throws IllegalStateException If the process was already running.
    */
    public void start()
    throws IOException {
        checkRunning(false);

        logger.info("Starting wrapper: " + Arrays.toString(arguments));
        final ProcessBuilder builder = new ProcessBuilder(arguments);
        builder.directory(workingDir);
        try {
            process = builder.start();
        } catch (IOException e) {
            logger.severe("Wrapper execution failed: " + e);
            throw e;
        }

        running = true;
        // TODO: It seems to be impossible to both know the origin and get
        //       messages in the right order.
        //       Consider whether we should switch to a single level in the
        //       right order.
        errForwarder = new Forwarder(process.getErrorStream(), Level.WARNING);
        outForwarder = new Forwarder(process.getInputStream(), Level.INFO);
    }

    /**
    Abort the external process.
    @throws IllegalStateException If the process was not running.
    */
    public void abort() {
        checkRunning(true);
        logger.info("Aborting wrapper");
        process.destroy();
        // TODO: On POSIX-like systems abort is asynchronous, so when we
        //       immediately check it is very unlikely the process is already
        //       aborted.
        try {
            logger.fine("The wrapper has been aborted, the exit code is: " +
                process.exitValue());
        } catch (IllegalThreadStateException ex) {
            logger.warning("The wrapper is still running");
        }
        running = false;
        // TODO: Check what happens to Forwarder threads.
        //       Probably they'll get EOF or IOException and finish
        //       automatically.
        //       Check that they actually finish and the messages logged
        //       make sense for an aborted process.
    }

    /**
    Wait for the external process to finish.
    TODO: Mandatory timeout.
    @return Exit code of the external process.
    @throws InterruptedException If thread is interrupted while waiting
        for the external process to finish.
    @throws IllegalStateException If the process was not running.
    */
    public int waitFor()
    throws InterruptedException {
        checkRunning(true);
        try {
            final int exitValue = process.waitFor();
            errForwarder.waitFor();
            outForwarder.waitFor();
            running = false;
            logger.info(
                "Finished wrapper, exit value: " + exitValue
                );
            return exitValue;
        } catch (InterruptedException e) {
            logger.info("Interrupted while waiting for wrapper to end");
            throw e;
        }
    }

    /**
    Verify the running state of the process.
    @param shouldBeRunning The correct running state.
    @throws IllegalStateException If the process running state was wrong.
    */
    private void checkRunning(boolean shouldBeRunning) {
        if (running != shouldBeRunning) {
            throw new IllegalStateException(
                "Wrapper " + (running ? "already" : "not") + " running"
                );
        }
    }

    private class Forwarder implements Runnable {

        private final BufferedReader in;
        private final Thread thread;
        private final Level level;

        /**
        Creates a log forwarder for a single input stream
        and starts reading from that stream.
        @param in Stream to read lines from.
        @param level Level at which to log lines.
        */
        Forwarder(InputStream in, Level level) {
            this.in = new BufferedReader(new InputStreamReader(in));
            this.level = level;
            thread = new Thread(this);
            thread.start();
        }

        /**
        Forwards log message from the input stream to the logger,
        until end of input is reached.
        Used by internal thread, do not call yourself.
        */
        public void run() {
            try {
                while (true) {
                    final String line = in.readLine();
                    if (line == null) {
                        // EOF: we're done.
                        return;
                    }
                    logger.log(level, line);
                    rawLogger.log(level, line);
                }
            } catch (IOException e) {
                logger.warning("Logging of wrapper output aborted: " + e);
            }
        }

        /**
        Wait for this forwarder to end its work
        (EOF or IOException from process).
        */
        public void waitFor()
        throws InterruptedException {
            thread.join();
        }
    }

}
