// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner;

import java.io.PrintWriter;
import java.io.StringWriter;
import java.text.DateFormat;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.logging.Formatter;
import java.util.logging.LogRecord;

/**
Formatter which creates a single line per message.
However, when the log event contains a Throwable,
the stack trace is printed as well.
SimpleFormatter was too verbose for my taste.
*/
public class PlainFormatter extends Formatter {

    private final DateFormat dateFormat;

    public PlainFormatter() {
        super();
        dateFormat = new SimpleDateFormat("yyyy-MM-dd HH:mm:ss");
    }

    public String format(LogRecord record) {
        final StringBuffer ret = new StringBuffer();
        // Date and time.
        ret.append(dateFormat.format(new Date(record.getMillis())));
        ret.append(' ');
        // Level.
        ret.append(record.getLevel().getName()).append(": ");
        // Message.
        String message = record.getMessage();
        if (message == null) {
            message = "(no message)";
        }
        ret.append(message).append('\n');
        // Exception, if any.
        final Throwable thrown = record.getThrown();
        if (thrown != null) {
            final StringWriter trace = new StringWriter(1000);
            final PrintWriter out = new PrintWriter(trace);
            thrown.printStackTrace(out);
            out.close();
            ret.append(trace.getBuffer());
        }
        // Done.
        return ret.toString();
    }

}
