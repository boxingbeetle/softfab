// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.logging.Logger;

public class ExecuteRunInfo extends TaskRunInfo {

    /**
    Resources reserved for running the task.
    Keys are of type String, values are of type ResourceInfo.
    LinkedHashMap is used to preserve the order of the resources
    (which used to be important to handle MHP streamers/streams)
    */
    public Map resources = new LinkedHashMap();

    public void addResource(ResourceInfo resource) {
        resources.put(resource.ref, resource);
    }

    public RunFactory getRunFactory(Logger logger) {
        return new ExecutionRunFactory(logger, this);
    }

    public String getActionText() {
        return "execution";
    }

}
