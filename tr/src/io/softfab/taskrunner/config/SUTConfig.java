// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner.config;

import io.softfab.xmlbind.DataObject;

public class SUTConfig implements DataObject {

    /**
    Name of the target type that is connected to the factory PC on which
    this task runner is executing.
    */
    public String target;

    public void verify() {
        // TODO: Validate target name.
    }

}
