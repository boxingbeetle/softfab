// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner.config;

import java.util.regex.Pattern;

import io.softfab.xmlbind.DataObject;
import io.softfab.xmlbind.ParseException;

public class Parameter implements DataObject {

    private static final Pattern PARAM_NAME_PATTERN = Pattern.compile(
        "^|[A-Za-z_][A-Za-z_0-9]*$"
        );

    /**
    The name of this parameter.
    */
    public String name;

    /**
    The value of this parameter.
    */
    public String value;

    public void verify()
    throws ParseException {
        if (!PARAM_NAME_PATTERN.matcher(name).matches()) {
            throw new ParseException("Invalid parameter name \"" + name + "\"");
        }
    }
}
