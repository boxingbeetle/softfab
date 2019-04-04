// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner;

/**
 * A request to the Control Center.
 */
public abstract class ServerRequest {

    private final String page;

    protected ServerRequest(String page) {
        this.page = page;
    }

    /**
     * Gets the name of the page to send the request to.
     * @return Page name.
     */
    public String getPage() {
        return page;
    }

    /**
     * Gets the query part of the URL.
     * @return Query string, or null if this request does not use a query.
     */
    public abstract String getQuery();

    /**
     * Gets the MIME type of the request body.
     * @return MIME type, or null if this request does not have a body.
     */
    public abstract String getBodyType();

    /**
     * Gets the data of the request body.
     * @return Body data, or null if this request does not have a body.
     */
    public abstract String getBody();

}
