# API Calls

You can interface with SoftFab programmatically using API calls over HTTP.

<p class="todo">
The current API was created in an ad-hoc way. We intend to redesign it in proper REST style in a future major release. But in the mean time, you can use the API documented here.
</p>

If you are new to the SoftFab API, please read the section about the [call mechanism](#call) first.

##Function List<a id="functions"></a>

These are the currently available API functions:

<!-- note: keep functions listed in alphabetical order -->

*   [Abort](#Abort)
*   [GetFactoryInfo](#GetFactoryInfo)
*   [GetJobHistory](#GetJobHistory)
*   [GetJobInfo](#GetJobInfo)
*   [GetResourceInfo](#GetResourceInfo)
*   [GetTagged](#GetTagged)
*   [GetTaskDefParams](#GetTaskDefParams)
*   [InspectDone](#InspectDone)
*   [LoadExecuteDefault](#LoadExecuteDefault)
*   [ResourceControl](#ResourceControl)
*   [TaskAlert](#TaskAlert)
*   [TaskRunnerExit](#TaskRunnerExit)
*   [TriggerSchedule](#TriggerSchedule)

How to call an API function from a wrapper-script is explained [here](#call).

If you would like to query or change a certain piece of information on the Control Center and there is currently no API call that offers the desired functionality, please let us know.

### Abort<a id="Abort"></a>

Aborts one or more named (if they exist) or all tasks in a list of jobs. Multiple tasks can be aborted in multiple jobs. The existence of all mentioned tasks is not enforced in all the jobs. The API call should be interpreted as: abort these tasks in these jobs if they exist. This means that under certain conditions it is possible that after return not even one task is aborted.

Possible associated waiting or running extraction tasks are **not** aborted.

Arguments:

jobId: (multiple, at least one)
:   The job ID of the job to abort tasks of.

taskName: (optional, multiple)
:   The names of the tasks to abort. If this argument is omitted, all tasks in the job will be aborted.

onlyWaiting: (optional)
:   Abort only tasks that are waiting: do not abort currently running tasks. Possible values are `true` and `false`. If absent `false` is implied.

Returns:

On success 'Abort' returns an XML structure tagged by `<abortedtasks>` with 0 or more `<taskref>` task references; 1 for every successful aborted task.

Examples:

`http://factory.company.com/Abort?jobId=080910-1234-ABCD&taskName=build`
:   Abort the "build" task in the specified job.

`http://factory.company.com/Abort?jobId=080910-1234-ABCD&jobId=080910-2345-BCDE`
:   Abort all running and waiting tasks in two specified jobs.

`http://factory.company.com/Abort?jobId=080910-2345-BCDE&onlyWaiting=true`
:   Abort all waiting tasks in the specified job.

### GetFactoryInfo<a id="GetFactoryInfo"></a>

Exports factory information in XML format. Next to the factory name the root URL, the Control Center version number and the names and sizes of all internal data tables are exported.

Arguments:

none

Example:

`http://factory.company.com/GetFactoryInfo`
:   Return all kind of monitoring information in XML format of "factory".

### GetJobHistory<a id="GetJobHistory"></a>

Queries the job history. The returned XML contains the matching job IDs; you can use the [GetJobInfo](#GetJobInfo) API call to get detailed information about each job.

Arguments:

ctabove: (optional)
:   Only return jobs created on or after the given date. The format of the date is "yyyy-mm-dd", optionally extended with a time stamp in the format "hh:mm".

ctbelow: (optional)
:   Only return jobs created before the given date. The format of the date is "yyyy-mm-dd", optionally extended with a time stamp in the format "hh:mm".

configId: (optional, multiple)
:   Only return jobs created from the specified configuration(s).

owner: (optional, multiple)
:   Only return jobs owned by the specified user(s).

target: (optional, multiple)
:   Only return jobs that have the specified target(s).

execState: (optional)
:   Only return jobs in the given execution state. Possible values are `all`, `completed`, `finished` and `unfinished`. If absent, `all` is implied.

Example:

`http://factory.company.com/GetJobHistory?ctabove=2008-01-01&ctbelow=2009-01-01&configId=Regression+tests&execState=completed`
:   Return the IDs of all jobs created in 2008 from the configuration "Regression tests" that ran to completion.

### GetJobInfo<a id="GetJobInfo"></a>

Exports job information in XML format.

Arguments:

jobId: (mandatory)
:   The job ID of the job to retrieve the job information from.

Example:

`http://factory.company.com/GetJobInfo?jobId=080104-1435-AF98`
:   Return all information in XML format about job "080104-1435-AF98".

### GetResourceInfo<a id="GetResourceInfo"></a>

Exports information of any resource in XML format. Currently the resource types are Task Runners and the customer defined resources. If no parameters are given all the resources will be exported.

Arguments:

type: (optional, multiple)
:   The type of resource to retrieve the information from. The resource types are defined by the customer or `"sf.tr"` which is the definition for a Task Runner.

name: (optional, multiple)
:   The name of the resource to retrieve the information from. The current implementation allows different types of resource sharing the same name. This will change in future.

Examples:

`http://factory.company.com/GetResourceInfo`
:   Return information of all resources.

`http://factory.company.com/GetResourceInfo?type=sf.tr`
:   Return information of all resources of type "sf.tr".

`http://factory.company.com/GetResourceInfo?name=myresource`
:   Return information of all different kind of resources identified by the name "myresource".

`http://factory.company.com/GetResourceInfo?type=sf.tr&name=myresource`
:   Return just the information of resource "sf.tr" with name "myresource".

`http://factory.company.com/GetResourceInfo?type=sf.tr&type=mytype`
:   Return the information of all resources "sf.tr" and custom resource typed "mytype".

### GetTagged<a id="GetTagged"></a>

Filters records using tags. The output is in XML format and consists of a set of triples: (record ID, tag key, tag value).

Arguments:

subject: (mandatory)
:   The type of record to query. Valid values are `config` (configuration), `schedule` and `taskdef` (task definitions).

key: (any number of times)
:   Match only those records that have a value for the given keys. If no keys are specified, all keys match.

value: (any number of times)
:   Match only those records that have one of the given tag values. If no values are specified, all values match.

Examples:

`http://factory.company.com/GetTagged?subject=config`
:   List all tagged configurations and their keys and values. Configurations without any tags are omitted.

`http://factory.company.com/GetTagged?subject=schedule&key=sf.trigger`
:   List all triggered schedules that have a trigger filter.

`http://factory.company.com/GetTagged?subject=taskdef&key=sf.req&value=R1&value=R2`
:   List all task definitions that apply to requirement "R1" or requirement "R2".

### GetTaskDefParams<a id="GetTaskDefParams"></a>

Requests selected parameter values from all task definitions. Output is in XML format.

Arguments:

param: (any number of times)
:   The name(s) of the task parameters to list. If no names are specified, all task parameters are listed.

Examples:

`http://factory.company.com/GetTaskDefParams`
:   Get all parameters and their values for all task definitions.

`http://factory.company.com/GetTaskDefParams?param=sf.wrapper&param=SOURCE_ROOT`
:   Get the wrapper names and the values of parameter "SOURCE_ROOT" for all task definitions.

### InspectDone<a id="InspectDone"></a>

Marks a postponed inspection as done and stores the result.

Method: **POST**

Arguments:

jobId: (mandatory)
:   The ID of the job that the inspected task is part of. See the `SF_JOB_ID` <a href="../wrappers/#variables">wrapper variable</a>.

taskName: (mandatory)
:   The name of the inspected task. See the `SF_TASK_ID` <a href="../wrappers/#variables">wrapper variable</a>

result: (mandatory)
:   The result of the inspection. Accepted values are "ok" (green), "warning" (orange) and "error" (red).

summary: (optional)
:   Human readable string describing the result in more detail. For example: "8 passed, 2 failed, 0 errors".

data._key_: (optional)
:   Any number of mid-level data key/value pairs can be stored by this API call.

Examples:

<p class="todo">This API call is now POST-only; example needs updating.</p>

`http://factory.company.com/InspectDone?jobId=080706-1234-ABCD&taskName=inspect&result=warning&summary=Some+problems&data.pass=8&data.fail=2`
:   Mark the task "inspect" in job "080706-1234-ABCD" as done. The inspection found problems, hence the result being "warning" and the summary "Some problems". Two mid-level data pairs are stored: "pass=8" and "fail=2".

### LoadExecuteDefault<a id="LoadExecuteDefault"></a>

Loads a configuration and inserts it into the job queue with all locators and parameters set to their default values.

Method: **POST**

Arguments:

config: (mandatory)
:   The name of the configuration to load.

comment: (optional)
:   Comment string that will be appended to the comment in the configuration.

prod.<i>name</i>: (optional)
:   Locator for input product <i>name</i>. For example: `prod.image=http://host/path/`. Multiple locators can be specified on a single function call, but only for inputs that actually occur in the chosen configuration.

local.<i>name</i>: (optional)
:   Task Runner which has access to local input product <i>name</i>. For example: `local.image=MyRunner01`.

param.<i>name</i>: (optional)
:   It is possible to pass any number of optional job parameters, which do not affect execution of the job, but may provide some extra features. These job parameters are mainly useful for the program processing notification mails (see below).

One optional parameter has special meaning. If `param.notify=_notification_` is specified then a notification message will be sent when the job is complete. The way the message is sent and its content are defined by the specified notification method.

Currently only e-mail notification method is supported. To use it the value of the notification parameter must have the form `mailto:_user_name@host_or_domain_name_`. The notification message has subject `Job Complete` and body of the following form:

<pre>
id: 2004-03-10_13-02_197500
param.<i>name1</i>: <i>value1</i>
param.<i>name2</i>: <i>value2</i>
...
task.1.name = <i>task1</i>
task.1.result = <i>result1</i>
task.1.state = <i>state1</i>
task.2.name = <i>task2</i>
task.2.result = <i>result2</i>
task.3.state = <i>state2</i>
...
</pre>

The parameter `param.notify` itself is not included in the message.

### ResourceControl<a id="ResourceControl"></a>

<!--
Note: Inter-factory resource sharing also used an API call named ResourceControl, but this call was never published and is not compatible with the 2.14.0 version.
-->

This call is used to suspend and resume resources. Task Runnners are considered resources too, so it is possible to suspend (pause) and resume (unpause) them with this call.

Method: **POST**

Arguments:

name: (multiple, at least one)
:   The name of the resource to operate on.

action: (mandatory)
:   The action to perform: "suspend" or "resume".

The call is considered successful if the desired end state was reached. This means that suspending an already suspended resource or resuming a resource that was not suspended is considered a successful action.

Examples:

<p class="todo">This API call is now POST-only; example needs updating.</p>

`http://factory.company.com/ResouceControl?name=toollicense&action=suspend`
:   Suspends the resource "toollicense".

`http://factory.company.com/ResouceControl?name=runner1&name=runner2&action=resume`
:   Resumes Task Runners "runner1" and "runner2".

### TaskAlert<a id="TaskAlert"></a>

This call is used to signal the start and end of a Human Intervention Point (HIP). A HIP can be used to suspend the execution of a mostly automated task until a human has performed a certain task. During a HIP, the task background is changed from blue into yellow, to indicate that the task will not make any progress until someone performs an action.

Method: **POST**

Arguments:

jobId: (mandatory)
:   The job ID of the job that contains the task to suspend. You can use the SF_JOB_ID variable for this.

taskName: (mandatory)
:   The task ID of the task to suspend. You can use the SF_TASK_ID variable for this.

alert: (mandatory)
:   Alert type or empty string. Currently, the only supported type is `attention`. An empty string clears the alert status.

To signal the end of the HIP the same API call should be made again with empty value for `alert`.

More information on the HIP can be found in the document about [semi-automatic testing](../../concepts/semiauto/#hip).

### TaskRunnerExit<a id="TaskRunnerExit"></a>

Sets a flag that will cause a specified Task Runner to exit as soon as it becomes idle. This can be useful if you want to automatically reboot Factory PCs or if you want to reload automatically generated Task Runner configuration files.

Method: **POST**

Arguments:

runnerId: (mandatory)
:   The ID of the Task Runner to set the flag for. This Task Runner has to be of version 2.12.0 or higher.

### TriggerSchedule<a id="TriggerSchedule"></a>

Sets a flag that will cause a specified triggered schedule to activate.

Method: **POST**

Arguments:

scheduleId: (mandatory)
:   The ID of the schedule to set the trigger flag for. This schedule has to be a triggered schedule.

##Call Mechanism<a id="call"></a>

This chapter describes how to make calls to the SoftFab API. It applies to all [API functions](#functions) described above. If you want to do an HTTP request (call an API function) from a wrapper script, then please [read here](#wrapper) how to do this.

### Request

To call a function on the SoftFab API, you fetch a URL from the Control Center. The base of the URL is the same as the URL of the SoftFab web interface you use, typically `http://yourcompany.com/softfab/project/`, where `project` is your project name. The function name is appended to the base URL. For example, if you want to call the `LoadExecuteDefault` function, the complete URL would be `http://yourcompany.com/softfab/project/LoadExecuteDefault`.

Arguments are usually passed as a query string that is appended to the URL. For example, to pass the parameter "config" with value "regression\_test" and the parameter "comment" with value "Started from API", the last part of the URL would be `LoadExecuteDefault?config=regression_test&comment=Started+from+API`.

Note that characters other than alphanumerics have to be encoded if they occur in URLs, as described in [RFC 1630](http://www.faqs.org/rfcs/rfc1630.html). If you are doing the call from a programming language, there is a good chance the standard language already contains a method to perform URL encoding. For example, in Java there is `java.net.URLEncoder` and in Python there is `urllib.urlencode`.

In some cases a particular API call may need a more complex input data structure than it can easily be represented by URL query arguments. In those cases the API should be called using HTTP POST request with the data structure represented in XML format and sent as the request body of `text/xml` content type or or as the value of one of the parts of `multipart/form-data` content type. The documentation of the specific API function tells you if you should do an HTTP POST and what the XML message format is.

### Response

Fetching the constructed URL from the SoftFab Control Center will return data in XML format. This is the "return value" of the function. If the function call requested data, the response body will contain the data in XML format, see the function's documentation for details. If the nature of a particular API call implies only success/failure type of response then success is indicated by the response body containing `<ok/>`.

Failure is indicated by an HTTP error code. The human-readable part of the HTTP status line contains a brief description of the nature of the failure. The following HTTP status codes are used by the SoftFab API:

400 - Bad Request
:   There is something wrong about the request. It can be a syntax error, a reference to a non-existing database record, an otherwise invalid value etc. See the human-readable part of the status line for details.

403 - Forbidden
:   The access privileges were insufficient for the action that the API function tried to perform. See the next section on authorization for a way to fix this.

500 - Internal Server Error
:   The Control Center had problems handling the request. Please, report this as a bug.

### Authorization

API calls can be performed as any user, by authenticating with that user's name and password. If no user name is provided, the API call is performed as the `api` user.

The privileges required to perform a call depend on the actions done by that call: to get information `guest` access is enough, for starting jobs `user` access is needed and for changing definitions `operator` access is required. This is consistent with the privileges required for actions done via the web interface.

By default the user `api` does not have any access rights at all. If you want to allow unauthenticated API calls in your factory, change the role of the user `api`. This can be done on the Control Center, under Configure / Users.

### Doing an HTTP Request<a id="wrapper"></a>

#### wget

When writing a wrapper as a batch file, shell script or Makefile, we recommend the command line tool [wget](http://www.gnu.org/software/wget/). This tool is easy to script and it displays the full HTTP status line, so you can see the error message if something goes wrong. A typical 'wget' command line looks like this:

```
wget -O result.xml "https://example.com/sf/GetInfo?arg=test"
```

Or if authentication is required for this API call:

```
wget -O result.xml --http-user=name --http-password=pass "https://example.com/sf/GetInfo?arg=test"
```

#### part of script language - HTTP library

In other wrapper languages, you can use the respective standard library to do HTTP requests.
Read [this perl article](https://metacpan.org/pod/HTTP::Request) about HTTP requests in perl, or [this python article](https://docs.python.org/2/library/httplib.html) about HTTP requests in the python script language.

<!--
TODO: Example code for one or more supported wrapper languages: HTTP get and XML processing.
-->
