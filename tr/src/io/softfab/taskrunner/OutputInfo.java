// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner;

import io.softfab.xmlbind.DataObject;

/**
 * A collection of information about an output product.
 */
public class OutputInfo implements DataObject {

    /**
     * The machine-friendly name of this product.
     */
    public String name;

    public void verify() {
        // This data is provided by the Control Center; validating it here is
        // likely to cause more trouble than it solves.
    }

}
