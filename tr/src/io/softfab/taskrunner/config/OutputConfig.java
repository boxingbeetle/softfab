// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner.config;

import java.io.File;

import io.softfab.xmlbind.DataChecker;
import io.softfab.xmlbind.DataObject;
import io.softfab.xmlbind.ParseException;

public class OutputConfig implements DataObject {

    private final static File DEFAULT_FILE = new File("/default");

    /**
    Directory to which the output files are written.
    */
    public File reportBaseDir = DEFAULT_FILE;

    /**
    Directory where created products are stored.
    */
    public File productBaseDir = DEFAULT_FILE;

    public void verify()
    throws ParseException {
        DataChecker.checkExistingDirectory(reportBaseDir, "reportBaseDir");
        DataChecker.checkExistingDirectory(productBaseDir, "productBaseDir");
    }

}
