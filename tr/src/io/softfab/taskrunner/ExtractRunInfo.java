// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner;

import java.util.logging.Logger;

public class ExtractRunInfo extends TaskRunInfo {

    public ShadowRunInfo shadowrun;

    public RunFactory getRunFactory(Logger logger) {
        return new ExtractionRunFactory(logger, this);
    }

    public String getRunIdAsXML() {
        return "<shadowrun shadowId=\"" + shadowrun.shadowId + "\"/>";
    }

    public String getActionText() {
        return "extraction";
    }

}
