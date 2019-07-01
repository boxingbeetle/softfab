// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner.config;

import java.io.File;
import java.net.MalformedURLException;
import java.net.URL;

import io.softfab.xmlbind.DataChecker;
import io.softfab.xmlbind.DataObject;
import io.softfab.xmlbind.ParseException;

public class OutputConfig implements DataObject {

    private final static URL DEFAULT_URL;
    static {
        try {
            DEFAULT_URL = new URL("http://localhost/default/");
        } catch (MalformedURLException e) {
            // Escalate.
            throw new RuntimeException(e); // NOPMD
        }
    }

    private final static File DEFAULT_FILE = new File("/default");

    /**
    Base URL of the directory to which the output files are written.
    */
    public URL reportBaseURL = DEFAULT_URL;

    /**
    Directory to which the output files are written.
    */
    public File reportBaseDir = DEFAULT_FILE;

    /**
    Base URL of the directory where created products can be fetched from.
    */
    public URL productBaseURL = DEFAULT_URL;

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
