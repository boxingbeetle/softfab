// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner.config;

import io.softfab.xmlbind.DataObject;
import java.net.URL;

public class ControlCenterConfig implements DataObject {

    /**
    Base URL of the factory control center.
    */
    public URL serverBaseURL;

    /**
    ID of the access token to authenticate this Task Runner with.
    */
    public String tokenId;

    /**
    Password of the access token to authenticate this Task Runner with.
    */
    public String tokenPass;

    public void verify() {
        // Nothing to check.
    }

}
