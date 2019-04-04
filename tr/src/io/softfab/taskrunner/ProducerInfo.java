// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner;

import io.softfab.xmlbind.DataObject;

public class ProducerInfo implements DataObject {

    /**
    The name of the task that has produced this instance of the product.
    */
    public String taskId;

    /**
    Location of this instance of the combined product.
    */
    public String locator;

    /**
    The result of the task that has produced this instance of the product.
    */
    public String result;

    public void verify() {
        //System.out.println("Producer: " + taskId + ", " + result + ", " + locator);
        // This data is provided by the Control Center; validating it here is
        // likely to cause more trouble than it solves.
    }
}
