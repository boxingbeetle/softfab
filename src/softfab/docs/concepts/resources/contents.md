# Resources

Hardware and services that are used to execute tasks are modeled as resources.

SoftFab executes tasks using your existing infrastructure, such as computers and repositories. Some tasks may need to connect to services that are permanently running because they're not suitable to be instanced for each run, like heavy databases or external web services. If you are doing embedded development, you may want to run tests on prototype hardware that is limited in supply.

This external infrastructure is modeled using *resources*. By telling SoftFab about your infrastructure, the Control Center can assign the right combination of resources to execute each task.

## Resource Types

SoftFab supports the following classes of resources:

- [Task Runner](#runner)
- [repository](#repo)
- [user-defined resource types](#custom)

### Task Runner<a id="runner"></a>

The Task Runner is the execution agent of SoftFab: it is responsible for starting the processes that execute tasks such as builds and tests. It runs on a [Factory PC](../../start/factory_pc_installation/).

A Task Runner periodically synchronizes its status with the Control Center. This sync is the moment an idle Task Runner can be assigned a new task, or a working Task Runner can be told to abort the task it is currently running. If expected syncs are not coming in for an extended period of time, the Control Center will declare a Task Runner *lost* and any task it was running will fail with the `error` status code (red).

### Repository<a id="repo"></a>

Version control repositories that contain source code, test data, art assets, documentation and other content are also modeled as resources. Since the model is very abstract, it should work with any version control tool.

Schedules can be triggered when a repository receives relevant new content, such as a push to a particular branch in a Git repository. This can be used to set up a [Continuous Integration](../../howto/ci/) loop.

<p class="todo">Link to schedules and webhook docs, once those actually exist.</p>

### User-defined Resources<a id="custom"></a>

Resources that are specific to your project can be modeled using a user-defined resource type. Custom resources are defined in two steps:

- add a resource type in your [factory design](../../../ResTypeIndex)
- add one or more instances of the resource type on the [Resources page](../../../ResourceIndex)

It can be worth modeling a piece of hardware or a service as a resource if it has one or more of the following properties:

- it cannot be used simultaneously by multiple jobs or tasks
- it can be temporarily unavailable and tasks that require it should be delayed until it is available again
- there is a piece of configuration related to it, for example a URL, that you do want to be able to update with a single action

Examples of custom resource types:

- embedded hardware on which you want to run tests
- hardware or a service that has to be shared between automated and manual testing
- a work-in-progress service that is not always available for testing
- a database server that is always running, but has its data modified as part of the test
- a software license that restricts the number of concurrent executions of a particular tool

## Exclusivity<a id="exclusive"></a>

Some types of resource cannot be used concurrently, or only by related tasks. For example, an embedded device cannot simultaneously run two different firmware images and two tests modifying the same tables in a database could interfere which each other's results. Such restrictions can be modeled in SoftFab by defining the resource type to be exclusive.

### Per-task Exclusive

A resource type can be defined to be exclusive per task. This means that when a task definition requests a resource of that type, the resource is reserved for that task and only becomes available again for other tasks when the first task has finished.

Per-task exclusively is useful when a resource's state is changed as part of a task, but nothing is assumed about its state afterwards.

### Per-job Exclusive

It is also possible to define a resource to be exclusive per job. Such resources are reserved when the first task that requires them in a job starts and freed when the last task that requires them in a job has finished.

Per-job exclusively is useful when the first task prepares a particular resource state for the other tasks to use. For example, if you have made a piece of software that can only be installed on a test machine in a fixed location, you could have the first task install a particular build of your software and later tasks can each launch a separate instance to perform system tests on it.

It is possible for a resource type to be both per-job and per-task exclusive. This means that it can only be used by one task at a time and will remain reserved until all tasks in a job are done with it.

### Non-exclusive

A resource that is neither per-task nor per-job exclusive is called *non-exclusive*. Such a resource can be accessed simultaneously by any number of tasks from any job.

There are practical reasons why you might want to model something as a non-exclusive resource:

If a service is temporarily offline, you can [suspend](#suspend) its resource and tasks that require it will be delayed until the resource is resumed. If it were not modeled as a resource, it would be impossible to tell SoftFab that the service is offline and tasks that need it would run and fail with an `error` status (red) instead.

If a service might move every now and then, you can set its current location (for example, URL or <code>*host*:*port*</code> string) in the *locator* property, such that you only have to edit a single definition to update your entire factory.

### Exclusivity of Predefined Resource Types

Task Runner: per-task exclusive
:   A Task Runner can run a single task at a time.

Repository: non-exclusive
:   A repository can be simultaneously accessed by multiple tasks from multiple jobs.

## Capabilities<a id="capabilities"></a>

Not all resources of the same type may be suitable for executing all tasks:

- some tasks require special tooling to run, which is not installed on all Factory PCs
- to build an application, a task will need to get its source code from the application's repository; the web site repository will not work
- a feature might only be possible on revision 2+ of your embedded device, so a test for that feature cannot run on revision 1, but most tests can run on either revision

Such restrictions can be modeled using *capabilities:* per-resource properties to differentiate between resources of the same type. Capabilities affect resource assignment in the following way:

- a resource offers capabilities
- a task definition requires capabilities
- a resource that offers **all** of the required capabilities is reserved for a task
- the reserved resource may offer more capabilities than required, but resources with fewer capabilities are assigned first

### Targets<a id="targets"></a>

A *target* is a special kind of capability which is typically used to model platforms such as operating systems, where similar jobs will be run on all supported platforms.

Available targets are defined in the [Project Configuration](../../../ProjectEdit). A new job either has no target or one target from the configured list. A job with a target requires that target as a Task Runner capability. So for example a job with target `linux` can only run on a Task Runner with capability `linux`. A job with no target has no such requirement and can therefore run on any Task Runner.

## Suspending Resources<a id="suspend"></a>

If a resource is temporarily not available, it can be *suspended*. This means that it will not be reserved for new task runs until it is *resumed*. If a resource is in use at the time it is suspended, the task using it is allowed to finish.

Suspending a resource is useful when for example:

- a service has to be taken offline for maintenance or an upgrade
- a piece of hardware or software is suspected to be malfunctioning and needs to be examined and possibly repaired
- a piece of hardware or software is required for manual testing
