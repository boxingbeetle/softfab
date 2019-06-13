# Roadmap

This document contains an overview of features that are considered for implementation in SoftFab in the future. The SoftFab development team can use this to base a planning on. The SoftFab customers can use this to see if their wishes are already being taken into account by the developers.

<p class="todo">TODO: "Timeout for Task Runs" is implemented?</p>

Scheduling
---------

### Task Starvation Prevention

It is possible that tasks which require a combination of resources will not be dispatched, because individual resources are always in use by tasks which have simpler resource requirements. The scheduler could be modified to detect task starvation and take action, for example reserving one resource for the starved task until the other required resources are available as well.

Note that task starvation is not a problem if tasks have simple resource requirements (at most one resource) or if there is sufficient time in which the job queue is empty. We haven't seen task starvation occur in existing SoftFabs yet, but it could occur if usage patterns change.

There could also be a situation in which a task is impossible to dispatch, because the required resources or capabilities are simply not available in the SoftFab at that moment. This has been solved by the "reason for waiting" feature: when a task cannot be scheduled, the summary field displays the reason why.

### Multiple Instances of a Local Product

Currently there can only be one instance of a local product per job. It would be useful to have the ability to have multiple instances. For example, a certain project uses one Task Runner on Windows and one on Linux within the same job. Currently, they have to define two different products for the source tree on Windows and on Linux even though it is the same source tree on different locations.

Robustness
---------

### Timeout for Task Runs

A test run on a Factory PC could wind up in a situation where it is not making any progress. It would be useful to detect this and abort the test, so the Factory PC will be available to run other tests. One way to detect such situations is having a timeout. If a timeout occurs, the task will be aborted.

