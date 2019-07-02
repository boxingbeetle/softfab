// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner;

import java.util.regex.Matcher;
import java.util.regex.Pattern;

import io.softfab.xmlbind.DataObject;

/**
 * This class represents a task as identified by the control center.
 */
public class RunInfo implements DataObject {

    /**
     * Regular expression for splitting job IDs.
     */
    private final static Pattern JOB_ID = Pattern.compile(
        "(\\d{6})-(\\d{4}-\\p{XDigit}{4})"
        );

    // Data fields:
    public String jobId;
    public String taskId;
    public String runId;

    // Derived fields:
    private String jobPath; // NOPMD
    private String artifactPath; // NOPMD

    public void verify() {
        // This data is provided by the Control Center; validating it here is
        // likely to cause more trouble than it solves.
    }

    public String getJobPath() {
        if (jobPath == null) {
            final Matcher matcher = JOB_ID.matcher(jobId);
            jobPath =
                  matcher.matches()
                ? matcher.group(1) + "/" + matcher.group(2)
                : jobId;
        }
        return jobPath;
    }

    public String getArtifactPath() {
        if (artifactPath == null) {
            final Matcher matcher = JOB_ID.matcher(jobId);
            if (matcher.matches()) {
                artifactPath = "jobs/"
                        + matcher.group(1) + "/" + matcher.group(2) + "/"
                        + taskId;
            } else {
                artifactPath = "ERROR_BAD_JOB_ID_" + jobId;
            }
        }
        return artifactPath;
    }

}
