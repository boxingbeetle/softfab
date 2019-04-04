// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner;

import java.io.IOException;
import java.io.InputStream;
import java.util.logging.Level;
import java.util.logging.Logger;

import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.parsers.ParserConfigurationException;

import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.Node;
import org.w3c.dom.NodeList;
import org.xml.sax.SAXException;

import io.softfab.xmlbind.ParseException;
import io.softfab.xmlbind.XMLUnpacker;

/**
Polls the central software factory server to fetch a task to run.
*/
public class SyncLoop
implements ServerReplyListener {

    private static class SyncException extends Exception {
        public SyncException(String message) {
            super(message);
        }
    }

    /**
     * Time in milliseconds between two sync requests if the Control Center
     * did not specify a delay.
     */
    private static final int DEFAULT_SYNC_DELAY = 10000;

    private final Logger logger =
        Logger.getLogger("io.softfab.taskrunner");

    private final RunStatus runStatus = new RunStatus(logger);

    /**
     * XML parser instance.
     */
    private final DocumentBuilder documentBuilder;

    /**
     * Used to wait until the Control Center replies to a sync request.
     */
    private final Object syncReplyTrigger = new Object();

    /**
     * 1-place buffer to pass server responses from the callback thread to the
     * main thread.
     * Synchronize on syncReplyTrigger before accessing this field.
     */
    private Element serverResponse;

    /**
     * Should the main loop continue running?
     */
    private boolean running = true;

    public SyncLoop() {
        // Get an XML parser.
        final DocumentBuilderFactory documentBuilderFactory =
            DocumentBuilderFactory.newInstance();
        documentBuilderFactory.setIgnoringComments(true);
        try {
            documentBuilder = documentBuilderFactory.newDocumentBuilder();
        } catch (ParserConfigurationException e) {
            // Escalate.
            throw new RuntimeException( // NOPMD
                "Failed to create XML parser", e
                );
        }
    }

    public void mainLoop() {
        while (running) {
            // Submit sync request to Control Center.
            runStatus.submitSync(this);
            // Wait until Control Center replies.
            final Element response;
            synchronized (syncReplyTrigger) {
                if (serverResponse == null) {
                    try {
                        syncReplyTrigger.wait();
                    } catch (InterruptedException e) {
                        return;
                    }
                }
                response = serverResponse;
                serverResponse = null;
            }
            // Process commands.
            final int delay;
            if (response == null) {
                delay = DEFAULT_SYNC_DELAY;
            } else {
                delay = handleCommands(response);
            }
            // Wait before sending next sync request.
            runStatus.delay(delay);
        }
        ControlCenter.INSTANCE.exit();
    }

    public void serverReplied(InputStream in)
    throws IOException {
        Element response = null;
        try {
            final Document document;
            try {
                document = documentBuilder.parse(in);
            } catch (SAXException e) {
                logger.severe("Control Center returned bad XML: " + e);
                return;
            }
            response = document.getDocumentElement();
        } finally {
            // Whatever happens, synchronization must go on.
            synchronized (syncReplyTrigger) {
                assert serverResponse == null;
                serverResponse = response;
                syncReplyTrigger.notifyAll();
            }
        }
    }

    public void serverFailed(PermanentRequestFailure e) {
        logger.severe(
            "Control Center failed to synchronize: " + e.getMessage()
            );
        // Whatever happens, synchronization must go on.
        synchronized (syncReplyTrigger) {
            assert serverResponse == null;
            syncReplyTrigger.notifyAll();
        }
    }

    private int handleCommands(Element response) {
        int retDelay = DEFAULT_SYNC_DELAY;
        try {
            // We cannot parse with xmlbind because the order of commands
            // is relevant.
            if (!response.getTagName().equals("response")) {
                throw new SyncException("Invalid response");
            }
            final NodeList nodes = response.getChildNodes();
            final int count = nodes.getLength();
            for (int i = 0; i < count; i++) {
                final Node node = nodes.item(i);
                if (node.getNodeType() != Node.ELEMENT_NODE) {
                    continue;
                }
                final Element command = (Element)node;
                final String name = command.getTagName();
                if (name.equals("start") || name.equals("extract")) {
                    logger.fine("Received <" + name + "> command");
                    final TaskRunInfo newRunInfo =
                        (TaskRunInfo)XMLUnpacker.INSTANCE.unpack(
                            command,
                            name.equals("start")
                            ? ExecuteRunInfo.class
                            : ExtractRunInfo.class
                            );
                    runStatus.startTask(newRunInfo);
                } else if (name.equals("abort")) {
                    logger.fine("Received <abort> command");
                    runStatus.abortTask();
                } else if (name.equals("exit")) {
                    logger.fine("Received <exit> command");
                    running = false; // leave main loop
                    retDelay = 0; // exit immediately
                } else if (name.equals("wait")) {
                    logger.fine("Received <wait> command");
                    final int delay = Integer.parseInt(
                        command.getAttribute("seconds")
                        );
                    if (delay < 0) {
                        throw new SyncException("Invalid delay: " + delay);
                    }
                    retDelay = delay * 1000; // convert to ms
                } else {
                    throw new SyncException("Invalid command: " + name);
                }
            }
        } catch (ParseException e) {
            logger.severe(
                "Error parsing task parameters: " + e + ", " +
                "Control Center is probably communicating in a different " +
                "protocol version than the Task Runner supports"
                );
        } catch (SyncException ex) {
            logger.log(Level.SEVERE, "Exception in sync loop", ex);
        }
        return retDelay;
    }

}
