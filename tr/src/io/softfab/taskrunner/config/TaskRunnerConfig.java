// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner.config;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import io.softfab.xmlbind.DataObject;
import io.softfab.xmlbind.ParseException;

public class TaskRunnerConfig implements DataObject {

    public ControlCenterConfig controlCenter;
    public OutputConfig output;
    public GenericConfig generic;
    public SUTConfig sut;

    /**
    List of Wrapper directories of this Factory PC.
    Elements are of type WrappersConfig
    */
    public List wrappers = new ArrayList();

    /**
    Capabilities of this Factory PC.
    Elements are of type Capability.
    */
    public List capabilities = new ArrayList();

    /**
    Local parameters of this Factory PC.
    Keys and values are both strings.
    */
    public Map parameters = new HashMap();

    public void addWrappers(WrappersConfig wrapper) {
        wrappers.add(wrapper);
    }

    public void addCapability(Capability capability) {
        capabilities.add(capability);
    }

    public void addParam(Parameter parameter)
    throws ParseException {
        if (parameters.put(parameter.name, parameter.value) != null) {
            throw new ParseException("Duplicate parameter: " + parameter.name);
        }
    }

    public void verify()
    throws ParseException {
        if (wrappers.isEmpty()) {
            throw new ParseException("Missing <wrappers> tag.");
        }
    }
}
