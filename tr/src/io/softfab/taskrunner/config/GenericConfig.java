// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner.config;

import java.util.logging.Level;

import io.softfab.xmlbind.DataObject;
import io.softfab.xmlbind.ParseException;

public class GenericConfig implements DataObject {

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
    }
}
