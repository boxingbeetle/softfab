# Writing a Wrapper

Wrappers are glue scripts to integrating a build or test framework into SoftFab. Among other topics are discussed: variables, passing the results and example wrappers in different languages.

## Prerequisites

Before you can start writing a wrapper you should have a way to run the process you want to hook into SoftFab fully automatically (no manual actions required) from the command line. Many tools have a command line interface (read the manual of the tool), if it is a GUI tool without command line interface, a tool such as 'Auto-It' can be used to control the GUI tool.

Most tools generate an output file in a specific file format (e.g.: txt, xml, html). The wrapper has to post-process the output file(s) of the tool and convert it into browser suitable data, e.g. to create a summary string or a summary results file in HTML format.

You should have a PC ready with a working Task Runner on it. For the installation procedure of a Factory PC, please read the [Factory PC Installation](../../start/factory_pc_installation/) document. To start learning how the SoftFab TaskRunner works, you can also use your own development PC of course. Maybe at nights, your PC can also run tasks in the future! Why not use all idle CPU time to automatically run tasks (builds and tests)?

## Task Execution

You have a choice of which script language to implement a wrapper in. This section describes what the supported script languages have in common, while the [next section](#languages) documents the peculiarities of each language.

### Variables<a id="variables"></a>

A set of variables is defined that can be used by the wrapper to execute the task. We have reserved the prefix `SF_` for variables which originate in SoftFab itself, please do not use this prefix for variables originating in your project.

Variable | Since | Purpose
-----------|:-------:|----------
SF\_REPORT\_ROOT | 3.0 | Absolute directory path of the directory where the report for this task is be written. You can also use this directory as a private workspace for this task run. This directory is created by the Task Runner before the wrapper is invoked.
SF\_REPORT\_URL | 3.0 | URL under which the directory in `SF_REPORT_ROOT` is available.
SF\_PRODUCT\_ROOT | 3.0 |Directory reserved for products created by this task run. Since a task run is not required to produce any (file-based) outputs, this directory is not created automatically. This directory will be a unique-per-job subdirectory of the directory specified with `productBaseDir` in the Task Runner configuration (`config.xml`).
SF\_PRODUCT\_URL | 3.0 | URL under which the directory in `SF_PRODUCT_ROOT` is available.
SF\_WRAPPER\_ROOT | 3.0 | Absolute directory path of the directory where the executed wrapper script is located. Support files for the wrapper, such as report templates and tool configuration files, can be stored here.
_parameter name_ | 3.0 | For each Task Runner parameter (defined in `config.xml`) a variable is defined with the same name and value as the parameter.
SF\_JOB\_ID | 3.0 | Job ID of the job this task run is part of.
SF\_TASK\_ID | 3.0 | Task ID (name) of the task this task run belongs to.
SF\_RUN\_ID | 3.0 | Run ID used to identify an individual run of the same task. Currently it is always "0".
SF\_TARGET | 3.0 | Name of the target for which this task is executing.
_parameter name_ | 3.0 | For each task parameter, a variable is defined with the same name and value as the parameter. Parameters with the "sf." prefix are not included, since they are for internal use by the Task Runner.
SF\_INPUTS | 3.0 | A list containing the names of all input products of this task.
_input name_ | 3.0 | For each input product, a variable is defined with the same name as the product and the locator of the product as its value.
SF\_OUTPUTS | 3.0 | A list containing the names of all output products of this task.
SF\_RESOURCES | 3.0 | A list containing the references of all resources reserved for the execution of this task.
_resource reference_ | 3.0 | For each reserved resource, a variable is defined with the resource reference as the name and the locator of the resource as its value.
SF\_SUMMARY | 3.0 | Full path name of the file to which the Task Runner links the "Summary" navigation tab.
SF\_RESULTS | 3.0 | Full path name of the file to which the wrapper should write the results of the task.
SF\_CC\_URL | 3.0 | The root URL of the Control Center this Task Runner belongs to. Can be used to include hyperlinks in the reports or to perform SoftFab API calls.
SF\_TR\_ID | 3.0 | ID of the Task Runner that is executing this task run.
SF\_TR\_CAPABILITIES | 3.0 | A list containing the capabilities of this Task Runner. This includes all capabilities, not just the ones that are required for running this task.
SF\_PROD | 3.0 | A dictionary containing information about combined products. The structure of the dictionary is described below.

Representation of lists and dictionaries depends on the wrapper language. For the languages that support it, the corresponding data structures are used. For other languages the representation is described below in the sections about each particular language.

<a id="SF_PROD"></a>
The SF\_PROD variable has the following structure (represented using Python syntax):

```python
SF_PROD = {
	product1: {
		taskkey1: {
			'TASK': 'taskname1',
			'RESULT': 'result1',
			'LOCATOR': 'locator1'
		},
		taskkey2: {
			'TASK': 'taskname2',
			'RESULT': 'result2',
			'LOCATOR': 'locator2'
		}
	},
	product2: {
		taskkey3: {
			'TASK': 'taskname3',
			'RESULT': 'result3',
			'LOCATOR': 'locator3'
		}
	}
}
```

The values of _`taskkey*`_ are generated from the corresponding tasks names by replacing all non-alphanumeric characters with underscores. If that operation happens to produce identical task keys for several tasks in the job the task that consumes the combined product will fail. This means one should take care of avoiding task key clashes when using combined products.

Extraction tasks receive all the same information as the corresponding execution tasks except for the resources, which are not available for extraction tasks.

### Passing Results<a id="passing-results"></a>

The SoftFab Control Center must know the following things about a task run that has finished:

*   Result: **ok** (green), **warning** (orange), **error** (red) or **inspect** (yellow).
*   Summary text to be displayed for this task run. This should be a short text which tells the user the most important information about this task run, for example: "54 passed, 12 failed, 6 skipped". In case of an error or warning, it is advisable to let the summary describe the type of error/warning.
*   Locators of the output products (if any).
*   Mid-level Data extracted from the output reports (if any).

This information is passed via the Task Runner to the Control Center using the `results.properties` file (or `extracted.properties` for extraction tasks). It should be written in the root of the report directory tree (see SoftFab variable `SF_REPORT_ROOT`). The full path of this file is available in variable `SF_RESULTS`. Its format is similar to Java property files and looks like this:

`result=<result code>`
:   Possible values for `<result code>` are "`ok`", "`warning`", "`error`" and "`inspect`".

`summary=<summary string>`
:   Any human-readable string. If absent or empty it is automatically generated based on the result code.

`output.<product name>.locator=<locator>`
:   A machine-readable string that indicates the location where the by the task produced output product can be found, for example a file path or a URL. If the framework produces multiple outputs, you should specify a separate locator for each of them. Output locators are only relevant for execution tasks. An extraction task is not supposed to report any output locators and if it does they are ignored and a warning is written in the task runner log.

`data.<key>=<value>`
:   A key-value pair containing some mid-level data relevant to this task run. The results file can contain any number of these pairs. The key name and its value are stored in the SoftFab Control Center database. If more tasks have run, a trend graph can be plotted (this can be used to monitor the software project progress and to take action if required). Here a some mid-level data examples: Size of code per module (lines of code), total number of unit tests, number of failed tests and coverage percentage. The data value has to be extracted by the wrapper from the output report (file).

`extraction.result=<value>`
:   The result of the extraction task. Possible values are the same as for `result`. This represents the result of the extraction itself, while `result` produced by the extraction task represents the result of the corresponding execution task calculated by the extraction task.

If execution of a wrapper finishes with a non-zero exit code, the Task Runner will assume there was a problem executing the wrapper and report result "error" to the Control Center, without looking at the `results.properties` file. If the `results.properties` file is missing, the Task Runner will also report result "error" to the Control Center.

If the execution task is followed by its corresponding extraction task the result code can be reported by either of them. If no result code has been reported after both execution and extraction tasks have completed the task result is automatically set to `error`. If the extraction task reports a result code and there is already one reported previously by the execution task the codes are compared and if they are equal the summary string is replaced by the new value, otherwise a conflict occurs and the old result code is not changed.

Both execution and extraction wrappers can produce mid-level data. This means you can have mid-level data without having an extraction wrapper. If both the execution and extraction wrapper produce mid-level data (not recommended), than these will be merged by the Control Center (in such case maybe an extraction wrapper is not required at all).

### Controlling the flow through the Execution Graph

Even with a successful completion, result=ok (green), of a task, the wrapper can decide to cut off a branch in the Execution Graph by **not** producing an output product locator. In this case it creates a `results.properties` file with `result=ok` but it does not create the product itself and does not specify the `output.<product name>.locator=<locator>` line. Tasks depending on this product will not be executed now and their status color will become grey. See also the [FAQ page](../../start/faq) for more detailed info.

In some cases, even with an unsuccessful completion (red) of a task (not able to make a product), you still want to continue with the Execution Graph. Very often you like to 'undo' some work done in task A by task C independent of the results and status of the 'in between' task B. Say, after installation of a firmware binary code on a system under test (SUT) you run some tests that might fail completely but you still need to uninstall the SUT. An elegant way to implement this is defining the product, produced by the 'Test' task, as `combined`. Regardless the status of the 'Test' task the 'Uninstall' task will get executed. In this example you should specify the product of the 'Installer' task as well as the product of the 'Test' task as `local` to enforce the 'Test' and 'Uninstall' task to be executed by the same Task Runner. Note that in this example both `combined` and `local` properties are set of the product produced by the 'Test' task.

### Abort Wrapper

If you want more control over aborting a task run, you can use an abort wrapper. This is a wrapper which is run just before the execution process is aborted. There is no configuration required: just put a wrapper named <code>wrapper_abort.<i>ext</i></code> (where <code><i>ext</i></code> depends on the language the abort wrapper is written in) in the same directory as <code>wrapper.<i>ext</i></code>. The abort wrapper is passed the same set of variables as the execution wrapper. It can e.g. be used to nicely close low-level log files, so still the report can be read/used, to uninstall a firmware binary or to clean up generated intermediate or temporary files.
It is also possible to use an abort wrapper to abort (mid-level data) extraction runs. In this case, you should use a file named <code>extractor_abort.<i>ext</i></code>.

## Wrapper Languages <a id="languages"></a>

The Task Runner supports the following different script languages for writing a wrapper:

<a href="#shell">Shell Script</a>
:   Unix shell script, also available under Windows by using Cygwin. Powerful and portable way of writing a wrapper.

<a href="#batch">Batch File</a>
:   Windows batch file. This is a very straightforward way of writing a wrapper script. For complex scripts it is not the best choice though because it has limited functionality.

<a href="#make">Makefile</a>
:   Input file for the Make build tool. Useful for handling dependencies.

<a href="#perl">Perl Script</a>
:   A wrapper written in Perl can be useful if it has to perform more complex tasks, for which shell scripts or batch files are not powerful enough.

<a href="#python">Python Script</a>
:   Like Perl scripts, Python scripts can be used for wrappers that have to do more complex things.

<a href="#ruby">Ruby</a>
:   Like Perl and Python scripts, Ruby scripts can be used for wrappers that have to do more complex things.

<a href="#wsh">WSH Script</a>
:   A wrapper can be written in a language supported by Windows Scripting Host (thus works on Windows only). Currently the Task Runner supports VBScript and JScript.

<a href="#ant">Ant</a>
:   A wrapper can be written as a build file for Apache Ant. Ant is the most popular build tool for Java.

<a href="#nant">NAnt</a>
:   A wrapper can be written as a build file for NAnt. NAnt is a build tool similar to Ant, but for the .NET Framework.

Which language is selected depends on the file name extension of the wrapper script. For example `wrapper.pl` will be executed as Perl script.

The Task Runner searches for a wrapper with one of the supported file name extensions in the following order: `.bat`, `.sh`, `.mk`, `.pl`, `.py`, `.rb`, `.xml`, `.build`, `.vbs`, `.js`. The first file found is used as the wrapper. Thus if there are multiple `wrapper.*` files in the same directory the one used is the one whose extension comes first in the above mentioned list.

### Shell Script Wrapper <a id="shell"></a>

|                | Execution    | Extraction
|----------------|--------------|-----------
|File name       | `wrapper.sh` | `extractor.sh`
|Available since | Task Runner  | 3.0

The variables are available through the environment, for example: `$SF_REPORT_ROOT`. The variables are not exported by default.

Hint: to spot errors in shell scripts, you can use `set -u` to treat the use of undefined variables as an error and use `set -e` to exit the shell script if a command in it returns a non-zero exit code (like the default behaviour of Make). I'm not sure how portable these `set` commands are, but they work in bash and ksh.

Portability:<br/>
Runs on every Unix-like OS (Linux, BSD, Solaris, Mac OS X etc.) and on Windows using Cygwin. Beware that each shell is a little different and some command line utilities have subtle differences between platforms as well.

On Windows/Cygwin the wrapper shell script may not start correctly. In that case a simple workaround can be used. A batch file wrapper containing the following line can be used to call Cygwin shell and execute the shell script (this will start the shell script with the same base name as the batch file itself and located in the same directory):

`@start /b /wait %~dpns0.sh`

<a id="dict"></a>
Dictionary values of the variables are represented as several simple variables with names constructed based on the dictionary keys. The following example shows how the value of `SF_PROD` (from the example [above](#SF_PROD)) is represented:

```shell
SF_PROD_KEYS=product1 product2
SF_PROD_product1_KEYS=taskkey1 taskkey2
SF_PROD_product1_taskkey1_KEYS=TASK RESULT LOCATOR
SF_PROD_product1_taskkey1_TASK=taskname1
SF_PROD_product1_taskkey1_RESULT=result1
SF_PROD_product1_taskkey1_LOCATOR=locator1
SF_PROD_product1_taskkey2_KEYS=TASK RESULT LOCATOR
SF_PROD_product1_taskkey2_TASK=taskname2
SF_PROD_product1_taskkey2_RESULT=result2
SF_PROD_product1_taskkey2_LOCATOR=locator2
SF_PROD_product2_KEYS=taskkey3
SF_PROD_product2_taskkey3_KEYS=TASK RESULT LOCATOR
SF_PROD_product2_taskkey3_TASK=taskname3
SF_PROD_product2_taskkey3_RESULT=result3
SF_PROD_product2_taskkey3_LOCATOR=locator3
```

Single level lists are represented as strings with the list elements space-separated. More complex structures containing lists are currently not supported.

### Batch File Wrapper <a id="batch"></a>

|                | Execution     | Extraction
|----------------|---------------|-----------
|File name       | `wrapper.bat` | `extractor.bat`
|Available since | Task Runner   | 3.0

The variables are available through the environment, for example: `%SF_REPORT_ROOT%`.

Portability:<br/>
Runs only on Windows.

If in a wrapper directory both `wrapper.bat` and `wrapper.sh` exist, the batch file is used on Windows and the shell script is used on all other platforms.

Dictionary values of the variables are represented in the same way as for [shell scripts](#dict). Single level lists are represented as strings with the list elements space-separated. More complex structures containing lists are currently not supported.

### Makefile Wrapper <a id="make"></a>

|                | Execution    | Extraction
|----------------|--------------|-----------
|File name       | `wrapper.mk` | `extractor.mk`
|Available since | Task Runner  | 3.0

The variables are available as Make variables, for example: `${SF_REPORT_ROOT}`. The variables are not exported by default.

Portability:<br/>
We only tested with GNU Make, but probably other versions of Make will work as well. GNU Make is available on many platforms, but typically a Makefile runs shell commands, which might not be available on all platforms or might have small variations in functionality.

Example code for generating a results file:<br/>
(make sure indenting is done with tabs)

```make
all: image
	echo "result=ok" > ${SF_RESULTS}
	echo "summary=build successful" >> ${SF_RESULTS}
	echo "output.image.locator=${SF_PRODUCT_URL}/image/" >> ${SF_RESULTS}
```

Dictionary values of the variables are represented in the same way as for [shell scripts](#dict). Single level lists are represented as strings with the list elements space-separated. More complex structures containing lists are currently not supported.

### Perl Wrapper <a id="perl"></a>

|                | Execution    | Extraction
|----------------|--------------|-----------
|File name       | `wrapper.pl` | `extractor.pl`
|Available since | Task Runner  | 3.0

The variables are available as regular scalar variables in the global context of the Perl script, for example: `$SF_REPORT_ROOT`. Note: if the perl wrapper contains `use strict;` it is necessary to explicitly indicate that the variables provided by the Task Runner are in the global scope when accessing those variables. So instead of `$SF_REPORT_ROOT` one should use `$::SF_REPORT_ROOT`.

Portability:<br/>
The same wrapper script should work on any platform where Perl is available. Although to ensure full portability one must not make assumptions about path syntax and use dedicated perl modules to manipulate paths in a portable way.

Example code for generating a results file:

```perl
use strict;
use File::Spec;
if (open(RESULT, '>', $::SF_RESULTS)) {
    print RESULT <<"RESDATA";
result=ok
summary=task successful
output.image.locator=$::SF_PRODUCT_URL/image/
RESDATA
    close(RESULT);
} else {
    die "Failed to open the results file '$::SF_RESULTS': $!\n";
}
```
### Python Wrapper <a id="python"></a>

|                | Execution    | Extraction
|----------------|--------------|-----------
|File name       | `wrapper.py` | `extractor.py`
|Available since | Task Runner  | 3.0

The variables are available as ordinary Python variables, for example: `SF_REPORT_ROOT`.

Portability:<br/>
The same wrapper script should work on any platform where Python is available. It is best if you use slashes ('/') in your file paths, since that works both on Windows and Unix-like systems. For complex path operations, use the `os.path` module.

Example code for generating a results.properties file:

```python
resultsFile = file(SF_RESULTS, 'w')
print('result=ok', file=resultsFile)
print('summary=task successful', file=resultsFile)
print('output.TESTREPORT.locator=' + SF_PRODUCT_URL + '/testreport.html', file=resultsFile)
resultsFile.close()
```

### Ruby Wrapper <a id="ruby"></a>

|                | Execution    | Extraction
|----------------|--------------|-----------
|File name       | `wrapper.rb` | `extractor.rb`
|Available since | Task Runner  | 3.0

The variables are available as global Ruby variables, for example: `$SF_REPORT_ROOT`.

Portability:<br/>
The same wrapper script should work on any platform where Ruby is available.

Example code for generating a results.properties file:

```ruby
out = File.new($SF_RESULTS, 'w')
out << "result=ok\n"
out << "summary=task successful\n"
out << "output.image.locator=#{$SF_PRODUCT_URL}/image/\n"
out.close
```

### WSH Wrapper <a id="wsh"></a>

|                | Execution     | Extraction      | Language
|----------------|---------------|-----------------|---------
|File name       | `wrapper.js`  | `extractor.js`  | JScript
|                | `wrapper.vbs` | `extractor.vbs` | VBScript
|Available since | Task Runner   | 3.0

The variables are available as regular variables in the global context of the script.

Portability:<br/>
Available only on Windows. On older versions of Windows it may be necessary to install redistributable Windows Scripting Engine.

It is possible to reuse JScript or VBScript functions in all your wrappers. In the wrappers directory, create a subdirectory named `common` and put your common code there. All script files named `*.js` or `*.vbs` which are located in the `common` directory will be automatically included in the WSH interpreter when your wrapper is executed.

Dictionaries are represented as objects with the keys as properties. Since VBScript does not have a built-in mechanism for enumerating object properties the objects representing dictionaries contain two additional methods. `size()` returns the number of the properties (dictionary keys). `get(key)` returns the value of the property given it's key, which can be the name of the property or an integer (property index that can be used to enumerate property values).

### Ant <a id="ant"></a>

|                | Execution     | Extraction
|----------------|---------------|-----------
|File name       | `wrapper.xml` | `extractor.xml`
|Available since | Task Runner   | 3.0

Portability:<br/>
Ant is available on any platform that runs Java.

The variables are available as Ant properties. By default these properties are passed down to Ant subtasks, but you can suppress this by adding `inheritAll="false"` to the `<ant>` task tag. List values are represented as space-separated strings. Dictionary values are represented by a dot-separated property name, for example "SF\_PROD.SOURCE\_ROOT.export.RESULT".

Example Ant wrapper:

```xml
<project default="run">
    <target name="run">
        <!-- run build -->
        <ant dir="${SOURCE_ROOT}" target="jar"
            output="${SF_SUMMARY}" inheritAll="false"/>
        <!-- make product dir -->
        <mkdir dir="${SF_PRODUCT_ROOT}"/>
        <!-- move output files to product dir -->
        <move todir="${SF_PRODUCT_ROOT}">
            <fileset dir="${SOURCE_ROOT}/generated/bin" includes="*.jar"/>
        </move>
        <!-- write results file -->
        <echo file="${SF_RESULTS}">
result=ok
summary=build successful
output.JAR_URL.locator=${SF_PRODUCT_URL}
        </echo>
    </target>
</project>
```

In this example, `SOURCE_ROOT` is an input product that contains the directory path of the source tree to build. The build is done by running Ant on the source tree with the `"jar"` target. The build creates a number of JAR files in the directory `generated/bin` under the source tree. These JARs are moved to the products directory, so they can be served by the web server. The URL of the JARs on this web server becomes the locator of the `JAR_URL` output product.

### NAnt <a id="nant"></a>

|                | Execution       | Extraction
|----------------|-----------------|-----------
|File name       | `wrapper.build` | `extractor.build`
|Available since | Task Runner     | 3.0

Portability:<br/>
NAnt is available on any platform that runs .NET: it works with Microsoft's .NET implementation and with Mono.

The variables are available as NAnt properties. By default these properties are passed down to NAnt subtasks, but you can suppress this by adding `inheritall="false"` to the `<nant>` task tag. List values are represented as space-separated strings. Dictionary values are represented by a dot-separated property name, for example "SF\_PROD.SOURCE\_ROOT.export.RESULT".

Below is an elaborate example showing how to run unit tests in the MSTest tool and extract mid-level data from the results file (.trx):

```xml
<project>
    <property name="builddir" value="${SOURCE_ROOT}\build"/>
    <!--
    Note: If the .trx file is created on a network drive, MSTest runs the tests in a different security context.
    -->
    <property name="trxfile" value="${builddir}\results_${SF_JOB_ID}_${SF_TASK_ID}.trx"/>
    <property name="resultcounters" value="total executed passed error failed timeout aborted inconclusive passedButRunAborted notRunnable notExecuted disconnected warning completed inProgress pending"/>

    <!-- Execute unit tests. -->
    <nant buildfile="${builddir}\unittest.build" inheritall="false">
        <properties>
            <property name="test.resultsfile" value="${trxfile}"/>
        </properties>
    </nant>

    <!-- Generate a report in HTML format. -->
    <style style="${xsldir}\MsTestReport2008.xsl" in="${trxfile}" out="${SF_SUMMARY}"/>

    <!-- Extract test result counters. -->
    <foreach item="String" in="${resultcounters}" delim=" " property="counter">
        <xmlpeek file="${trxfile}" property="count.${counter}" xpath="/tt:TestRun/tt:ResultSummary/tt:Counters/@${counter}">
            <namespaces>
                <namespace prefix="tt" uri="http://microsoft.com/schemas/VisualStudio/TeamTest/2006"/>
            </namespaces>
        </xmlpeek>
    </foreach>

    <!--
    Determine test result.
    Note that every line overrides a subset of the situations from the previous line.
    -->
    <property name="result" value="error"/>
    <property name="result" value="warning" if="${int::parse(count.passed) + int::parse(count.failed) == int::parse(count.total)}"/>
    <property name="result" value="ok" if="${int::parse(count.passed) == int::parse(count.total)}"/>

    <!-- Generate a SoftFab results file. -->
    <echo file="${SF_RESULTS}">
        result=${result}
        summary=${count.passed} passed, ${count.failed} failed, ${count.error} errors, ${int::parse(count.total) - int::parse(count.passed) - int::parse(count.failed) - int::parse(count.error)} other
        output.TEST_RESULT.locator=token
    </echo>
    <foreach item="String" in="${resultcounters}" delim=" " property="counter">
        <echo file="${SF_RESULTS}" append="true" message="data.count.${counter}=${property::get-value('count.' + counter)}"/>
    </foreach>
</project>
```

The `xsldir` variable can be implemented as a framework parameter or as a Task Runner parameter; it should point to a directory containing XSL style sheets for creating nice human-readable reports from XML data. The `SOURCE_ROOT` variable is the locator of an input product named `SOURCE_ROOT`. The output product `TEST_RESULT` is a combined token product of which the producer result codes can be inspected by a consuming task to decide whether changes to the code base should be automatically promoted or not.
