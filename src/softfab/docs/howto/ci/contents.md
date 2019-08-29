# Continuous Integration

In a Continuous Integration (CI) development process, as used in Agile and DevOps environments, the build and tests are kicked off on a change in the Configuration Management (CM) system. To do so the CM system should trigger a SoftFab schedule which fires, in its turn, a specified configuration.

<p class="todo">
TODO: Update and re-test the example scripts for SoftFab 3.0+.<br/>
</p>

Introduction
-----------

In a typical project, a group of developers writes code and commits it in a configuration management (CM) system. Because developers are only human, they make mistakes, so it is a good idea to regularly build and test the current state of the code base. A popular way to do this is a daily build, but why wait until the end of the day if you can do the check immediately after a commit? This document describes how to configure SoftFab and your CM system to make that possible.

Having a CM-triggered build and test is very useful if you are using a [Continuous Integration](http://martinfowler.com/articles/continuousIntegration.html) process. But if you are using a process based on one or more promotion levels it is also useful to have a CM-triggered build and test, since it allows you to automatically reject commits for promotion that break the build or test. If you have sufficient confidence in your test suite, you can even automatically promote commits that pass the tests.

Preparation in SoftFab
---------------------

First, create a configuration that implements the build and test. Typically the first task will update or export the latest code from the CM system. This is followed by a build and one or more quick tests. It is important that the entire build and test cycle stays short, so it can be run many times per day. Tests that take a long time can better be scheduled to run overnight or you can add more Task Runners on more hardware to execute build and test tasks in parallel.

Now create a triggered schedule that starts the configuration you prepared. A triggered schedule sits waiting for a SoftFab API call to trigger it. When triggered, it kicks off the associated configuration(s). When the created jobs are finished, it waits for the next trigger. If a trigger is received while the previous jobs are still running, the configuration(s) will be instantiated again as soon as the jobs finish. This avoids flooding the queue when many triggers occur.

Triggering a Schedule
--------------------

You can trigger a schedule using the [TriggerSchedule](../../reference/api/#TriggerSchedule) API call. This means you request the following URL:

```
https://example.com/sf/TriggerSchedule?scheduleId=NameOfTriggeredSchedule
```

This API call should be made when relevant commits are made in your CM system. How this works is described in the documentation of your CM system.

If your project uses multiple integration streams, for example a main development branch and a bug fix branch, it is useful to have a separate schedule for testing each of them. You can use a naming convention to automatically trigger the right schedule to test the committed code.

The user making the API call must have permission to modify the schedule. This means the user must either be the owner of the schedule or have operator privileges. We recommend creating a functional user account for both editing and triggering the CM-triggered schedules.
