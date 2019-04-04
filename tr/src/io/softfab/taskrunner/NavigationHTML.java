// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner;

import java.io.File;
import java.io.FileWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.net.MalformedURLException;
import java.net.URL;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;

import io.softfab.taskrunner.config.ConfigFactory;

public final class NavigationHTML {

    /**
     * Name of content frame in navigation HTML.
     */
    private final static String CONTENT_FRAME = "content";

    /**
     * File name of navigation HTML.
     */
    private final static String NAVIGATION_HTML = "navigation.html";

    /**
     * File name of results.properties.
     */
    private final static String RESULTS_PROPERTIES = "results.properties";

    /**
     * Base URL of the factory Control Center.
     */
    private final URL serverBaseURL;

    private final URL iconURL;

    private final URL styleURL;

    private final URL jobURL;

    /**
     * List of additional navigation entries.
     * The entries "Report Summary", "Wrapper Log" and "Wrapper Results" are always present
     * and not part of this list.
     */
    private final List navigationEntries;

    /**
     * Directory where the navigation HTML will be written.
     */
    private final File outputDir;

    private final String summaryFileName;

    public NavigationHTML(
            File outputDir, RunFactory factory, String summaryFileName
        ) {
        this.outputDir = outputDir;
        this.summaryFileName = summaryFileName;

        final TaskRunInfo runInfo = factory.runInfo;
        serverBaseURL = ConfigFactory.getConfig().controlCenter.serverBaseURL;
        try {
            iconURL = new URL(serverBaseURL, "/styles/SoftFabIcon.png");
            styleURL = new URL(serverBaseURL, "/styles/report_navigation.css");
            jobURL = new URL(serverBaseURL,
                "ShowReport?jobId=" + runInfo.run.jobId);
        } catch (MalformedURLException e) {
            // Since serverBaseURL is already validated, the combined URLs
            // should never be invalid, unless the code above is invalid.
            throw new RuntimeException("Internal error", e); // NOPMD
        }

        navigationEntries = new ArrayList();
        if (!summaryFileName.equals("")) {
            addNavigation(summaryFileName, "Report Summary");
        }
        addNavigation(factory.getLogFileName(), "Wrapper Log");
        addNavigation(RESULTS_PROPERTIES, "Wrapper Results");
    }

    /**
     * Add an item to the navigation bar.
     * @param fileName name (relative URL) of the report / log file.
     * @param description description that will be presented to the user.
     */
    private void addNavigation(String fileName, String description) {
        navigationEntries.add(new NavigationEntry(fileName, description));
    }

    /**
     * Writes HTML files in the output directory which let the user navigate
     * the reports.
     */
    public void writeNavigation()
    throws TaskRunException {
        try {
            writeFrameset();
        } catch (IOException e) {
            throw new TaskRunException("Error writing navigation HTML", e);
        }

        try {
            writeNavigationBar();
        } catch (IOException e) {
            throw new TaskRunException("Error writing navigation HTML", e);
        }

        // Placeholder results.properties file.
        try {
            final File resultsFile = new File(outputDir, RESULTS_PROPERTIES);
            resultsFile.getParentFile().mkdirs();
            final PrintWriter results = new PrintWriter(new FileWriter(resultsFile));
            try {
                results.println("No wrapper results yet, please wait...");
            } finally {
                results.close();
            }
        } catch (IOException e) {
            throw new TaskRunException("Error writing initial results.properties file", e);
        }

        // Placeholder Report Summary file.
        final File summaryFile = new File(outputDir, summaryFileName);
        if (summaryFileName.equals("") || summaryFile.exists()) {
            return;
        } else if (summaryFileName.endsWith("/")) {
            summaryFile.mkdirs();
            return;
        }
        summaryFile.getParentFile().mkdirs();
        try {
            final PrintWriter out = new PrintWriter(new FileWriter(summaryFile));
            try {
                if (summaryFileName.endsWith(".html")) {
                    out.println("<?xml version=\"1.0\" encoding=\"iso-8859-1\" ?>");
                    out.println(
                        "<!DOCTYPE html PUBLIC \"-//W3C//DTD XHTML 1.0 Strict//EN\" " +
                        "\"http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd\">"
                        );
                    out.println("<html>");
                    out.println("<head>");
                    out.println("\t<title>Placeholder for Report Summary file</title>");
                    out.println(
                        "\t<meta http-equiv=\"REFRESH\" " +
                        "content=\"10; url=" + summaryFileName +"\" />"
                        );
                    out.println("</head>");
                    out.println(
                        "<body xmlns=\"http://www.w3c.org/1999/xhtml\" " +
                        "xml:lang=\"en\" lang=\"en\">"
                        );
                    out.println("<p>");
                    out.println("No report index yet, please wait...");
                    out.println("</p>");
                    out.println("</body>");
                    out.println("</html>");
                } else {
                    out.println(
                        "No report index yet, " +
                        "please refresh your browser page..."
                        );
                }
            } finally {
                out.close();
            }
        } catch (IOException e) {
            throw new TaskRunException("Error writing summary file", e);
        }
    }

