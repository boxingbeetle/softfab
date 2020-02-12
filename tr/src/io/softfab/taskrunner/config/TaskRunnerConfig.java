// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner.config;

import java.util.ArrayList;
import java.util.List;

import io.softfab.xmlbind.DataObject;
import io.softfab.xmlbind.ParseException;

public class TaskRunnerConfig implements DataObject {

    public ControlCenterConfig controlCenter;
    public OutputConfig output;
    public GenericConfig generic;

    /**
    List of Wrapper directories of this Factory PC.
    */
    public List<WrappersConfig> wrappers = new ArrayList<>();

    public void addWrappers(WrappersConfig wrapper) {
        wrappers.add(wrapper);
    }

    public void verify()
    throws ParseException {
        if (wrappers.isEmpty()) {
            throw new ParseException("Missing <wrappers> tag.");
        }
    }
}
