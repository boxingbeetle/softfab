// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner;

import java.io.File;
import java.io.IOException;
import java.net.URL;
import java.util.logging.Logger;

class ExtractionRunFactory extends RunFactory {

    public ExtractionRunFactory(Logger logger, ExtractRunInfo info) {
        super(logger, info);
    }

    protected void createWorkEnv(File outputDir) {
        // Extraction run will use work environment created for execution run.
    }

    protected String getLogFileName() {
        return "extraction_log.txt";
    }

    protected void reportURL() {
        // TODO: this is mostly a copy/paste from ExecutionRunFactory
        final URL outputURL;
        try {
            outputURL = new URL(
                outputConfig.reportBaseURL,
                runInfo.run.getJobPath() + "/" + runInfo.run.taskId +
                    "/" + getLogFileName()
                );
        } catch (IOException e) {
            logger.severe("Error constructing report URL: " + e);
            return;
        }

        final ServerFormRequest request = new ServerFormRequest("TaskReport");
        request.addQueryParam("shadowId",
                ((ExtractRunInfo)runInfo).shadowrun.shadowId
                );
        request.addBodyParam("url", outputURL.toExternalForm());
        ControlCenter.INSTANCE.submitRequest(
            request,
            new APIReplyListener(logger, "submit extraction log URL")
            );
    }

    protected void reportResult(Result result) {
        final ServerFormRequest request = new ServerFormRequest("TaskDone");
        request.addQueryParam("shadowId",
            ((ExtractRunInfo)runInfo).shadowrun.shadowId
            );
        if (result.getExtractCode() != Result.UNKNOWN) {
            request.addBodyParam(
                "extraction.result",
                Result.getCodeString(result.getExtractCode())
                );
        }
        //if (result.getCode() != Result.UNKNOWN) {
        //    request.addBodyParam("result", result.getCodeString());
        //}
        final String summary = result.getSummary();
        if (summary != null) {
            request.addBodyParam("summary", summary);
        }
        request.addBodyParams(result.getExtractedData());
        ControlCenter.INSTANCE.submitRequest(
            request,
            new APIReplyListener(logger, "submit extraction results")
            );
    }

    protected void writeNavigation(File outputDir) {
        // Extraction does not need navigation HTML.
    }

    protected String getWrapperFileNameBase() {
        return "extractor";
    }

    public String getStartupFileBaseName() {
        return "extract";
    }

    public String getResultFileName() {
        return "extracted.properties";
    }
}