    /**
     * Writes the frameset file of the navigation HTML.
     */
    private void writeFrameset()
    throws IOException {
        final PrintWriter out = new PrintWriter(
            new FileWriter(new File(outputDir, "index.html")));
        try {
            out.println("<?xml version=\"1.0\" encoding=\"iso-8859-1\" ?>");
            out.println(
                "<!DOCTYPE html PUBLIC \"-//W3C//DTD XHTML 1.0 Frameset//EN\" " +
                "SYSTEM \"http://www.w3.org/TR/xhtml1/DTD/xhtml1-frameset.dtd\">"
                );
            out.println(
                "<html xmlns=\"http://www.w3c.org/1999/xhtml\" " +
                "xml:lang=\"en\" lang=\"en\">" );
            out.println("<head>");
            //TODO: Add project name in front of "SoftFab".
            //Possible solution: extract this name from CC config.py
            out.println("\t<title>SoftFab - Task Report</title>");
            out.println(
                "\t<link rel=\"shortcut icon\" href=\"" + iconURL + "\" />"
                );
            out.println("</head>");
            out.println("<frameset rows=\"32,*\">");
            out.println(
                "\t<frame name=\"navigation\" src=\"" + NAVIGATION_HTML + "\" " +
                "frameborder=\"0\" marginwidth=\"3\" marginheight=\"3\" " +
                "scrolling=\"no\" noresize=\"noresize\" />"
                );
            final NavigationEntry firstTab =
                (NavigationEntry)navigationEntries.get(0);
            out.println(
                "\t<frame name=\"" + CONTENT_FRAME + "\" " +
                "src=\"" + firstTab.fileName + "\" frameborder=\"0\" " +
                "noresize=\"noresize\" />"
                );
            out.println("</frameset>");
            out.println("</html>");
        } finally {
            out.close();
        }
    }

    /**
     * Writes the navigation bar frame file of the navigation HTML.
     */
    private void writeNavigationBar()
    throws IOException {
        final PrintWriter out = new PrintWriter(
            new FileWriter(new File(outputDir, "navigation.html")));
        try {
            out.println("<?xml version=\"1.0\" encoding=\"iso-8859-1\" ?>");
            out.println(
                "<!DOCTYPE html PUBLIC \"-//W3C//DTD XHTML 1.0 Strict//EN\" " +
                "\"http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd\">"
                );
            out.println("<html>");
            out.println("<head>");
            out.println("\t<title>Navigation Frame</title>");
            out.println(
                "\t<link rel=\"stylesheet\" type=\"text/css\" " +
                "href=\"" + styleURL + "\" />"
                );
            out.println("</head>");
            out.println(
                "<body xmlns=\"http://www.w3c.org/1999/xhtml\" " +
                "xml:lang=\"en\" lang=\"en\">"
                );
            out.println("<p>");
            out.println(
                "<a href=\"" + serverBaseURL + "\" target=\"_top\">" +
                "<img src=\"" + iconURL + "\" align=\"right\" border=\"0\" />" +
                "Home</a>"
                );
            out.println(
                "<a href=\"" + jobURL + "\" target=\"_top\">Show Reports</a>"
                );
            writeNavigationEntries(out);
            out.println("</p>");
            out.println("</body>");
            out.println("</html>");
        } finally {
            out.close();
        }
    }

    /**
     * Write HTML for additional navigation buttons.
     */
    private void writeNavigationEntries(PrintWriter out) {
        for (final Iterator i = navigationEntries.iterator(); i.hasNext(); ) {
            final NavigationEntry entry = (NavigationEntry)i.next();
            out.println(
                "<a href=\"" + entry.fileName + "\" " +
                "target=\"" + CONTENT_FRAME + "\">" +
                entry.description + "</a>"
                );
        }
    }

    private static class NavigationEntry {
        NavigationEntry(String fileName, String description) {
            this.fileName = fileName;
            this.description = description;
        }
        final String fileName;
        final String description;
    }
}
