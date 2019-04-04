// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner;

import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.Reader;
import java.util.logging.Logger;


/**
 * Listener which logs the outcome of a server request and does nothing
 * more.
 * Useful for API calls of which the returned value is unimportant.
 */
public class APIReplyListener
implements ServerReplyListener {

    private final Logger runLogger;
    private final String description;

    public APIReplyListener(Logger runLogger, String description) {
        this.runLogger = runLogger;
        this.description = description;
    }

    public void serverReplied(InputStream in)
    throws IOException {
        // Read the response.
        final Reader reader = new InputStreamReader(in);
        final StringBuffer response = new StringBuffer();
        try {
            final char[] buf = new char[512];
            while (true) {
                final int charsRead = reader.read(buf);
                if (charsRead == -1) {
                    break;
                }
                response.append(buf, 0, charsRead);
            }
        } finally {
            reader.close();
        }

        // Handle the response.
        // TODO: A standardized format for the returned value would be
        //       useful, so we can do more than just printing it.
        runLogger.fine(
            "Succeeded to " + description + ", server replied: " + response
            );
    }

    public void serverFailed(PermanentRequestFailure e) {
        runLogger.severe("Failed to " + description + ": " + e.getMessage());
    }

}
