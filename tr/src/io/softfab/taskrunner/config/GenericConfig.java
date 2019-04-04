// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner.config;

import java.util.logging.Level;

import io.softfab.xmlbind.DataObject;
import io.softfab.xmlbind.ParseException;

public class GenericConfig implements DataObject {

    /**
    String containing allowed characters in TaskRunnerId.
    */
    private final static String VALID_ID_CHARS =
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-+_ ";

    /**
    Unique task runner identifier (used in combination with host name).
    */
    public String taskRunnerId;

    /**
    Log level for the main task runner logger.
    */
    public String logFile;

    /**
    Log level for the main task runner logger.
    */
    public Level logLevel;

    /**
    Path to the windows wrapper to kill external processes.
    */
    public String processWrapper;

    public void verify()
    throws ParseException {
        // TODO: Use regexp instead.
        final String upperId = taskRunnerId.toUpperCase();
        for (int i = 0; i < taskRunnerId.length(); i++) {
            if (VALID_ID_CHARS.indexOf(upperId.charAt(i)) < 0) {
                throw new ParseException(
                    "taskRunnerId parameter contains illegal character"
                    );
            }
        }
        if (taskRunnerId.length() <= 0) {
            throw new ParseException(
                "taskRunnerId parameter must not be empty"
                );
        }
    }
}
