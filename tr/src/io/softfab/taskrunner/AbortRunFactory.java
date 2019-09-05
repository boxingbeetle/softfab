// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner;

import java.io.File;
import java.util.ArrayList;
import java.util.List;

class AbortRunFactory extends RunFactory {

    private final RunFactory factory;

    AbortRunFactory(RunFactory factory) {
        super(factory.logger, factory.runInfo);
        this.factory = factory;
    }

    protected void createWorkEnv(File outputDir) {
        // Use work environment created for the run to be aborted.
    }

    protected String getLogFileName() {
        return "abort_log.txt";
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
        final List<String> reports = new ArrayList();
        for (final String report : result.getReports()) {
            reports.add(new File(report).getName());
        }
        reports.add(getLogFileName());
        request.addBodyParam("report", reports);
        request.addBodyParams(result.getOutputLocators());
        request.addBodyParams(result.getExtractedData());
        ControlCenter.INSTANCE.submitRequest(
            request,
            new APIReplyListener(logger, "submit task done notice")
            );
    }

    protected String getStartupFileBaseName() {
        return factory.getStartupFileBaseName() + "_abort";
    }

    protected String getResultFileName() {
        return "results_abort.properties";
    }

    protected String getWrapperFileNameBase() {
        return factory.getWrapperFileNameBase() + "_abort";
    }

    protected String getWrapperName() {
        return factory.getWrapperName();
    }

}
