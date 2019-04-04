// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner;

import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.logging.Logger;

import io.softfab.xmlbind.DataObject;

/* This class must be public, otherwise XMLUnpacker won't have
 * enough access to be able to assign fields declared here.
 */
public abstract class TaskRunInfo implements DataObject {

    public RunInfo run;

    public TaskInfo task;

    /**
     * Products that serve as input to the task.
     */
    public Map<String, InputInfo> inputs = new HashMap<>();

    public final void addInput(InputInfo input) {
        inputs.put(input.name, input);
    }

    /**
     * Names of products that serve as output to the task.
     */
    public Set<String> outputs = new HashSet<>();

    public final void addOutput(OutputInfo output) {
        outputs.add(output.name);
    }

    public String getRunIdAsXML() {
        return "<run jobId=\"" + run.jobId +
            "\" taskId=\"" + run.taskId +
            "\" runId=\"" + run.runId + "\"/>";
    }

    public abstract String getActionText();

    public abstract RunFactory getRunFactory(Logger logger);

    public void verify() {
        // This data is provided by the Control Center; validating
        // it here is likely to cause more trouble than it solves.
    }

}
