// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner;

import java.io.BufferedReader;
import java.io.IOException;
import java.util.HashMap;
import java.util.Iterator;
import java.util.Map;
import java.util.TreeMap;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
Contains the results of a task run.
*/
public class Result {

    public final static int UNKNOWN = 0;
    public final static int OK = 1;
    public final static int WARNING = 2;
    public final static int ERROR = 3;
    public final static int INSPECT = 4;

    /**
    Index i in this array contains the string representation of result code i.
    */
    private final static String[] CODE_STRINGS =
        { "unknown", "ok", "warning", "error", "inspect" };

    private static final Pattern PROPERTY_PATTERN = Pattern.compile(
        "\\s*([\\w.]+)\\s*=\\s*((?:.*\\S)?)\\s*"
        );

    private final static Pattern OUTPUT_PATTERN = Pattern.compile(
        "^output.([^.]+)\\.([^.]+)$"
        );

    public static String getCodeString(int code)
    {
        return CODE_STRINGS[code];
    }

    /**
    @see #getCode
    */
    private int code;

    /**
    @see #getSummary
    */
    private String summary;

    /**
    @see #getReports
    */
    private Map<Integer, String> reports;

    /**
    @see #getOutputLocators
    */
    private Map<String, String> locators;

    /**
    @see #getExtractedData
    */
    private Map<String, String> extracted;

    /**
    @see #getExtractCode
    */
    private int extractCode;

    private static void checkResultCode(int code) {
        if (code < 0 || code >= CODE_STRINGS.length) {
            throw new IllegalArgumentException(
                "Result code out of range: " + code
                );
        }
    }

    private static int parseResultCode(String codeString)
    throws TaskRunException {
        int result = UNKNOWN;
        for (int i = 0; i < CODE_STRINGS.length; i++) {
            if (CODE_STRINGS[i].equals(codeString)) {
                result = i;
            }
        }
        if (result == UNKNOWN) {
            throw new TaskRunException(
                "Invalid result code \"" + codeString + "\""
                );
        }
        return result;
    }

    /**
    Create a Result with the given code and summary.
    @param code OK, WARNING or ERROR.
    @param summary Summary text that can be shown to the user.
      If no specific message is available, pass null and the Control Center
      will create a default message.
    */
    public Result(int code, String summary) {
        this(code, summary, UNKNOWN);
    }

    /**
    Create a Result with the given code, summary, and extraction code.
    @param code OK, WARNING or ERROR.
    @param summary Summary text that can be shown to the user.
    @param extractCode result code of the extraction task
    */
    public Result(int code, String summary, int extractCode) {
        checkResultCode(code);
        checkResultCode(extractCode);
        this.code = code;
        this.summary = summary;
        this.reports = new TreeMap<>();
        this.locators = new HashMap<>();
        this.extracted = new HashMap<>();
        this.extractCode = extractCode;
    }

    /**
    Reads a Result from a file.
    The file is a text file with one key-value pair per line.
    It must include the keys "result" and "summary", whose values contain
    the result code (as a string) and summary text respectively.
    Syntax for locators: "output.PRODUCT_NAME.locator=VALUE".
    @param in Stream to parse.
    @throws IOException If reading the file fails.
    @throws TaskRunException If parsing the file fails.
    */
    public Result(BufferedReader in)
    throws IOException, TaskRunException {
        extractCode = UNKNOWN;
        code = UNKNOWN;
        summary = null;
        // Load properties.
        final Map<String, String> resultProp = new HashMap<>();
        try {
            while (true) {
                String line = in.readLine();
                if (line == null) {
                    break;
                }
                final Matcher matcher = PROPERTY_PATTERN.matcher(line);
                if (matcher.matches()) {
                    resultProp.put(matcher.group(1), matcher.group(2));
                } else {
                    line = line.trim();
                    if (line.length() > 0 && line.charAt(0) != '#') {
                        throw new TaskRunException(
                            "Invalid property file syntax: " + line
                            );
                    }
                }
            }
        } finally {
            in.close();
        }

        // Parse properties.
        reports = new TreeMap<>();
        locators = new HashMap<>();
        extracted = new HashMap<>();
        for (final Map.Entry<String, String> entry : resultProp.entrySet()) {
            parseProperty(entry.getKey(), entry.getValue());
        }
    }

    private void parseProperty(String name, String value)
    throws TaskRunException {
        if (name.equals("result")) {
            code = parseResultCode(value);
        } else if (name.equals("summary")) {
            summary = value;
        } else if (name.equals("extraction.result")) {
            extractCode = parseResultCode(value);
        } else if (name.startsWith("data.")) {
            // We don't remove "data." here, because it would have to be added
            // later anyway when posting the data to the Control Center
            extracted.put(name, value);
        } else if (name.equals("report")) {
            // Just "report" is a shortcut for "report.0".
            reports.put(0, value);
        } else if (name.startsWith("report.")) {
            final String priorityStr = name.substring(7);
            int priority;
            try {
                priority = Integer.parseUnsignedInt(priorityStr);
            } catch (NumberFormatException e) {
                throw new TaskRunException(
                    "Invalid report priority: \"" + value + "\""
                    );
            }
            reports.put(priority, value);
        } else {
            final Matcher matcher = OUTPUT_PATTERN.matcher(name);
            if (matcher.matches()) {
                final String product = matcher.group(1);
                final String property = matcher.group(2);
                if (property.equals("locator")) {
                    locators.put("output." + product, value);
                } else {
                    throw new TaskRunException(
                        "Unsupported output property: \"" + property + "\""
                        );
                }
            } else {
                throw new TaskRunException(
                    "Don't know how to handle property: \"" + name + "\""
                    );
            }
        }
    }

    /**
    Gets the result code.
    @return UNKNOWN, OK, WARNING or ERROR.
    */
    public int getCode() {
        return code;
    }

    /**
    Gets the result code as a string.
    @return "unknown", "ok", "warning" or "error".
    */
    public String getCodeString() {
        return getCodeString(code);
    }

    /**
    Gets a short user-readable summary describing the results.
    Example: "3 out of 5 tests passed".
    @return A summary text for this results, or null if no summary is available.
    */
    public String getSummary() {
        return summary;
    }

    /**
    Get the reports produced by the task.
    @return A (possibly empty) sequence of report file paths.
    */
    public Iterable<String> getReports() {
        return reports.values();
    }

    /**
    Get locators of the outputs produced by the task.
    @return A (possibly empty) mapping from output product name to locator.
    */
    public Map<String, String> getOutputLocators() {
        return locators;
    }

    /**
    Gets the extraction result code.
    @return UNKNOWN, OK, WARNING or ERROR.
    */
    public int getExtractCode() {
        return extractCode;
    }

    /**
    Get mid-level data.
    @return A (possibly empty) mapping from data key to value.
    */
    public Map<String, String> getExtractedData() {
        return extracted;
    }

}
