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

    /**
    Old name for "reportBaseURL", kept for backwards compatibility.
    */
    public URL outputBaseURL = DEFAULT_URL;

    /**
    Old name for "reportBaseDir", kept for backwards compatibility.
    */
    public File outputBaseDir = DEFAULT_FILE;

    /**
    Old name for "productBaseURL", kept for backwards compatibility.
    */
    public URL imageBaseURL = DEFAULT_URL;

    /**
    Old name for "productBaseDir", kept for backwards compatibility.
    */
    public File imageBaseDir = DEFAULT_FILE;

    public void verify()
    throws ParseException {
        // Backwards compatibility with the time the term "output" was used
        // instead of "report".
        if (reportBaseURL == DEFAULT_URL) { // NOPMD
            if (outputBaseURL == DEFAULT_URL) { // NOPMD
                throw new ParseException(
                    "No value specified for \"reportBaseURL\""
                    );
            } else {
                reportBaseURL = outputBaseURL;
            }
        }
        if (reportBaseDir == DEFAULT_FILE) { // NOPMD
            if (outputBaseDir == DEFAULT_FILE) { // NOPMD
                throw new ParseException(
                    "No value specified for \"reportBaseDir\""
                    );
            } else {
                DataChecker.checkExistingDirectory(
                    outputBaseDir, "outputBaseDir"
                    );
                reportBaseDir = outputBaseDir;
            }
        }
        // Backwards compatibility with the time the term "image" was used
        // instead of "product".
        if (productBaseURL == DEFAULT_URL) { // NOPMD
            if (imageBaseURL == DEFAULT_URL) { // NOPMD
                throw new ParseException(
                    "No value specified for \"productBaseURL\""
                    );
            } else {
                productBaseURL = imageBaseURL;
            }
        }
        if (productBaseDir == DEFAULT_FILE) { // NOPMD
            if (imageBaseDir == DEFAULT_FILE) { // NOPMD
                throw new ParseException(
                    "No value specified for \"productBaseDir\""
                    );
            } else {
                DataChecker.checkExistingDirectory(
                    imageBaseDir, "imageBaseDir"
                    );
                productBaseDir = imageBaseDir;
            }
        }

        DataChecker.checkExistingDirectory(reportBaseDir, "reportBaseDir");
        DataChecker.checkExistingDirectory(productBaseDir, "productBaseDir");
    }

}
