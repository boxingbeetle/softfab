// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner;

import java.util.HashMap;
import java.util.Map;

import io.softfab.xmlbind.DataObject;
import io.softfab.xmlbind.ParseException;

/**
A collection of information about a resource.
*/
public class ResourceInfo implements DataObject {

    /**
    Reference name of this resource.
    This corresponds to the "ref" attribute in the task definition XML.
    */
    public String ref;

    /**
    Location of this resource.
    */
    public String locator;

    /**
    Additional parameters to the task.
    */
    public Map<String, String> parameters = new HashMap<>();

    public void addParam(TaskRunParameter parameter)
    throws ParseException {
        if (parameters.put(parameter.name, parameter.value) != null) {
            throw new ParseException("Duplicate parameter: " + parameter.name);
        }
    }

    public void verify() {
        // This data is provided by the Control Center; validating it here is
        // likely to cause more trouble than it solves.
    }

}
