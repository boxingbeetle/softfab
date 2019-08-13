// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner;

/**
 * This class encapsulates the current version of the Task Runner.
 */
public final class Version {

    private static final String VERSION = "3.0.0-pre3"; // NOPMD

    private Version() {
        // Prevent instantiation.
    }

    public static String getVersion() {
        return VERSION;
    }

}
