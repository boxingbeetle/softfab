// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.xmlbind;

import java.io.File;
import java.io.IOException;
import java.lang.reflect.Field;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.net.InetAddress;
import java.net.MalformedURLException;
import java.net.URL;
import java.net.UnknownHostException;
import java.util.Collection;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Iterator;
import java.util.Map;
import java.util.Set;
import java.util.logging.Level;

import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.parsers.ParserConfigurationException;

import org.w3c.dom.Attr;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.NamedNodeMap;
import org.w3c.dom.Node;
import org.xml.sax.SAXException;

/**
Unpacks an XML element into a data object.
This class is a singleton; use the INSTANCE field.
This class is thread safe.
@see #unpack
*/
public class XMLUnpacker {

    /**
    Singleton instance of this class.
    */
    public final static XMLUnpacker INSTANCE = new XMLUnpacker();

    /**
    Interface for classes that can unpack a string (an XML attribute value)
    into an instance of a specific class.
    There should be one AttributeUnpacker for every type that is used as a field
    in a DataObject.
    */
    public interface AttributeUnpacker {
        Object unpack(String valueString)
        throws ParseException;
    }

    private final Map attributeUnpackers;

    private XMLUnpacker() {
        attributeUnpackers = new HashMap();
        registerUnpackers();
    }

    /**
    Instantiate a DOM document builder.

    Design note:
    Although DocumentBuilders can be reused, they cannot be used concurrently,
    so we might as well create a new one each time.
    A thread-safe sharing mechanism is possible, if DocumentBuilder
    instantiation turns out to be a heavy process.
    Same argument applies to DocumentBuilderFactory.

    @throws ParseException If no document builder could be found.
    */
    private DocumentBuilder createDocumentBuilder()
    throws ParseException {
        try {
            final DocumentBuilderFactory documentBuilderFactory =
                DocumentBuilderFactory.newInstance();
            documentBuilderFactory.setIgnoringComments(true);
            return documentBuilderFactory.newDocumentBuilder();
        } catch (ParserConfigurationException e) {
            throw new ParseException("Unable to create an XML parser", e);
        }
    }

    /**
    Convenience method that parses and unpacks an XML file.
    @param file XML file to unpack data from.
    @param dataClass Class of the DataObject to unpack into.
    @return The object containing the unpacked data.
    @throws IOException
        If reading the input file fails.
    @throws ParseException
        If there is a syntactic or semantic problem with the data.
    @throws IllegalArgumentException
        If dataClass does not implement DataObject.
    */
    public DataObject unpackFile(File file, Class dataClass)
    throws IOException, ParseException {
        // Read data from XML file into DOM tree.
        Document document;
        try {
            document = createDocumentBuilder().parse(file);
        } catch (SAXException e) {
            throw new ParseException("Error while parsing XML", e);
        }
        // Unpack data.
        return unpack(document.getDocumentElement(), dataClass);
    }

    /**
    Convenience method that parses and unpacks XML data from a URL.
    @param url URL that specifies the location of the XML data.
    @param dataClass Class of the DataObject to unpack into.
    @return The object containing the unpacked data.
    @throws IOException
        If reading from the URL fails.
    @throws ParseException
        If there is a syntactic or semantic problem with the data.
    @throws IllegalArgumentException
        If dataClass does not implement DataObject.
    */
    public DataObject unpackFromURL(URL url, Class dataClass)
    throws IOException, ParseException {
        // Read data from XML file into DOM tree.
        Document document;
        try {
            document = createDocumentBuilder().parse(url.toExternalForm());
        } catch (SAXException e) {
            throw new ParseException("Error while parsing XML", e);
        }
        // Unpack data.
        return unpack(document.getDocumentElement(), dataClass);
    }

    /**
    Unpacks an XML element into a data object.
    TODO: For now, DOM is used, maybe switch to SAX later.
    @param element The XML element to unpack.
    @param dataClass Class of the DataObject to unpack into.
    @return The object containing the unpacked data.
    @throws ParseException
        If there is a syntactic or semantic problem with the data.
    @throws IllegalArgumentException
        If dataClass does not implement DataObject.
    */
    public DataObject unpack(Element element, Class dataClass)
    throws ParseException {
        // Wrapper which fills in the context on parse exceptions.
        try {
            return unpackImpl(element, dataClass);
        } catch (ParseException e) {
            e.insertContext(element.getTagName());
            throw e;
        }
    }

