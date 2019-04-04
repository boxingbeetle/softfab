// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner.config;

import io.softfab.xmlbind.DataObject;

public class Capability implements DataObject {

    /**
    Identification string of this capability.
    */
    public String name;

    public String toString() {
        // Used for constructing the SF_TR_CAPABILITIES variable.
        return name;
    }

    public void verify() {
        // No fields, so nothing to check.
    }
}
