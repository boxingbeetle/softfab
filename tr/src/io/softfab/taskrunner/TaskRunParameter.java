// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner;

import io.softfab.xmlbind.DataObject;

/**
Additional parameter to a task run.
Interpretation of these is done by the framework wrapper.
*/
public class TaskRunParameter implements DataObject {

    /**
    The machine-friendly name of this parameter.
    */
    public String name;

    /**
    The value of this parameter.
    */
    public String value;

    public void verify() {
        // This data is provided by the Control Center; validating it here is
        // likely to cause more trouble than it solves.
    }

}