    private DataObject unpackImpl(Element element, Class dataClass) // NOPMD
    throws ParseException {
        // Verify that dataClass is a subclass of DataObject.
        if (!DataObject.class.isAssignableFrom(dataClass)) {
            throw new IllegalArgumentException(
                "Given class " + dataClass.getName() + " does not implement DataObject"
                );
        }

        final Set unspecifiedFields = findAttributeFields(dataClass);
        final Map addMethods = findAddMethods(dataClass);

        // Instantiate object.
        DataObject ret;
        try {
            ret = (DataObject)dataClass.newInstance();
        } catch (IllegalAccessException e) {
            throw new ParseException(
                "Class " + dataClass.getName() + " or its parameterless constructor " +
                "is inaccessible", e
                );
        } catch (InstantiationException e) {
            throw new ParseException(
                "Failed to instantiate class " + dataClass.getName(), e
                );
        }

        // Unpack attributes.
        final NamedNodeMap attributes = element.getAttributes();
        for (int i = 0; i < attributes.getLength(); i++) {
            final Attr attribute = (Attr)attributes.item(i);

            // Get the field.
            final Field field = getField(ret.getClass(), attribute.getName());

            // Unpack the field.
            Object value;
            try {
                value = unpackAttribute(attribute.getValue(), field.getType());
            } catch (ParseException e) {
                e.insertContext(attribute.getName());
                throw e;
            }

            // Assign the field.
            final boolean wasPresent = unspecifiedFields.remove(field);
            assert wasPresent; // XML attributes are unique.
            assignField(ret, field, value);
        }

        // Unpack elements.
        for (Node node = element.getFirstChild(); node != null;
                node = node.getNextSibling()
            ) {
            if (node instanceof Element) {
                final Method addMethod =
                    (Method)addMethods.get(node.getNodeName());
                if (addMethod == null) {
                    // No method, so it must be a field.

                    // Get the field.
                    final Field field =
                        getField(ret.getClass(), node.getNodeName());
                    final Class fieldType = field.getType();

                    // Unpack the field.
                    Object value;
                    if (fieldType == String.class) {
                        // TODO: Keep this special case?
                        node.normalize();
                        value = node.getNodeValue();
                    } else if (DataObject.class.isAssignableFrom(fieldType)) {
                        value = unpack((Element)node, fieldType);
                    } else {
                        throw new ParseException(
                            "Field corresponding to element " +
                            "\"" + field.getName() + "\" " +
                            "is of type " + fieldType.getName() + ", " +
                            "which does not implement DataObject"
                            );
                    }

                    // Assign the field.
                    final boolean wasPresent = unspecifiedFields.remove(field);
                    if (wasPresent) {
                        assignField(ret, field, value);
                    } else {
                        throw new ParseException(
                            "Element \"" + field.getName() + "\" " +
                            "occurs multiple times, " +
                            "but it is mapped to a field, " +
                            "rather than an add method"
                            );
                    }
                } else {
                    // Unpack the parameter.
                    final Class paramType = addMethod.getParameterTypes()[0];
                    final Object value = unpack((Element)node, paramType);

                    // Invoke add method.
                    try {
                        addMethod.invoke(ret, new Object[] { value });
                    } catch (IllegalAccessException e) {
                        throw new ParseException(
                            "Add method " + dataClass.getName() + "." + // NOPMD
                            addMethod.getName() + " is inaccessible", e
                            );
                    } catch (InvocationTargetException e) {
                        final Throwable th = e.getTargetException();
                        if (th instanceof ParseException) {
                            throw (ParseException)th;
                        } else {
                            throw new ParseException( // NOPMD
                                "Got an exception when calling " +
                                dataClass.getName() + "." +
                                addMethod.getName(), e.getCause()
                                );
                        }
                    }
                }
            }
        }

        // Check that all attribute fields were specified.
        // First, filter out fields that are not mandatory.
        for (final Iterator i = unspecifiedFields.iterator(); i.hasNext(); ) {
            final Field field = (Field)i.next();
            if (DataObject.class.isAssignableFrom(field.getType())) {
                // Filter out element fields (fields that implement DataObject).
                i.remove();
            } else {
                Object value;
                try {
                    value = field.get(ret);
                } catch (IllegalAccessException e) {
                    throw new ParseException(
                        "Field \"" + field.getName() + "\" is inaccessible", e
                        );
                }
                // Filter out element fields that have a default value.
                // Note that primitive types always have a default value of
                // zero/false.
                if (value != null) {
                    i.remove();
                }
            }
        }
        // Any remaining fields are illegal.
        if (!unspecifiedFields.isEmpty()) {
            final StringBuffer buf = new StringBuffer();
            for (final Iterator i = unspecifiedFields.iterator(); i.hasNext(); ) {
                final Field field = (Field)i.next();
                buf.append(field.getName());
                if (i.hasNext()) {
                    buf.append(", ");
                }
            }
            throw new ParseException(
                "Unspecified fields in " + ret.getClass().getName() + ": " + buf
                );
        }

        // Done parsing, now verify the result and return it.
        ret.verify();
        return ret;
    }

