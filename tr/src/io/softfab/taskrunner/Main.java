// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner;

import java.io.File;
import java.io.IOException;
import java.net.MalformedURLException;
import java.net.URL;
import java.util.logging.FileHandler;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.Logger;

import io.softfab.taskrunner.config.ConfigFactory;
import io.softfab.taskrunner.config.TaskRunnerConfig;
import io.softfab.xmlbind.ParseException;

/**
Command-line entry point for task runner program.
*/
public final class Main {

    private Main() {
        // Prevent instantiation.
    }

    private static Logger logger;

    public static void main(String[] args) {
        // Initialise logger.
        logger = Logger.getLogger("io.softfab.taskrunner");
        final Handler[] rootHandlers = logger.getParent().getHandlers();
        for (int i = 0; i < rootHandlers.length; i++) {
            rootHandlers[i].setFormatter(new PlainFormatter());
        }
        // Later log level will be set according to task runner config.
        logger.setLevel(Level.INFO);
        // TODO: On level SEVERE, alert the fab operator (by e-mail?).
        logger.info("Task Runner version " + Version.getVersion());

        // Parse configuration files.
        String configFile;
        if (args.length > 0) {
            configFile = args[0];
        } else {
            configFile = "config.xml";
        }
        logger.info("Parsing configuration: " + configFile);
        try {
            ConfigFactory.init(new File(configFile));
        } catch (IOException e) {
            fatalError("Error reading configuration file: " + e);
        } catch (ParseException e) {
            fatalError("Error parsing configuration file: " + e.getMessage());
        }

        final TaskRunnerConfig config = ConfigFactory.getConfig();

        if (config.generic.logFile.length() > 0) {
            // Send logger output to file.
            try {
                final FileHandler fh = new FileHandler(config.generic.logFile);
                fh.setFormatter(new PlainFormatter());
                logger.addHandler(fh);
            } catch (IOException e) {
                fatalError("Error creating log file: " + e);
            }
        }

        // If the server base URL does not end with a '/', patch it.
        final URL serverBaseURL = config.controlCenter.serverBaseURL;
        final String serverBaseFile = serverBaseURL.getFile();
        if (serverBaseFile.lastIndexOf('/') + 1 != serverBaseFile.length()) {
            URL newURL;
            try {
                newURL = new URL(serverBaseURL, serverBaseFile + '/');
            } catch (MalformedURLException e) {
                fatalError("Unable to create a correct serverURL" + e);
                return; // Unreachable, but compiler doesn't know that.
            }
            config.controlCenter.serverBaseURL = newURL;
        }

        // Set user-defined log level.
        logger.setLevel(config.generic.logLevel);

        logger.info("Connecting to " + config.controlCenter.serverBaseURL);
        logger.info("Token ID: " + config.controlCenter.tokenId);

        // Run main loop.
        final SyncLoop syncLoop = new SyncLoop();
        logger.info("Entering synchronization loop");
        syncLoop.mainLoop();
        logger.info("Exit from synchronization loop");
        System.exit(0);
    }

    /** Prints an error message and exits task runner.
      */
    private static void fatalError(String message) {
        logger.severe(message);
        System.exit(2);
    }
}
