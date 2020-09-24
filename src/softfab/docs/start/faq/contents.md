# Frequently Asked Questions

Answers to common questions from new users.

## Questions<a id="questions"></a>

*   [What is the difference between orange and red tasks?](#orange_red)
*   [How to rename a Framework or Task Definition?](#rename_framework_or_teskdef)
*   [How to delete a Framework or Task Definition?](#delete_framework_or_teskdef)
*   [Why is the next task not carried out, if the previous task succeeded?](#next_task_not_executed)
*   [Why is the next task still carried out, if the previous task failed with result=error?](#next_task_executed)
*   [What causes: Error writing "execute.sh": java.io.IOException: Error writing content?](#IOException)

### My question is not listed here, please help?

You can request community support by [posting your question on GitHub](https://github.com/boxingbeetle/softfab/issues/new?labels=question).

Commercial support is available from [Boxing Beetle](https://boxingbeetle.com/services/).

## Answers<a id="answers"></a>

### What is the difference between orange and red tasks?<a id="orange_red"></a>

Orange (result code `warning`) is used when the task execution itself went fine, but there is a problem with the content that was processed. For example, a compiler found suspicious constructs in the source code or a test tool encountered failing test cases. Red (result code `error`) is used when the task execution could not be completed. For example, an error in the source code prevented compilation from completing or a test tool encountered a syntax error in a test script.

We make this distinction for a number of reasons. The primary reason is that the purpose of testing is to get information about the quality of a piece of software. Red means that the task failed to acquire that information, so you don't know how good or bad the software under test is. Orange means the task was able to acquire that information, but that there are problems with the quality of the software under test. This means there is still work to do, but at least you know where you are.

A secondary reason for having two separate colors is that when a task ends up red, there is typically a problem in the test setup or the test scripts, while when a task ends up orange, there is typically a problem in the software under test. This means that the first person to investigate a red task would be a tester and for an orange task it would be a developer. And even if those two are the same person in your project, it still helps to determine where to start looking for the problem.

Related information:

*   [job/task colors](../user_manual/#history) in the User Manual
*   [passing results](../../reference/wrappers/#passing-results) in Writing a Wrapper

### How to rename a Framework or Task Definition?<a id="rename_framework_or_teskdef"></a>

Currently a Rename function is not yet available, but the following work-around does the trick.

From the homepage of your factory go to: Configure ▸ Design ▸ Frameworks/Task Definitions. Select the Framework or Task Definition to be renamed. Edit the Framework or Task Definition and select the 'Save As' button at the bottom of the page. Now enter a new name and 'Save'. Next you will have to delete the old Framework or Task Definition.

### How to delete a Framework or Task Definition?<a id="delete_framework_or_teskdef"></a>

From the homepage of your factory go to: Configure ▸ Design ▸ Frameworks/Task Definitions. A list with all Frameworks or Task Definitions is presented. Scroll to the very right of the window, and you will find the 'Delete' link. If the Framework is still used by one or more Task Definitions, it cannot be deleted now. First remove the dependency in the involved Task Definitions. Also if a Task Definition is used by one or more Configurations, it cannot be deleted. First remove the dependency in the involved Configurations.

### Why is the next task not carried out, if the previous task succeeded?<a id="next_task_not_executed"></a>

Let's assume your [execution graph](../../concepts/exegraph/) looks similar to this:

<?graph build?>

<!-- TODO: Also render an example of the tables on ShowReport. -->

The `test` task will only start to execute if the `BINARY` product has been produced. It is possible for the `build` task to succeed without producing the `BINARY` product. In most cases this is due to an omission in the wrapper script.

The `BINARY` product is considered to be produced if `output.BINARY.locator` has been written to `results.properties` by the wrapper script of the `build` task. For more info read the document about [passing results](../../reference/wrappers/#passing-results).

Simple example in Batch file script language (`wrapper.bat`):

```bat
ECHO %SF_TASK_ID% is running...
devenv /build Release /project Name ProjName.sln
IF NOT EXIST %WORKSPACE_AREA%/Name.exe GOTO build_failed

build_ok:
ECHO result=ok > %SF_RESULTS%
ECHO summary=build successful >> %SF_RESULTS%
ECHO output.BINARY.locator=%WORKSPACE_AREA%/Name.exe >> %SF_RESULTS%
GOTO end

build_failed:
ECHO result=error > %SF_RESULTS%
ECHO summary=build failed >> %SF_RESULTS%
GOTO end

end:
ECHO %SF_TASK_ID% is finished.
```

### Why is the next task still carried out, if the previous task failed with result=error?<a id="next_task_executed"></a>

As with [the previous question](next_task_not_executed), the key thing to note is that for inter-task dependencies, it only matters whether a product was produced or not. So the fact that the first task failed is irrelevant.

If a wrapper writes the output location to `results.properties` without checking whether the output was actually produced, dependent tasks will attempt to run and then fail to find the product they need. To avoid this, make sure your wrapper only writes for example `output.BINARY.locator` to the results if the binary was actually produced.

For tasks that do more than one thing, it can be useful to produce output products even when the task doesn't run to completion. For example, if your build produces three binaries and building the first two succeeded and building the third failed, the task result is `error` but testing of the first two binaries can proceed.

### What causes: Error writing "execute.sh": java.io.IOException: Error writing content?<a id="IOException"></a>

If you see such error message in the task summary string, then the Task Runner could not write the file `execute.sh` (or `.bat`, `.pl` etc., depending on the wrapper language used). This file contains a generated script that bootstraps the wrapper execution.

The most likely cause of this problem is that the disk containing the reports directory of the Factory PC that attempted to run the task is out of free space.
