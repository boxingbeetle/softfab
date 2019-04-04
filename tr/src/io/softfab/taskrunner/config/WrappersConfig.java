// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner.config;

import java.io.File;

import io.softfab.xmlbind.DataChecker;
import io.softfab.xmlbind.DataObject;
import io.softfab.xmlbind.ParseException;

public class WrappersConfig implements DataObject {

    /**
    Directory which contains the wrapper scripts.
    It can be an absolute path or a path relative to the current directory
    (typically "fab/client/taskrunner").
    */
    public File dir;

    public void verify()
    throws ParseException {
        DataChecker.checkExistingDirectory(dir, "dir");
    }

}
