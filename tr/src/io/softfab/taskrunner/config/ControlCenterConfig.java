// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner.config;

import io.softfab.xmlbind.DataObject;
import java.net.URL;

public class ControlCenterConfig implements DataObject {

    /**
    Base URL of the factory control center.
    */
    public URL serverBaseURL;

    public void verify() {
        // Nothing to check.
    }

}
