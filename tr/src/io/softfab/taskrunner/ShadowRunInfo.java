// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner;

import io.softfab.xmlbind.DataObject;

public class ShadowRunInfo implements DataObject {

    public String shadowId;

    public void verify() {
        // This data is provided by the Control Center; validating
        // it here is likely to cause more trouble than it solves.
    }
}