    /**
    Build set of public instance fields.
    @param dataClass Class in which to look for attribute fields.
    @return a Set of Field objects.
    TODO: return a Map like findAddMethods?
    */
    private Set findAttributeFields(Class dataClass) {
        final Set ret = new HashSet();
        final Field[] fields = dataClass.getFields();
        for (int i = 0; i < fields.length; i++) {
            final Field field = fields[i];
            if ( (field.getModifiers() & Modifier.STATIC) == 0
            && !Collection.class.isAssignableFrom(field.getType())
            && !Map.class.isAssignableFrom(field.getType()) ) {
                ret.add(field);
            }
        }
        return ret;
    }

    /**
    Build a map of add methods.
    @param dataClass Class in which to look for add methods.
    @return a Map with as key the tag name (String)
        and as value the add method (Method).
    */
    private Map findAddMethods(Class dataClass)
    throws ParseException {
        final Map ret = new HashMap();
        final Method[] methods = dataClass.getMethods();
        for (int i = 0; i < methods.length; i++) {
            final Method method = methods[i];
            if (method.getName().startsWith("add")) {
                // Perform sanity checks.
                if (method.getReturnType() != Void.TYPE) {
                    throw new ParseException(
                        "Add method " + dataClass.getName() + "." + method.getName() +
                        " has non-void return type"
                        );
                }
                final Class[] parameterTypes = method.getParameterTypes();
                if (parameterTypes.length != 1) {
                    throw new ParseException(
                        "Add method " + dataClass.getName() + "." + method.getName() +
                        " takes " + parameterTypes.length + " parameters" +
                        " instead of 1"
                        );
                }
                final Class parameterType = parameterTypes[0];
                if (!DataObject.class.isAssignableFrom(parameterType)) {
                    throw new IllegalArgumentException(
                        "Parameter of add method " +
                        dataClass.getName() + "." + method.getName() +
                        " does not implement DataObject"
                        );
                }
                final Class canThrow[] = method.getExceptionTypes();
                for (int j = 0; j < canThrow.length; j++) {
                    if (!ParseException.class.isAssignableFrom(canThrow[j])) {
                        throw new ParseException(
                            "Add method " + dataClass.getName() + "." + method.getName() +
                            " throws exceptions other than ParseException"
                            );
                    }
                }

                // Add method to map.
                final StringBuffer tagName = new StringBuffer(method.getName());
                tagName.delete(0, 3); // remove "add"
                tagName.setCharAt(0, Character.toLowerCase(tagName.charAt(0)));
                ret.put(tagName.toString(), method);
            }
        }
        return ret;
    }

