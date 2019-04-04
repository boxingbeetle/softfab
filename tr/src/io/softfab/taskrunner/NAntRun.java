// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner;

import java.io.File;
import java.io.PrintWriter;
import java.util.Collection;
import java.util.Iterator;
import java.util.Map;
import java.util.logging.Logger;

import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.parsers.ParserConfigurationException;
import javax.xml.transform.OutputKeys;
import javax.xml.transform.Transformer;
import javax.xml.transform.TransformerConfigurationException;
import javax.xml.transform.TransformerException;
import javax.xml.transform.TransformerFactory;
import javax.xml.transform.dom.DOMSource;
import javax.xml.transform.stream.StreamResult;

import org.w3c.dom.Document;
import org.w3c.dom.Element;

public class NAntRun extends TaskRun {

    private static DocumentBuilderFactory documentBuilderFactory =
        DocumentBuilderFactory.newInstance();
    private static TransformerFactory transformerFactory =
        TransformerFactory.newInstance();

    public NAntRun(File wrapperFile,
            File outputDir, RunFactory factory, Logger runLogger
        ) {
        super(wrapperFile, outputDir, factory, runLogger);
        runLogger.info("NAntRun: " + scriptPath);
    }

    protected void writeStartupScript(PrintWriter out)
    throws TaskRunException {
        final WrapperVariableFlattener collector = new WrapperVariableFlattener('.');
        generateWrapperVariables(collector);

        // Create DOM document of NAnt build file.
        final DocumentBuilder builder;
        try {
            builder = documentBuilderFactory.newDocumentBuilder();
        } catch (ParserConfigurationException e) {
            throw new TaskRunException("Error creating DOM builder", e);
        }
        final Document document = builder.newDocument();
        final Element rootElem = document.createElement("project");
        document.appendChild(rootElem);
        for (final Iterator it = collector.getVariables(); it.hasNext(); ) {
            final Map.Entry entry = (Map.Entry)it.next();
            final Object value = entry.getValue();
            final String valueStr =
                value instanceof Collection
                ? join((Collection)value, ' ')
                : (String)value;
            final Element propertyElem = document.createElement("property");
            propertyElem.setAttribute("name", (String)entry.getKey());
            // Escape "$" to avoid "${" from being treated as an expression evaluation.
            propertyElem.setAttribute("value", valueStr.replace("$", "${'$'}"));
            rootElem.appendChild(propertyElem);
        }
        final Element nantElem = document.createElement("nant");
        nantElem.setAttribute("buildfile", scriptPath);
        rootElem.appendChild(nantElem);

        // Write DOM document to file.
        final Transformer transformer;
        try {
            transformer = transformerFactory.newTransformer();
        } catch (TransformerConfigurationException e) {
            throw new TaskRunException("Error creating XML transformer", e);
        }
        transformer.setOutputProperty(OutputKeys.METHOD, "xml");
        transformer.setOutputProperty(OutputKeys.INDENT, "yes");
        try {
            final StreamResult antResult = new StreamResult(out);
            transformer.transform(new DOMSource(document), antResult);
        } catch (TransformerException e) {
            throw new TaskRunException(
                "Error generating XML for NAnt startup script", e
                );
        }
    }

    protected String[] getStartupCommand(String startupScriptPath) {
        return new String[] { "nant", "-buildfile:" + startupScriptPath };
    }

}
