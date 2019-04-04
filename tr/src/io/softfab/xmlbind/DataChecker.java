// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.xmlbind;

import java.io.File;
import java.io.IOException;

/**
A collection of utility methods to verify parsed data.
Often the check itself is trivial, but giving a useful error message is not.
*/
public final class DataChecker {

    /**
    This class should not be instantiated.
    */
    private DataChecker() {
        // This constructor exists only to prevent instantiation.
    }

    /**
    Check that the given file path represents an existing directory.
    @param directory The file path to check.
    @param attrName
        The name of the XML attribute where the path was read from.
        This is used to create a useful error message when necessary.
    @throws ParseException If the given file path does not exist,
        or is not a directory.
    */
    public static void checkExistingDirectory(File directory, String attrName)
    throws ParseException {
        try {
            String canonicalPath;
            try {
                canonicalPath = directory.getCanonicalPath();
            } catch (IOException e) {
                throw new ParseException(
                    "Directory \"" + directory + "\" is invalid: " + e
                    );
            }
            if (!directory.exists()) {
                throw new ParseException(
                    "Directory does not exist: \"" + canonicalPath + "\""
                    );
            }
            if (!directory.isDirectory()) {
                throw new ParseException(
                    "Path is not a directory: \"" + canonicalPath + "\""
                    );
            }
        } catch (ParseException e) {
            e.insertContext(attrName);
            throw e;
        }
    }

    /**
    Checks whether a given integer is within the specified range.
    @param value The integer to check.
    @param attrName
        The name of the XML attribute where the integer was read from.
        This is used to create a useful error message when necessary.
    @param loLimit The lowest value allowed, inclusive.
    @param hiLimit The highest value allowed, inclusive.
    @throws ParseException If the given integer is not in the range.
    */
    public static void checkIntRange(int value, String attrName,
        int loLimit, int hiLimit)
    throws ParseException {
        if (value < loLimit || value > hiLimit) {
            throw new ParseException(
                "Integer value is out of range " +
                "[" + loLimit + ".." + hiLimit + "]: " + value
                ).insertContext(attrName);
        }
    }

    /**
    Checks whether a given integer is a valid port number.
    @param port The integer to check.
    @param attrName
        The name of the XML attribute where the port number was read from.
        This is used to create a useful error message when necessary.
    @throws ParseException If the given integer is not in the range [1..0xFFFF].
    */
    public static void checkPort(int port, String attrName)
    throws ParseException {
        if (port <= 0 || port >= 0x10000) {
            throw new ParseException(
                "Port number out of range: " + port
                ).insertContext(attrName);
        }
    }

}
