// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner;

import java.io.File;
import java.net.MalformedURLException;
import java.net.URL;
import java.util.Random;
import java.util.logging.Logger;


class ExecutionRunFactory extends RunFactory {

    private static final int CREATE_DIR_RETRY_COUNT = 5;
    private static final int CREATE_DIR_DELAY_FIXED = 1000;
    private static final int CREATE_DIR_DELAY_RANDOM = 4000;
    private static final double CREATE_DIR_DELAY_FACTOR = 1.6;

    public ExecutionRunFactory(Logger logger, ExecuteRunInfo info) {
        super(logger, info);
    }

    protected void createWorkEnv(File outputDir) throws TaskRunException {
        // Create output directory.
        boolean createDirOK = outputDir.mkdirs();
        if (!createDirOK) {
            // Workaround for errors that occur when creating a directory on
            // a network share in Windows.
            final Random random = new Random(System.currentTimeMillis() +
                outputDir.getPath().hashCode());
            int retry = CREATE_DIR_RETRY_COUNT;
            int fixed = CREATE_DIR_DELAY_FIXED;
            int range = CREATE_DIR_DELAY_RANDOM;
            do {
                try {
                    Thread.sleep(fixed + random.nextInt(range));
                } catch (InterruptedException ex) {
                    throw new TaskRunException("Interrupted", ex);
                }
                fixed *= CREATE_DIR_DELAY_FACTOR;
                range *= CREATE_DIR_DELAY_FACTOR;
                createDirOK = outputDir.mkdirs();
            } while ((!createDirOK) && (--retry > 0));
        }
        if (!createDirOK) {
            throw new TaskRunException(
                "Could not create output directory: \"" + outputDir + "\""
                );
        }
    }

    protected String getLogFileName() {
        return "wrapper_log.txt";
    }

    protected void reportURL() {
        final String taskName = runInfo.run.taskId;
        final URL outputURL;
        try {
            outputURL = new URL(
                outputConfig.reportBaseURL,
                runInfo.run.getJobPath() + "/" + taskName + "/"
                );
        } catch (MalformedURLException e) {
            logger.severe("Error constructing report URL: " + e);
            return;
        }

        final ServerFormRequest request =
            new ServerFormRequest("TaskReport");
        request.addQueryParam("id", runInfo.run.jobId);
        request.addQueryParam("name", taskName);
        request.addBodyParam("url", outputURL.toExternalForm());
        ControlCenter.INSTANCE.submitRequest(
            request,
            new APIReplyListener(logger, "submit report URL")
            );
    }

    protected void reportResult(Result result) {
        // Create request and send it to Control Center.
        final ServerFormRequest request = new ServerFormRequest("TaskDone");
        request.addQueryParam("id", runInfo.run.jobId);
        request.addQueryParam("name", runInfo.run.taskId);
        if (result.getCode() != Result.UNKNOWN) {
            request.addBodyParam("result", result.getCodeString());
        }
        final String summary = result.getSummary();
        if (summary != null) {
            request.addBodyParam("summary", summary);
        }
        request.addBodyParams(result.getOutputLocators());
        request.addBodyParams(result.getExtractedData());
        ControlCenter.INSTANCE.submitRequest(
            request,
            new APIReplyListener(logger, "submit task done notice")
            );
    }

    protected String getWrapperFileNameBase() {
        return "wrapper";
    }
    public String getStartupFileBaseName() {
        return "execute";
    }

    public String getResultFileName() {
        return "results.properties";
    }

}
