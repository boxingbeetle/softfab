# Continuous Integration

In a Continuous Integration (CI) development process, as used in Agile and DevOps environments, the build and tests are kicked off when new commits are added to a version control repository. To do so the version control system should trigger a SoftFab schedule which fires, in its turn, a specified configuration.

<p class="todo">
TODO: Update and re-test the example scripts for SoftFab 3.0+.<br/>
</p>

Introduction
-----------

In a typical project, a group of developers writes code and pushes commits to a central repository. Because developers are only human, they make mistakes, so it is a good idea to regularly build and test the current state of the code base. A popular way to do this is a daily build, but why wait until the end of the day if you can do the check immediately after commits are pushed? This document describes how to configure SoftFab and your version control system to make that possible.

Having a push-triggered build and test is very useful if you are using a [Continuous Integration](http://martinfowler.com/articles/continuousIntegration.html) process. But if you are using a process based on one or more promotion levels it is also useful to have a push-triggered build and test, since it allows you to automatically reject commits for promotion that break the build or test. If you have sufficient confidence in your test suite, you can even automatically promote commits that pass the tests.

Preparation in SoftFab
---------------------

First, create a configuration that implements the build and test. Typically the first task will update or export the latest code from the version control system. This is followed by a build and one or more quick tests. It is important that the entire build and test cycle stays short, so it can be run many times per day. Tests that take a long time can better be scheduled to run overnight or you can add more Task Runners on more hardware to execute build and test tasks in parallel.

Now create a triggered schedule that starts the configuration you prepared. A triggered schedule sits waiting for a SoftFab API call to trigger it. When triggered, it kicks off the associated configuration(s). When the created jobs are finished, it waits for the next trigger. If a trigger is received while the previous jobs are still running, the configuration(s) will be instantiated again as soon as the jobs finish. This avoids flooding the queue when many triggers occur.

Triggering a Schedule<a id="webhook"></a>
--------------------

When new commits are pushed to your repository, some mechanism needs to notify the Control Center of that event. SoftFab currently offers the following mechanisms:

- [GitHub webhook](#webhook_github)
- [Gogs webhook](#webhook_gogs)
- [implementing a new webhook](#webhook_new)
- [notification by API call](#apitrigger)

### GitHub webhook<a id="webhook_github"></a>

On your GitHub project page, select Settings, then Webhooks and click the "Add webhook" button.

As the payload URL, enter:

<pre><?ccURL?>webhook/github</pre>

Set "Content type" to `application/json`.

For the secret, generate a random string of sufficient length and paste that same string both in the form at GitHub and in the repository configuration here in your Control Center.

The rest of the settings you can leave on their default values.

Submit the form and then click on the webhook's payload URL to check whether GitHub's ping is listed as a success under "Recent Deliveries".

### Gogs webhook<a id="webhook_gogs"></a>

On the Gogs web interface, select Settings, then Webhooks and add a new webhook of the type "Gogs".

As the payload URL, enter:

<pre><?ccURL?>webhook/gogs</pre>

Set "Content type" to `application/json`.

For the secret, generate a random string of sufficient length and paste that same string both in the form at Gogs and in the repository configuration here in your Control Center.

The rest of the settings you can leave on their default values.

Submit the form and then click on the webhook's payload URL and scroll down to "Recent Deliveries". Press the "Test Delivery" button to check whether Gogs's ping is received correctly by your Control Center.

### Implementing a new webhook<a id="webhook_new"></a>

If you're a Python developer who is not too shy to modify the tools you're using, you can add your own webhook implementation in `src/softfab/webhooks/`. New submodules added there are automatically picked up when the Control Center starts. If your webhook is implemented in `foo.py`, it will be called when `POST` requests are made to the following URL:

<pre><?ccURL?>webhook/foo</pre>

Note that we give no backwards compatibility guarantees for SoftFab's intertal interfaces at this point in time, so if you want to make sure your webhook will work with future SoftFab releases, the best strategy is to send us a [pull request](https://github.com/boxingbeetle/softfab/pulls) to integrate it into SoftFab itself.

### Notification by API call<a id="apitrigger"></a>

You can trigger a schedule using the [TriggerSchedule](../../reference/api/#TriggerSchedule) API call. This means you request the following URL:

<pre><?ccURL?>TriggerSchedule?scheduleId=NameOfTriggeredSchedule</pre>

This API call should be made when relevant commits are pushed to your repositories. Most version control systems have hooks that allow scripts to run on various events, including when commits are pushed.

If your project uses multiple integration streams, for example a main development branch and a bug fix branch, it is useful to have a separate schedule for testing each of them. You can use a naming convention to automatically trigger the right schedule to test the committed code.

The user making the API call must have permission to modify the schedule. This means the user must either be the owner of the schedule or have operator privileges. We recommend creating a functional user account for both editing and triggering the push-triggered schedules.
