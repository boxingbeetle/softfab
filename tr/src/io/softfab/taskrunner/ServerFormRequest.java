// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner;

import java.io.UnsupportedEncodingException;
import java.net.URLEncoder;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public class ServerFormRequest extends ServerRequest {

    private class Param {
        final String name;
        final String value;
        Param(String name, String value) {
            this.name = name;
            this.value = value;
        }
    }

    private static String paramString(List<Param> params) {
        final StringBuffer buf = new StringBuffer();
        try {
            boolean first = true;
            for (final Param param : params) {
                if (first) {
                    first = false;
                } else {
                    buf.append('&');
                }
                buf.append(
                        URLEncoder.encode(param.name, "UTF-8")).
                    append('=').append(
                        URLEncoder.encode(param.value, "UTF-8"));
            }
        } catch (UnsupportedEncodingException e) {
            throw new RuntimeException( // NOPMD
                "URL encoding in UTF-8 format is not supported: " + e
                );
        }
        return buf.toString();
    }

    private final List<Param> queryParams;
    private final List<Param> bodyParams;

    public ServerFormRequest(String page) {
        super(page);
        queryParams = new ArrayList<>();
        bodyParams = new ArrayList<>();
    }

    /**
     * Adds a parameter that identifies the resource being modified.
     * @param name Parameter name.
     * @param value Parameter value.
     */
    public void addQueryParam(String name, String value) {
        queryParams.add(new Param(name, value));
    }

    /**
     * Adds a parameter that indicates how the resource should be modified.
     * @param name Parameter name.
     * @param value Parameter value.
     */
    public void addBodyParam(String name, String value) {
        bodyParams.add(new Param(name, value));
    }

    /**
     * Adds a parameter that indicates how the resource should be modified.
     * @param name Parameter name.
     * @param values Sequence of parameter values.
     */
    public void addBodyParam(String name, Iterable<String> values) {
        for (final String value : values) {
            bodyParams.add(new Param(name, value));
        }
    }

    /**
     * Adds multiple parameters that indicate how the resource should be modified.
     * @param map Parameters to add.
     */
    public void addBodyParams(Map<String, String> map) {
        for (final Map.Entry<String, String> entry : map.entrySet()) {
            addBodyParam(entry.getKey(), entry.getValue());
        }
    }

    public String getQuery() {
        return paramString(queryParams);
    }

    public String getBodyType() {
        return bodyParams.isEmpty()
            ? null : "application/x-www-form-urlencoded";
    }

    public String getBody() {
        return paramString(bodyParams);
    }

}
