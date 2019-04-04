// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner.config;

import java.io.File;
import java.io.IOException;

import io.softfab.xmlbind.ParseException;
import io.softfab.xmlbind.XMLUnpacker;

/**
Factory that supplies the configurations of the task runner application.
Configuration files are parsed once at initialisation and cached for later use.
*/
public final class ConfigFactory {

    private ConfigFactory() {
        // Prevent instantiation.
    }

    private static TaskRunnerConfig root = null;

    /**
    Parse the configuration file.
    This method must be called before using any of the get[...]Config methods.
    By explicitly parsing at program startup rather than parsing on demand,
    configuration errors are detected as soon as possible.
    @throws IOException If reading the configuration file failed.
    @throws ParseException If parsing the configuration file failed.
    */
    public static void init(File configFile)
    throws IOException, ParseException {
        root = (TaskRunnerConfig)XMLUnpacker.INSTANCE.unpackFile(
            configFile, TaskRunnerConfig.class
            );
    }

    /**
    Gets the root element of the configuration.
    @throws IllegalStateException If called before init is called.
    */
    public static TaskRunnerConfig getConfig() {
        if (root == null) {
            throw new IllegalStateException(
                "Not initialised; call ConfigFactory.init() first"
                );
        }
        return root;
    }
}