The timeout value could be given in the task definition, or calculated based on previous executions of the same task. The latter depends on [Estimated Time of Arrival](#eta).

### Failure Alerts

If a critical failure occur in the SoftFab, send an alert the user and/or operator. This requires the following items to be implemented:

*   detecting failures
*   decide whether a failure is critical enough to raise an alert
*   decide who to alert (user and/or operator)
*   sending the alert by a [SoftFab Message](#sfmsg)

### Report Navigation HTML

Right now, the Task Runner writes static HTML files for the report navigation structure. This has some problems:

*   If the Control Center URL changes, links break.
*   The style sheet is on the Control Center as well, so incompatible upgrades to the style sheet will break old reports.
*   When we will be cleaning up reports: the links to no longer existing reports will have to be removed.

So perhaps we should generate the navigation HTML files dynamically, on the Control Center. Although it's slightly more complex, it gives us a lot more flexibility.

Resources
--------

### Automated Resource Registration

The Task Runner software that runs on Factory PCs contacts the Control Center and automatically registers itself. It is possible to do this for other resources as well, for example streamer PCs. The resource would also tell the Control Center about its capabilities. Note this is not possible for all resources, for example a software license is an abstract resource, which is not capable of communicating.

The Control Center web interface should provide an overview of the available resources and their status (cockpit). This could be an extension of the Task Runners status page.

Note that only PC-like resources can register themselves. The only type of resource used by our current customers is a software license, which is completely passive. So implementing automated resource registration has a low priority right now.

Reporting
--------

### Query on CM Tags

A typical question that users have, is to see all tests performed on a certain baseline / release. To enable this, it should be possible to associate jobs with a certain CM tag and to query by those tags. Source and image locators have a relation to CM tags, probably they can be used in some way.

### Saving of Queries

When it is possible to make complex queries, it becomes useful to save them for later use.

Note that it is already possible to bookmark a query. However, this is not obvious to most users. Also it only works if you always access the Control Center from the same PC; it would be better to associate the saved queries with a SoftFab account. Also it would be nice to be able to share queries with other users.

### Central Report Storage

Currently reports are stored on Factory PCs, but those may not always be available and are usually not backed up. Storing build and test reports in a central database would solve this. However, for some projects the size of reports is too large for a central database to be useful. Probably it's a good idea to only store parts of the reports in the central database, for example for a build the list of warnings and errors would be stored, but the source code and object files would not.

### Linking to Issue Tracking System

When a test fails, there will probably be a related PR in an issue tracking system. If the tracking system has a web interface (most do nowadays), it would be useful to link from the report in SoftFab to the PR in the issue tracking system.

A similar linking mechanism could be made for other external tools with web interfaces, for example a requirements management system.

A very simple implementation would be to allow hyperlinks to be appended to an existing report, without any knowledge of the semantics in the SoftFab. This could be expanded to a kind of bulletin board system, where SoftFab users can add comments to a report.

In a more advanced integration the SoftFab could add entries to a PR with a summary of the test results and a link to the report. Maybe SoftFab could even automatically open PRs if a regression test fails. Whether this is desirable depends on the way of working of a project of course.

### Dashboard<a id="dashboard"></a>

It would be nice to have a single page which gives an overview of a project's status.

We have similar things like this already, but none of them provide exactly the dashboard functionality:

*   Home page: this shows what is going on in terms of process, but does not show the state well.
*   Task Matrix: this shows the state reasonably well, but its format does not work well for all projects. For example, it is week based and its layout favors many executions of the same tasks.
*   GetTaggedTaskInfo: this exports information about the latest executions of tasks, allowing an external application (as is being written in the Merlin tool chain subproject) to create a kind of dashboard. But it would be nice to use this information in the Control Center web interface as well.

Tools which are somewhat similar to SoftFab often have a dashboard:

*   Tinderbox, follow one of the links in the "Mozilla.org usage of tinderbox" section to see it in action.
*   [Dart](http://public.kitware.com/Dart/), select "Examples" to see a dashboard.

Actually the Dart and Tinderbox dashboards are a like a cross between our home page and the task matrix, meaning they show the most recent events, rather than the current state. So they are not exactly what I mean with "dashboard", but they could inspire us nevertheless.

#### User definable monitors

In this idea we can have multiple system of user defined dashboards with some monitors placed on it. These monitors collect the data via the SoftFab API. Monitors can be user made, provided by SoftFab or can be third party plug-ins all having their own looks.

### Report Differences Between Two Runs of the Same Task

In some cases, users are more interested in changes in problems found in tests, rather than the full list of problems. For example, when working on passing a conformance test suite, regressions require more immediate attention than tests that have never passed before. In the case of static code checks, some problems are false positives, which should be ignored and if the frameworks cannot handle that, maybe SoftFab could.

We could make an easy way to see the differences in mid-level data between two runs. The advantage of this is that it automatically works for every framework for which the user has written an extractor. The disadvantage is that in some cases framework specific knowledge may be required to make a useful comparison. For example, not only the number of failing conformance tests is important, but also which tests: if one test that used to fail now passes and one test that used to pass now fails, the net total is zero, but it is an important change.

This feature could be integrated with the [dashboard](#dashboard) idea, by showing not just the latest executions, but also the delta compared to the previous one.

Another approach would be to pass a locator to information from the previous run to the wrapper. It could be the URL of the report. Or it could be an output product from the previous run which is used as an input by the current run, this takes a bit more effort, but allows you to preserve TR binding by using a local product and allows you to use any kind of locator and access protocol, not just URLs fetched by HTTP.

Both approaches complement each other: using mid-level data is a good solution if no framework specific information is needed, while passing report locators is a good solution if a framework specific comparator has to be written.

Metrics
------

### Collect Metrics

It is not possible to process metrics that were not collected. So we could store potentially useful information in our database, only to process it at a later point in time. However, we should be careful not to start collecting metrics at random, but only those for which a scenario exists in which they are useful. See also [dashboard](#dashboard).

### Estimated Time of Arrival (ETA)<a id="eta"></a>

Store the start and end time of each task run in the database. Use this to calculate the average running time of a task. This value can be used to predict the end time of a running task, or even the end time of a job.

### Display Project Metrics (Factory Usage)

Display metrics like the number of jobs/tasks run and how this number changes over time, how often each task is run etc.  See also [dashboard](#dashboard).

Communication
------------

This section lists features that allow SoftFab to function as a "communication tool" within a project.

### Yellow Notes

Allow users to leave notes on a Control Center page, which other users will see when they view the page.

Examples: a note explaining why a certain resource is not available, a note explaining some configuration changes.

The mechanism for leaving notes could be made such that every page supports notes. So instead of us deciding which pages will have notes and which will not, it is up to the user to decide on which page to leave a note.

It is probably useful to allow hyperlinks to be placed in notes. What format should we use for this? Forum tags like \[url\] or just automatically linking everything starting with "http://"?

### Adding Comments to a Job

Make a way to add comments to a job, for example to document the reason its execution failed.

A simple way would be to make the user-specified comment editable.

Is this still needed as a separate feature if we have the Yellow Notes feature?

### Project Specific Documentation

Create a place on the Control Center where the project can put hyperlinks to their documentation. The documentation itself is managed outside SoftFab.

Maybe it's nice to also put links to the latest JavaDoc/Doxygen/Epydoc run in the same place (using LatestReport redirection page).

Miscellaneous
------------

### SoftFab Message<a id="sfmsg"></a>

A SoftFab Message is a message with timing and process information and some additional job dependent information that is sent to a specified (list of) addressee(s) by yet to choose system(s) or protocol(s) (e.g. email, SMS, pager, Sametime, ...).

### Rerun Task/Job

If a task execution hits an occasional error, it would be useful to rerun the task in the hope it will complete the next time. Such occasional errors could be caused by problems such as loose cables, power failure or software crashes.

For example, when recovering from the situation where a Task Runner was aborted, it would be useful to automatically add another run of the same task. Then another Factory PC can execute it, or the same Factory PC after it has recovered (for example when it comes back up after a power failure).

A possible UI feature: add a rerun button next to each task/job in the report view. However, it is not clear whether this is desirable, since finished jobs could become "in progress" again, which may be confusing to the user. Maybe rerunning aborted tasks or tasks with errors should be allowed, but rerunning succesfull tasks should not? An alternative would be to implement user-requested reruns by creating a new job which uses the same settings (locators, parameters) as the original job.

Allowing more than one run of a task requires some changes in the job database and in the communication protocol between Control Center and Task Runner.

When multiple runs of the same task are possible, it would be possible to implement the current "execute N times" feature by creating N runs within a single job, instead of creating N jobs. This would make it easier to get an overview of the results.

### Clean Up Old Reports and Products on Factory PCs

Currently old reports are stored on Factory PCs forever. However, since disk space is limited and some frameworks produce rather large reports, it is possible for a Factory PC to run out of disk space. An automated process could be made which cleans up old reports when they are no longer useful.

In addition to reports, cleaning up old products is required as well. Especially source trees can get very large for some projects.
