// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner;

public class ServerXMLRequest extends ServerRequest {

    private final String request;

    public ServerXMLRequest(String page, String request) {
        super(page);
        this.request = request;
    }

    public String getQuery() {
        return null;
    }

    public String getBodyType() {
        return "text/xml";
    }

    public String getBody() {
        return request;
    }

}
