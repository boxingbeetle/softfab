// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner;

public class PermanentRequestFailure extends Exception {

    public PermanentRequestFailure(String message) {
        super(message);
    }

    public PermanentRequestFailure(String message, Throwable cause) {
        super(message, cause);
    }

}
