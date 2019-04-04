// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner.config;

import io.softfab.xmlbind.DataObject;

public class SUTConfig implements DataObject {

    /**
    Name of the target type that is connected to the factory PC on which
    this task runner is executing.
    */
    public String target;

    /**
    Identification of the system under test (SUT).
    This identification string is target specific;
    it is passed as-is to the target control scripts.
    For generic wrappers this field is not used;
    the dummy default was added to make this field optional.
    */
    public String sutId = "dummy";

    public void verify() {
        // TODO: Validate target name.
        //       Do not validate sutId, since most fabs don't use it.
    }

}
