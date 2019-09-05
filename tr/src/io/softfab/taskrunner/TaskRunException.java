// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner;

/**
Thrown when an error is detected during a task run,
which is serious enough to abort the run.
*/
public class TaskRunException extends Exception {

    public TaskRunException(String message) {
        super(message);
    }

    public TaskRunException(String message, Throwable cause) {
        super(message, cause);
    }

    /**
    Create a Result object, with result code ERROR and a summary based on the
    description (and cause, if any) of this TaskRunException.
    */
    public Result toResult() {
        return toResult(false);
    }

    /**
    Create a Result object, with result code ERROR or IGNORE and a summary
	based on the description (and cause, if any) of this TaskRunException.
    */
	public Result toResult(boolean ignore) {
        return new Result(ignore ? Result.IGNORE : Result.ERROR, toString());
    }

    public String toString() {
        final Throwable cause = getCause();
        return cause == null ? getMessage() : getMessage() + ": " + cause;
    }

}

