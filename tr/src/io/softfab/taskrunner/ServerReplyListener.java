// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner;

import java.io.IOException;
import java.io.InputStream;

public interface ServerReplyListener {
    /**
     * Called when the request has succeeded.
     * @param in Stream to read the reply from. Do not close it.
     * @throws IOException When reading the reply fails.
     *   The request will be retried if this happens. If that is not what
     *   you want, you have to intercept the exception.
     */
    void serverReplied(InputStream in)
    throws IOException;

    /**
     * Called when the request has permanently failed.
     * On transient failures the request will be retried, so if you receive
     * this callback you can conclude that the problem is not likely to go
     * away if you try again.
     * @param e Exception object which contains details about the failure.
     */
    void serverFailed(PermanentRequestFailure e);
}
