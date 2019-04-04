// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner;

import java.util.HashMap;
import java.util.Map;

import io.softfab.xmlbind.DataObject;
import io.softfab.xmlbind.ParseException;

/**
 * Contains information about framework, script and task parameters
 */
public class TaskInfo implements DataObject {

    public String target;
    public String framework;
    public String script;

    /**
    Additional parameters to the task.
    Keys and values are both strings.
    */
    public Map parameters = new HashMap();

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

    /**
     * Get file name of framework specific report file.
     */
    public final String getFrameworkSummary() {
        String summary = (String)parameters.get("sf.summary");
        if (summary == null) {
            // Control Center version 2.13.0 and later will always send
            // the "sf.summary" parameter, but older versions only send it
            // if the user has overridden the parameter.
            summary = "log.txt";
        }
        return summary;
    }

}
