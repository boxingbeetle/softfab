// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner;

import java.io.File;

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
        // The log file of the run to be abotrted is used
        return factory.getLogFileName();
    }

    protected void reportURL() {
        // Nothing to report
    }

    protected void reportResult(Result result) {
        // Nothing to report
    }

    protected String getStartupFileBaseName() {
        return factory.getStartupFileBaseName() + "_abort";
    }

    protected String getResultFileName() {
        // No result file used
        return null;
    }

    protected void writeNavigation(File outputDir) {
        // Nothing to write
    }

    protected String getWrapperFileNameBase() {
        return factory.getWrapperFileNameBase() + "_abort";
    }

    protected String getWrapperName() {
        return factory.getWrapperName();
    }

}
