// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner;

/**
 * This exception can be thrown to indicate that the task has been aborted
 */
public final class AbortedException extends TaskRunException {

    public AbortedException() {
        super("Aborted by request of the Control Center");
    }

}
