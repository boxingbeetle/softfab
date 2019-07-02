// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.MalformedURLException;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Base64;
import java.util.List;
import java.util.logging.Level;
import java.util.logging.Logger;

import io.softfab.taskrunner.config.ConfigFactory;
import io.softfab.taskrunner.config.ControlCenterConfig;

/**
 * Communicates with the Control Center (server).
 * This class is final since it starts a thread in its constructor, which would
 * cause the thread to run on a partially initialized object if this class is
 * ever subclassed.
 */
public final class ControlCenter
implements Runnable {

    /**
     * Singleton instance.
     * TODO: Maybe it is better not to make it a singleton, so we can better
     *       control access to it.
     *       This is especially important to ensure TaskDone and Synchronize
     *       are always called with the right info respective to their order
     *       of calling.
     *       Simpler said: RunStatus seems to be the only class that can
     *       submit requests without a risk of them being submitted in the
     *       wrong order.
     */
    public static final ControlCenter INSTANCE = new ControlCenter();

    private static final Logger logger =
        Logger.getLogger("io.softfab.taskrunner");

    /**
     * Number of milliseconds to wait before retrying a request to the
     * Control Center.
     */
    private static final int RETRY_DELAY = 10000;

    private final URL serverBaseURL;
    private final String authorization;

    private final List queue = new ArrayList();

    /**
     * Worker thread.
     */
    private final Thread thread;

    /**
     * Should the main worker thread continue to wait for new requests?
     * Acquire the monitor of "queue" before modifying this field.
     */
    private boolean running = true;

    private ControlCenter() {
        // Get relevant configuration sections.
        ControlCenterConfig config = ConfigFactory.getConfig().controlCenter;
        serverBaseURL = config.serverBaseURL;
        authorization = "Basic " + Base64.getEncoder().encodeToString(
            (config.tokenId + ":" + config.tokenPass).getBytes(
                StandardCharsets.US_ASCII
                )
            );

        // Start worker thread.
        thread = new Thread(this, "Control Center communication");
        thread.start();
    }

    /**
     * Queues a request to the Control Center.
     * @param request The request.
     * @param listener Listener that will be called when the request has either
     *   succeeded or failed permanently.
     */
    public void submitRequest(
            ServerRequest request, ServerReplyListener listener
        ) {
        synchronized (queue) {
            queue.add(new QueuedRequest(request, listener));
            queue.notifyAll();
        }
    }

    /**
     * Implementation of Runnable interface, called by private worker thread.
     * Do not call this yourself.
     */
    public void run() {
        while (true) {
            // Get a request from the head of the queue.
            // Note: Sun JDK (tested 1.5.0 and 1.6.0) fails to compile this with
            //       the "final" modifier.
            /*final*/ QueuedRequest queuedRequest;
            synchronized (queue) {
                while (queue.isEmpty()) {
                    if (!running) {
                        return;
                    }
                    try {
                        queue.wait();
                    } catch (InterruptedException e) {
                        // Check the running flag again.
                    }
                }
                queuedRequest = (QueuedRequest)queue.get(0);
            }

            // Try sending the request.
            boolean retry = false;
            try {
                final InputStream in = queuedRequest.execute();
                queuedRequest.serverReplied(in);
            } catch (IOException e) {
                // Transient I/O error.
                logger.warning(
                    "Transient error sending request to Control Center: " +
                    e.getMessage()
                );
                final StringBuffer err = new StringBuffer("");
                final StackTraceElement[] stack = e.getStackTrace();
                for (int i = 0; i < stack.length; i++) {
                    err.append(stack[i].toString());
                    err.append('\n');
                }
                logger.severe(err.toString());
                retry = true;
                try {
                    // Avoid overloading the server with failing requests.
                    Thread.sleep(RETRY_DELAY);
                } catch (InterruptedException iex) {
                    // Check the running flag again.
                }
            } catch (PermanentRequestFailure e) {
                // Permanent error.
                logger.warning(
                    "Permanent error sending request to Control Center: " +
                    e.getMessage()
                    );
                queuedRequest.serverFailed(e);
            }

            if (!retry) {
                // Remove request from queue.
                synchronized (queue) {
                    queue.remove(0);
                }
            }
        }
    }

    /**
     * Shuts down the communication with the Control Center.
     * Waits for the currently queued requests to be handled before returning.
     */
    public void exit() {
        logger.fine("Waiting for Control Center communication thread to end");
        synchronized (queue) {
            running = false;
        }
        try {
            // Wait for the worker thread to finish processing what was already
            // in the queue.
            thread.interrupt();
            thread.join();
        } catch (InterruptedException e) {
            // Exit immediately.
        }
        logger.fine("Control Center communication thread has ended");
    }

    /**
     * Establishes connection with Control Center and sends request.
     * @param request The request to make.
     * @return A stream from which the Control Center reply can be read.
     *   Remember to close it when you are done reading.
     * @throws IOException If a transient error happens connecting or sending.
     * @throws PermanentRequestFailure If this request failed and has little
     *   chance of succeeding by retrying.
     */
    private InputStream sendRequest(ServerRequest request)
    throws IOException, PermanentRequestFailure {
        // Get info from request object.
        final String page = request.getPage();
        final String query = request.getQuery();
        final String bodyType = request.getBodyType();
        final String body = request.getBody();

        // Construct URL.
        final URL url;
        try {
            final URL baseURL = new URL(serverBaseURL, page);
            url = query == null
                ? baseURL
                : new URL(baseURL.toExternalForm() + '?' + query);
        } catch (MalformedURLException e) {
            // If this happens, it should be considered an internal error of
            // the Task Runner.
            throw new PermanentRequestFailure(
                "Request URL is invalid: " + e.getMessage(), e
                );
        }

        // Initiate the connection.
        // Note: It is not documented exactly what happens in openConnection,
        //       so we don't know whether to treat it like a transient or
        //       permanent error. We treat it as transient.
        final HttpURLConnection connection =
            (HttpURLConnection)url.openConnection();
        // All calls we currently do change state on the server and should
        // therefore made as POST.
        connection.setRequestMethod("POST");
        // Pass token credentials using HTTP Basic authentication.
        connection.setRequestProperty("Authorization", authorization);
        if (bodyType != null) {
            assert body != null;
            connection.setRequestProperty("Content-Type", bodyType);
            connection.setDoOutput(true);
            connection.setDoInput(true);
            final OutputStream output = connection.getOutputStream();
            output.write(body.getBytes());
            output.flush();
            output.close();
        }
        // This implicitly connects.
        final int responseCode = connection.getResponseCode();
        String responseMessage = connection.getResponseMessage();
        if (responseMessage == null) {
            responseMessage = "(no message)";
        }
        switch (responseCode) {
        case HttpURLConnection.HTTP_INTERNAL_ERROR:
            // It is very likely that repeating this request will trigger
            // the same error over and over again, so give up now.
            throw new PermanentRequestFailure(
                "Server encountered an internal error processing " +
                "the request"
                );
        case HttpURLConnection.HTTP_BAD_REQUEST:
            // The HTTP spec says we SHOULD NOT repeat the same request.
            throw new PermanentRequestFailure(
                "Server rejected the request as bad: " + responseMessage
                );
        case HttpURLConnection.HTTP_UNAUTHORIZED:
            // It is unlikely that retrying will get us in.
            throw new PermanentRequestFailure(
                "Server requires authentication: " + responseMessage
                );
        case HttpURLConnection.HTTP_PROXY_AUTH:
            // It is unlikely that retrying will get us in.
            throw new PermanentRequestFailure(
                "Proxy requires authentication: " + responseMessage
                );
        case HttpURLConnection.HTTP_FORBIDDEN:
            // The HTTP spec says we SHOULD NOT repeat the same request.
            throw new PermanentRequestFailure(
                "Server disallowed access: " + responseMessage
                );
        case HttpURLConnection.HTTP_LENGTH_REQUIRED:
            // Trying again will most likely trigger the same error.
            // I doubt this error will ever occur in practice, but I have
            // been surprised before.
            throw new PermanentRequestFailure(
                "Server requires Content-Length header"
                );
        default:
            if (responseCode >= 400) {
                throw new IOException(
                    "Response code " + responseCode + ": " + responseMessage
                    );
            } else {
                return connection.getInputStream();
            }
        }
    }

    private class QueuedRequest {
        private final ServerRequest request;
        private final ServerReplyListener listener;

        public QueuedRequest(
                ServerRequest request, ServerReplyListener listener
            ) {
            this.request = request;
            this.listener = listener;
        }

        public InputStream execute()
        throws IOException, PermanentRequestFailure {
            return sendRequest(request);
        }

        /**
         * Calls the listener to let it process the server reply.
         * This method closes the stream.
         * @param in The stream to read the reply from.
         * @throws IOException If there is an I/O error reading the reply.
         */
        public void serverReplied(InputStream in)
        throws IOException {
            try {
                try {
                    listener.serverReplied(in);
                } finally {
                    try {
                        in.close();
                    } catch (IOException e) {
                        // I still wonder what kind of things could go wrong
                        // when closing a stream...
                        logger.warning("Error closing stream: " + e);
                    }
                }
            } catch (IOException e) {
                // Propagate IOExceptions, but not other Exceptions.
                throw e;
            } catch (Exception e) {
                logger.log(Level.SEVERE, "Error handling server reply", e);
            }
        }

        /**
         * Calls the listener to tell it the reply failed permanently.
         * @param e Exception object with information about the failure.
         */
        public void serverFailed(PermanentRequestFailure e) {
            try {
                listener.serverFailed(e);
            } catch (Exception e2) {
                logger.log(Level.SEVERE, "Error handling server failure", e2);
            }
        }

    }

    public void uploadArtifact(Path artifact)
    throws IOException, PermanentRequestFailure {
        throw new IOException("not implemented");
    }

}
