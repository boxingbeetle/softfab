// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner;

import java.io.UnsupportedEncodingException;
import java.net.URLEncoder;
import java.util.HashMap;
import java.util.Iterator;
import java.util.Map;

public class ServerFormRequest extends ServerRequest {

    private static String paramString(Map<String, String> params) {
        final StringBuffer buf = new StringBuffer();
        try {
            boolean first = true;
            for (final Map.Entry<String, String> entry : params.entrySet()) {
                if (first) {
                    first = false;
                } else {
                    buf.append('&');
                }
                buf.append(
                        URLEncoder.encode(entry.getKey(), "UTF-8")).
                    append('=').append(
                        URLEncoder.encode(entry.getValue(), "UTF-8"));
            }
        } catch (UnsupportedEncodingException e) {
            throw new RuntimeException( // NOPMD
                "URL encoding in UTF-8 format is not supported: " + e
                );
        }
        return buf.toString();
    }

    private final Map<String, String> queryParams;
    private final Map<String, String> bodyParams;

    public ServerFormRequest(String page) {
        super(page);
        queryParams = new HashMap<>();
        bodyParams = new HashMap<>();
    }

    /**
     * Adds a parameter that identifies the resource being modified.
     * @param name Parameter name.
     * @param value Parameter value.
     */
    public void addQueryParam(String name, String value) {
        queryParams.put(name, value);
    }

    /**
     * Adds a parameter that indicates how the resource should be modified.
     * @param name Parameter name.
     * @param value Parameter value.
     */
    public void addBodyParam(String name, String value) {
        bodyParams.put(name, value);
    }

    /**
     * Adds multiple parameters that indicate how the resource should be modified.
     * @param map Parameters to add.
     */
    public void addBodyParams(Map<String, String> map) {
        bodyParams.putAll(map);
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
