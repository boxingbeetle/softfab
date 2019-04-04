// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner;

import java.util.HashMap;
import java.util.Map;

import io.softfab.xmlbind.DataObject;
import io.softfab.xmlbind.ParseException;

/**
 * A collection of information about an input product.
 */
public class InputInfo implements DataObject {

    /**
     * The machine-friendly name of this product.
     */
    public String name;

    /**
     * Location of this product.
     */
    public String locator;

    /**
     * Information about the producers of this combined product.
     * For non-combined products this is always empty.
     */
    public Map producers = new HashMap();

    public void addProducer(ProducerInfo producer)
    throws ParseException {
        if (producers.put(producer.taskId, producer) != null) {
            throw new ParseException("Duplicate producer: " + producer.taskId);
        }
    }

    public boolean isCombined() {
        return !producers.isEmpty();
    }

    public void verify() {
        // This data is provided by the Control Center; validating it here is
        // likely to cause more trouble than it solves.
    }

}