    /**
    Unpack a string into a simple (non-composite) object.
    @param valueString String to unpack.
    @param type Class of the object to unpack to.
    */
    private Object unpackAttribute(String valueString, Class type)
    throws ParseException {
        final AttributeUnpacker unpacker =
            (AttributeUnpacker)attributeUnpackers.get(type);
        if (unpacker == null) {
            throw new ParseException(
                "Cannot unpack values of type " + type.getName()
                );
        }
        return unpacker.unpack(valueString);
    }

    private static Field getField(Class clazz, String fieldName)
    throws ParseException {
        try {
            return clazz.getField(fieldName);
        } catch (NoSuchFieldException e) {
            throw new ParseException( // NOPMD
                "Public field \"" + fieldName + "\" does not exist" +
                " in " + clazz.getName()
                );
        }
    }

    private static void assignField(Object obj, Field field, Object value)
    throws ParseException {
        try {
            field.set(obj, value);
        } catch (IllegalAccessException e) {
            throw new ParseException(
                "Field \"" + field.getName() + "\" is inaccessible", e
                );
        }
        // Note: IllegalArgumentException cannot occur, unless there is an
        //       internal error in the code. Since it is a RuntimeException,
        //       it will be noticed should it occur nevertheless.
    }

    /**
    Register the built-in unpackers.
    These unpack commonly used classes that are part of the Java API.
    */
    private void registerUnpackers() {
        // String.
        attributeUnpackers.put(String.class, new AttributeUnpacker() {
                public Object unpack(String valueString) {
                    return valueString;
                }
            } );

        // Boolean.
        final AttributeUnpacker booleanUnpacker = new AttributeUnpacker() {
                public Object unpack(String valueString)
                throws ParseException {
                    // Note: Boolean.valueOf maps any unknown string to false,
                    //       instead of performing proper error checking.
                    if (valueString.equals("true")) {
                        return Boolean.TRUE;
                    } else if (valueString.equals("false")) {
                        return Boolean.FALSE;
                    } else {
                        throw new ParseException(
                            "Invalid boolean value: \"" + valueString + "\""
                            );
                    }
                }
            };
        attributeUnpackers.put(Boolean.class, booleanUnpacker);
        attributeUnpackers.put(Boolean.TYPE, booleanUnpacker);

        // Integer.
        final AttributeUnpacker integerUnpacker = new AttributeUnpacker() {
                public Object unpack(String valueString)
                throws ParseException {
                    try {
                        return Integer.valueOf(valueString);
                    } catch (NumberFormatException e) {
                        throw new ParseException( // NOPMD
                            "Invalid integer value: \"" + valueString + "\""
                            );
                    }
                }
            };
        attributeUnpackers.put(Integer.class, integerUnpacker);
        attributeUnpackers.put(Integer.TYPE, integerUnpacker);

        // File.
        attributeUnpackers.put(File.class, new AttributeUnpacker() {
                public Object unpack(String valueString) {
                    return new File(valueString);
                }
            } );

        // URL.
        attributeUnpackers.put(URL.class, new AttributeUnpacker() {
                public Object unpack(String valueString)
                throws ParseException {
                    try {
                        return new URL(valueString);
                    } catch (MalformedURLException e) {
                        throw new ParseException( // NOPMD
                            "Invalid URL \"" + valueString + "\"" +
                            ": " + e.getMessage()
                            );
                    }
                }
            } );

        // Network host.
        attributeUnpackers.put(InetAddress.class, new AttributeUnpacker() {
                public Object unpack(String valueString)
                throws ParseException {
                    try {
                        return InetAddress.getByName(valueString);
                    } catch (UnknownHostException e) {
                        throw new ParseException( // NOPMD
                            "Invalid host name: \"" + valueString + "\"" +
                            ": " + e.getMessage()
                            );
                    }
                }
            } );

        // Log level.
        attributeUnpackers.put(Level.class, new AttributeUnpacker() {
                public Object unpack(String valueString)
                throws ParseException {
                    try {
                        return Level.parse(valueString);
                    } catch (IllegalArgumentException e) {
                        throw new ParseException( // NOPMD
                            "Invalid log level: \"" + valueString + "\""
                            );
                    }
                }
            } );

    }
}
