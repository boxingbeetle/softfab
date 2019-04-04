// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.xmlbind;

/**
Thrown when a syntax error is detected in the data that is being parsed.
*/
public class ParseException extends Exception {

    private StringBuffer context = null;

    public ParseException(String description) {
        super(description);
    }

    public ParseException(String description, Throwable cause) {
        super(description, cause);
    }

    /**
    Adds a context level for this exception.
    The context is represented as a string such as "level2.level1.level0",
    where "levelN" are the levels in the order they are inserted.
    The reverse order is convenient for adding context from a recursively
    invoked parse method.
    @return This object itself, so you can this method in an expression
      after the "throw" statement (similar to StringBuffer.append).
    */
    ParseException insertContext(String level) {
        if (context == null) {
            context = new StringBuffer(level);
        } else {
            context.insert(0, '.').insert(0, level);
        }
        return this;
    }

    public String getMessage() {
        final Throwable cause = getCause();
        return super.getMessage()
            + ( context == null ? "" : " (in " + context + ")" )
            + ( cause == null ? "" : ": " + cause.getMessage() );
    }

}

