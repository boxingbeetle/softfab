// SPDX-License-Identifier: BSD-3-Clause

package io.softfab.taskrunner;

import java.util.Collection;
import java.util.HashMap;
import java.util.Iterator;
import java.util.Map;

class WrapperVariableFlattener
implements TaskRun.StartupScriptGenerator {

    private final char separator;
    private final Map<String, Object> variables;

    WrapperVariableFlattener(char separator) {
        this.separator = separator;
        variables = new HashMap<>();
    }

    public Iterator<Map.Entry<String, Object>> getVariables() {
        return variables.entrySet().iterator();
    }

    public boolean encodeCollectionOpen(TaskRun.Context context, Collection value) {
        variables.put(TaskRun.join(context.getNames(), separator), value);
        return false;
    }

    public void encodeCollectionClose(TaskRun.Context context, Collection value) {
        // The encodeCollectionOpen() method returned false, so this method will not be called.
        assert false;
    }

    public boolean encodeMapOpen(TaskRun.Context context, Map value) {
        variables.put(TaskRun.join(context.getNames(), separator) + separator + "KEYS", value.keySet());
        return true;
    }

    public void encodeMapClose(TaskRun.Context context, Map value) {
        // Nothing to do.
    }

    public void encodeString(TaskRun.Context context, String value) {
        variables.put(TaskRun.join(context.getNames(), separator), value);
    }

}
