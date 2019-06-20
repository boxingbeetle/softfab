# Frequently Asked Questions

Answers to common questions from new users.

<p class="todo">TODO: Do we facilitate contacting the SoftFab team?</p>

The questions<a id="questions"></a>
-----------------------------------

*   [What is the difference between orange and red tasks?](#orange_red)
*   [How to rename a Framework or Task Definition?](#rename_framework_or_teskdef)
*   [How to delete a Framework or Task Definition?](#delete_framework_or_teskdef)
*   [Why is the next task not carried out, if the previous task succeeded?](#next_task_not_executed)
*   [Why is the next task still carried out, if the previous task failed with result=error?](#next_task_executed)
*   [The following error message is not clear: Error writing "execute.pl": java.io.IOException: Error writing content?](#IOException)

### My question is not listed here, please help?

<!--
Please, contact the [SoftFab team](../contact/) with your question.
-->
Please, contact the SoftFab team with your question.

The answers<a id="answers"></a>
-----------------------------------

### What is the difference between orange and red tasks?<a id="orange_red"></a>

Orange (result code "warning") should be used when the task execution itself went fine, but there is a problem with the content that was processed. For example, a compiler found suspicious constructs in the source code or a test tool encountered failing test cases. Red (result code "error") should be used when the task execution could not be completed. For example, an error in the source code prevented compilation and linking from completing or a test tool encountered a syntax error in a test script.

We make this distinction for a number of reasons. The primary reason is that the purpose of testing is to get information about the quality of a piece of software. Red means that the task failed to acquire that information, so you don't know how good or bad the software under test is. Orange means the task was able to acquire that information, but that there are problems with the quality of the software under test. This means there is still work to do, but at least you know where you are.

A secondary reason for having two separate colors is that when a task ends up red, there is typically a problem in the test setup or the test scripts, while when a task ends up orange, there is typically a problem in the software under test. This means that the first person to investigate a red task would be a tester and for an orange task it would be a developer. And even if those two are the same person in your project, it still helps to determine where to start looking for the problem.

Related information:

*   [job/task colors](../user_manual/#history) in the User Manual
*   [passing results](../../reference/wrappers/#passing-results) in Writing a Wrapper

### How to rename a Framework or Task Definition?<a id="rename_framework_or_teskdef"></a>

Currently a Rename function is not yet available, but the following work-around does the trick.

From the homepage of your factory go to: Configure / Design / Frameworks or Task Definitions. Select the Framework or Task Definition to be renamed. Edit the Framework or Task Definition and select the 'Save As' button at the bottom of the page. Now enter a new name and 'Save'. Next you will have to delete the old Framework or Task Definition.

### How to delete a Framework or Task Definition?<a id="delete_framework_or_teskdef"></a>

From the homepage of your factory go to: Configure / Design / Frameworks or Task Definitions. A list with all Frameworks or Task Definitions is presented. Scroll to the very right of the window, and you will find the 'Delete' link. If the Framework is still used by one or more Task Definitions, it cannot be deleted now. First remove the dependency in the involved Task Definitions. Also if a Task Definition is used by one or more Configurations, it cannot be deleted. First remove the dependency in the involved Configurations.

### Why is the next task not carried out, if the previous task succeeded?<a id="next_task_not_executed"></a>

In the execution graph you have defined e.g. a first framework `build`, a product `BINARY` and a next framework `test` as follows: `build` ==> `BINARY` ==> `test`. A task derived from framework `test` will only start to execute if the output.`BINARY`.locator has been set in the wrapper script of framework `build`. Thus, if the task `build` succeeds, the output locator should be set. For more info read the document about [passing results](../../reference/wrappers/#passing-results). You can always check the content of the file behind SF\_RESULTS. In your browser simply open e.g. `http://.../reports/20090621/2050-30E2/build/results.properties`

Simple example in Batch file script language (wrapper.bat):

```bat
ECHO %SF_TASK_ID% is running...
devenv /build Release /project Name ProjName.sln
IF NOT EXIST %WORKSPACE_AREA%/Name.exe GOTO build_failed

build_ok:
ECHO result=ok > %SF_RESULTS%
ECHO summary=build successful >> %SF_RESULTS%
ECHO output.BINARY.locator="successfully created new BUILD product" >> %SF_RESULTS%
GOTO end

build_failed:
ECHO result=error > %SF_RESULTS%
ECHO summary=build failed >> %SF_RESULTS%
GOTO end

end:
ECHO %SF_TASK_ID% is finished.
```

### Why is the next task still carried out, if the previous task failed with result=error?<a id="next_task_executed"></a>

In the execution graph you have defined e.g. a first framework `build`, a product `BINARY` and a next framework `test` as follows: `build` ==> `BINARY` ==> `test`. A task derived from framework `test` will only start to execute if the output.`BINARY`.locator has been set in the wrapper script of framework `build`. Thus, if the task `build` fails, the output locator should **not** be set! For more info read the document about [passing results](../../reference/wrappers/#passing-results). You can always check the content of the file behind SF\_RESULTS. In your browser simply open e.g. `http://.../reports/20090621/2050-30E2/build/results.properties`

Simple example in Batch file script language (wrapper.bat):

```bat
ECHO %SF_TASK_ID% is running...
devenv /build Release /project Name ProjName.sln
IF NOT EXIST %WORKSPACE_AREA%/Name.exe GOTO build_failed

build_ok:
ECHO result=ok > %SF_RESULTS%
ECHO summary=build successful >> %SF_RESULTS%
ECHO output.BINARY.locator="new build product" >> %SF_RESULTS%
GOTO end

build_failed:
ECHO result=error > %SF_RESULTS%
ECHO summary=build failed >> %SF_RESULTS%
GOTO end

end:
ECHO %SF_TASK_ID% is finished.
```

### The following error message is not clear: Error writing "execute.pl": java.io.IOException: Error writing content<a id="IOException"></a>

If you see such error message in the summary string, then the Task Runner cannot write the content to the file 'execute.pl'. Please check how many space is left on the disc (partition or network share) where this file is written to (to find out see wrapper variable SF\_REPORT\_ROOT). It can be the local hard disk of the Factory PC (e.g. C:\\) or the project's network drive. Clean-up some disk space, backup files, compress files or ask the help desk to increase the quota of the network drive. It is wise to write a script to automatically check the disc space and perform clean-ups (e.g. by using a framework to monitor disc space on a daily schedule).
