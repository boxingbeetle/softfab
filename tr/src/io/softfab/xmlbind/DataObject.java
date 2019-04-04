// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.xmlbind;

/**
A collection of data fields,
where each field corresponds to an element or attribute in XML.
Attribute fields can be of any type supported by XMLUnpacker.
Element fields must be of a type that implements DataObject itself.
Every attribute field is mandatory:
by forcing that the XML contains every single value,
users can be sure the list of values is complete and there are not some
implicit/default values hidden inside the code.
Element fields are optional: if a Factory PC does not have certain
capabilities, it does not make sense to configure them.

Elements that can occur multiple times are set using add methods:
if the tag name is "someTag", the method called is "addSomeTag".
An add method should have a single parameter, the DataObject to add,
the type of this parameter is used to bind the tag.
The return type of an add method must be void.
The fields used to store the data from these elements should either
be non-public, or implement java.util.Collection or java.util.Map,
so that XMLUnpacker can recognise them.
TODO: With JDK 1.5, use a generic list instead of a method.

Hint: Make sure that classes that implement DataObject are public,
otherwise XMLUnpacker cannot access them when unpacking the data.
The same is true for a superclass of a class that implements DataObject,
if that superclass contains fields that will be used to unpack data to.

TODO: Move some of this text to package-wide HTML.
TODO: Look into relation with capabilities again, once they are implemented.
*/
public interface DataObject {

    /**
    Verifies the validity of the data in this object.
    This method is called after all fields have been parsed.
    @throws ParseException if the data is not valid.
    */
    void verify()
    throws ParseException;

}
