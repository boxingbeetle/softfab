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
