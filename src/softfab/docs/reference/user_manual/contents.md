# User Manual

This document contains a global manual for SoftFab users. SoftFab users typically execute jobs (tasks) and view the results. They will probably also create configurations for jobs they frequently run and perhaps schedules to automatically start jobs.

Note that this manual is not going into too much detail since the UI may vary a little from release to release. But this global explanation is enough to get started. Most details are more or less self-explanatory.

<p class="todo">
TODO: Replace the old resource png in the resources section header by the windmill.<br>
TODO: The explanation of the Task Runner resource status table should be replaced and relocated by one covering other resources too.<br>
</p>

##SoftFab Web GUI

Every page has a title bar, a navigation bar and the main content.

### Title bar

All titles are starting with your project name followed by 'SoftFab'. The second part is the name of the page.

 At the right hand side you see time and date information, who is logged in, a way to log out and the SoftFab logo.

Clicking:
* the logo takes you to the 'About' page. Here you will find a link to the documentation pages.
* your user name shows you the user details page where you can change your password or see an overview of jobs and tasks that you created.

### Navigation bar

This bar shows where you are in the page tree of the Control Center. The current page is highlighted in blue. To the left of the current page are the parent pages of the current page, all the way up to the home page. To the right of the current page are the child pages of the current page (if any).

If the browser page gets very narrow the logo and button text may disappear.

### Main content
This is the part where you can make your actions or read the information from.

## Home ![Home](/styles/SoftFabLogoMono1.png)

The "Home" page is the default SoftFab page. From here you have access to all functionalities and locations. A table occupies the largest part where you can see the most recent 'jobs' that have run in the SoftFab. A 'job' is represented by a row in the table and its status is represented by a color.

More about jobs in the section titled [History](#history).

## Configure ![Configure](/styles/Configure.png)<a id=configure></a>

This is the starting point where you have to define the project settings, create or extend the design of the SoftFab project by building an executation graph including frameworks and products and where you can create new task definitions and resources.

### Project ![Project](/styles/Project1.png)

In the project page operators can change project wide settings.

**Project name**: enter a name for your project.

**Targets**: the default is 'unknown'. New targets can be added here (space separated). A Task Runner is used only if it contains a matching target. See the content of the Task Runner's config.xml, line: `<sut target="unknown"/>`. If two or more targets are defined, then a target has to be chosen for a job configuration to be executed. As a result the tasks in a job will run only on Task Runners with a matching target. For example: it can be useful if you have several different platforms to build/test on (e.g. Windows Mobile, embedded Linux, Symbian). It is possible to execute a certain job on e.g. Windows PC's only by adding the target 'windows'. Make sure the Task Runner's config.xml file on all Windows PC's contains the matching target="windows".

**Project time zone**: Enter the time zone of the projects home location. For multi-site projects, choose what time zone will be used in the project. The times shown on the SoftFab web pages are displayed according to the Project time zone.

**Multiple jobs limit**: Enter the maximum number of jobs that can be executed at once from a single configuration. The default value is 25. It is possible to start more than one job from one configuration at once (Click on 'Load', next enter the number of executions to start). This can be useful to reproduce a bug that does not occur every run, e.g. because it is a timing issue (non-deterministic bug). Running many tests on as much Task Runners as possible may show the problem, or simply by running a same test on all available Task Runners to test robustness. Each PC or System under Test may have different specifications and a potential problem can be found quicker. SoftFab takes care of the proper distribution and puts the jobs in a queue if required. A maximum jobs limit is required to protect too many jobs to be started accidentally.

**Task priorities**: It is possible to give tasks within a configuration a certain priority, e.g. for some test tasks you want the results asap. When this option is enabled, setting priorities to tasks can be done when creating a new configuration (execute from scratch) or when you first load an existing configuration. It is no guarantee that tasks with a higher priority will be carried out first, because other settings (e.g. design of the execution graph) have to be satisfied before dealing with priorities. Only for tasks with equal settings, priorities can be used. A task with the lowest priority number will be executed first. The priority number must be an integer and may be negative. By default, task priorities are disabled.

**Task Runner selection**: It is possible to bind a job (with tasks) to one specific Task Runner. It can be used to troubleshoot a problem that only occurs on a specific Task Runner and to force a job to run on the chosen Task Runner. It is not intended to replace capabilities (see Task Definitions). To select a Task Runner has to be done when creating a new configuration (execute from scratch) or when you first load an existing configuration. By default, Task Runner selection is disabled.

**Requirement tracing**: By default it is disabled. When enabled it will give an extra edit line in the Task Definition Edit Form called: requirements. Here you can fill in requirement ID's (e.g. ID's from a requirements database tool such as 'Doors'.) Later it is possible to retrieve an overview of all ID's and to see in what Task Definitions they are used. This way it can be possible to determine if all requirements where tested in the project. At the moment this feature is in an early stage of development. No real linking with a requirement database tool has been implemented. ID's have to be set manually. An API call is available to retrieve the Requirement ID's, see [GetTagged API call](../api/#GetTagged).

**Configuration tags**: These can be created to split the total list of configurations into two or more groups by tagging each configuration. Each group is tagged with an unique key. Specify the tag keys here (use strings) and in the Execute page you can click on a tag key and add configuration to a specific tag key. This improves the viewing and finding of a configuration in the total list of configurations. It is mostly used in projects with many configurations. By default, configuration tags are disabled.

### Design ![Design](/styles/Graph.png)

Here you can create or extend the design of the SoftFab project by building an execution graph. The execution graph must contain at least one framework. If more than one framework is defined, these can be connected by products. The execution graph gives you a visual overview of all the different frameworks and what the order of these frameworks are, when executed. Try to split up an automatic job into several parts (frameworks), e.g.: prepare\_code, static\_code\_check, build, unit\_tests, coverage\_tests or report\_generation tasks.
Hint: always try to automate as much as possible (e.g. creation of install packages, archiving or clean-up actions, create CM baseline, generate documentation, etc.).

Read more about the concept of execution graphs in [this document](/introduction/execution_graph/).

To be able to create and run a new job configuration you must have or create at least the following items: one framework, a wrapper script for the framework (to execute your task) and one task definition (using the framework). Learn more about framework and task definitions in [this document](/introduction/framework_and_task_definitions/).

### Users ![Users](/styles/UserList1.png)

On this page you can see all the SoftFab users for this factory. You can add a new user, change password(s) and change the user roles (inactive, guest, user or operator). It is not possible to delete a user. Set the user role to inactive this such case (this is done for traceability; the job history of all users are kept).

## Execute ![Execute](/styles/ExecConf2.png)<a id=execute></a>

From this page you are able to start remotely one or more builds, one or more tests or any other type of task an operator has integrated into the SoftFab tool. A 'task' in SoftFab terminology is the smallest unit of execution. A task runs on exactly one (available) Task Runner. It is possible that the tasks of a multi task job configuration run on many different, possibly globally distributed, Task Runners in parallel. In this way a job can complete in shorter time.

You can execute a job (tasks) in two different ways:

*   Execute From Scratch.
*   Execute (if table contains Job configurations)

The latter one means that somebody in the past already has walked the 'Execute From Scratch' path and he/she has saved the execution settings for that particular configuration. Loading this Job configuration and executing it, has the same effect as doing it via 'Execute From Scratch' but it takes fewer steps.

A Job configuration is represented by a row in the table.

### Execute From Scratch ![Execute from Scratch](/styles/ExecScra1.png)

This part of the GUI is a succession of pages, all equipped with 'back' and 'next' buttons. On each page you have to make some choices and proceed via the 'next' button.

If two or more 'targets' are integrated within the SoftFab of your project, you have to choose for what target you want to execute.

Select one or more tasks to execute. Ask your operator what these tasks mean and what they do.
If 'priorities' are activated, fill in integer values for each task. The lower the value, the higher priority the task will get during execution of the job.

According to the task(s) you have chosen, it could be possible that some inputs are required. The SoftFab needs to know these inputs in order to execute.
Note that tasks may also have outputs. Some outputs may be inputs for other tasks. In case a task requires an input, which is provided by another task (it's output), the SoftFab automatically makes the connection and the user will not be asked to fill in the input. These tasks will be processed sequentially.

On the same page it is possible that you have to fill in so called 'parameters'. Parameters are bound to a certain task. They may have a default value.

On the latest 'Execute' page you have the possibility to either execute or save the configuration. If you have chosen to execute the configuration, a confirmation will be displayed and a new 'job' is placed in the queue. To view the status of this job, see Home or History. Saving the configuration means that it becomes part of the table on the initial Execute page, it can be executed later.

On the same page there is a field where you can fill in your email address. You will receive an automated email on this address when the job is finished. If you select "On failure only" you will only receive an email in case the finished job has tasks with result: not OK (not green). You may enter a by comma separated list of addresses.

## History ![History](/styles/Reports1.png)<a id=history></a>

On this page a table is visible with all jobs ever executed, currently executing or waiting for execution. Sorting and filtering this table is possible by making use of the filter box (on top of the page) and by clicking on the sorting links.

A job is a collection of one or more tasks. It is an instance of a configuration as described in the Execute part. This is the bunch of work you want SoftFab to process automatically.
Jobs and tasks have a status (which may vary during it's lifetime), represented by a color. The status of a job is the same as the status with the highest priority of the underlying tasks. Once the status is not 'attention', 'busy' or 'waiting' anymore, it becomes fixed and it won't vary anymore.

<table>
	<tr>
		<th>
			Color:
		</th>
		<th>
			Status:
		</th>
		<th>
			Priority:
		</th>
		<th>
			Fixed:
		</th>
		<th>
			Description:
		</th>
	</tr>
	<tr class="attention">
		<td class="bright">
			yellow
		</td>
		<td class="bright">
			attention
		</td>
		<td class="bright">
			1
		</td>
		<td class="bright">
			no
		</td>
		<td class="bright">
			Human intervention is needed for the task/job.
		</td>
	</tr>
	<tr class="busy">
		<td class="bright">
			blue
		</td>
		<td class="bright">
			busy
		</td>
		<td class="bright">
			2
		</td>
		<td class="bright">
			no
		</td>
		<td class="bright">
			SoftFab is currently executing the task/job.
		</td>
	</tr>
	<tr>
		<td>
			white
		</td>
		<td>
			waiting
		</td>
		<td>
			3
		</td>
		<td>
			no
		</td>
		<td>
			The task/job is waiting for execution.
		</td>
	</tr>
	<tr class="error">
		<td class="bright">
			red
		</td>
		<td class="bright">
			error
		</td>
		<td class="bright">
			4
		</td>
		<td class="bright">
			yes
		</td>
		<td class="bright">
			SoftFab was not able to finish the task/job.
		</td>
	</tr>
	<tr class="warning">
		<td class="bright">
			orange
		</td>
		<td class="bright">
			warning
		</td>
		<td class="bright">
			5
		</td>
		<td class="bright">
			yes
		</td>
		<td class="bright">
			SoftFab has finished the job/task but the process
			SoftFab was running has produced some errors/warnings.
		</td>
	</tr>
	<tr class="ok">
		<td class="bright">
			green
		</td>
		<td class="bright">
			ok
		</td>
		<td class="bright">
			6
		</td>
		<td class="bright">
			yes
		</td>
		<td class="bright">
			SoftFab has finished the job/task and the process
			SoftFab was running didn't produce any error/warning.
		</td>
	</tr>
	<tr class="canceled">
		<td class="bright">
			gray
		</td>
		<td class="bright">
			canceled
		</td>
		<td class="bright">
			6
		</td>
		<td class="bright">
			yes
		</td>
		<td class="bright">
			A SoftFab user has aborted the task, which was
			still in 'waiting' status. Or SoftFab has aborted the
			task because it's dependencies will not be available.
		</td>
	</tr>
</table>

Click on the description of a job to see all underlying tasks. Click on the summary of a task to see its output and corresponding logs.

A zip file with all results, all logs and some extra navigation `.html` files can be downloaded if 'Export' is clicked.

## Task History ![Task History](/styles/Reports2.png)

This is another representation of the history of tasks that have been run. Unless the main History page, the tasks are displayed independent from the jobs they were in. This makes it easier to compare results between different runs of the same task. Multiple tasks can be selected.

## Task Matrix ![Task Matrix](/styles/TaskMatrix1.png)

Task Matrix is again another new way of displaying which tasks have run and their results. After you select a week, you will be presented with a matrix of all tasks and on which days of the selected week they were run. Tasks, which were not run but are configured in your SoftFab are also shown.

Filtering on (Job) configuration means: show only tasks that occur in this/these particular configuration(s).

## Resources![Resources](/styles/Resources1.png)<a id=resources></a>

In this section all resources instances, ordered by their type, and their status are presented.

Two types of resources do exist:
* User defined resource types.
* The predefined [Task Runner](#runner) resource type.

### User defined resources

User defined resources are visible only if they are created and configured (in Configure - Design - Resources) by a SoftFab operator. To do this, the SoftFab operator must first create a new resource type (e.g. tool, workspace, encoder, device, etc.), and next create a new resource.

Sometimes a task makes use of extra resources (e.g. special/unique equipment, use the same workspace or a tool with an expensive license/user). In case these resources are scarce it is likely that a project wants to share these among all test units that needs it. SoftFab is equipped with an automated reserve mechanism that controls the distribution of scarce resources among all tasks. In the Task Definition, it is possible to reserve a resource exclusively. After the task has finished the resource is released and another task (or user) can use this resource. By using resources in SoftFab, the costs of licensed tools can be reduced or expensive equipment can be used more optimal.

But it can also happen that for some reason (e.g. a special ad-hoc test) a user (not a task) wants to use a resource for him-/herself. To prevent SoftFab assigning a resource to another task at the same time, the user can reserve the resource on the Resources page by hand. He/she can release the resource after he/she has finished and SoftFab is able to use the resource again for next tasks. Always consult your SoftFab operator before reserving a resource in person.

Via this resource reserving mechanism it is even possible to share resources between different projects. Examples are expensive tools with a high license fee per user (e.g. MatLab, QAC, etc.) or special expensive professional equipment shared among tasks or even projects.

The projects SoftFab operator controls the configuration of the Resources.

### Task Runners<a id=runner></a>

The Task Runner is the part of the SoftFab, which is installed in the field, typically on a Factory PC. This OS independent piece of software (Java) has the actual control over the tasks.

A Task Runner periodically informs the Control Center about its status. This operation is called 'syncing' because most of the times it tells the Control Center what it already knows. Only in case of a changed situation, the Control Center adapts its Task Runner data according to the sync message.
The Task Runner status is also represented by a color.

<table>
	<tr>
		<th>
			Color:
		</th>
		<th>
			Status:
		</th>
		<th>
			Description:
		</th>
	</tr>
	<tr>
		<td>
			white
		</td>
		<td>
			unknown
		</td>
		<td>
			No sync messages received yet since the first time the 'Task Runner Status' page was opened. Wait a moment...
		</td>
	</tr>
	<tr class="free">
		<td class="bright">
			green
		</td>
		<td class="bright">
			free
		</td>
		<td class="bright">
			The Task Runner is free and waiting for a task to run.
		</td>
	</tr>
	<tr class="busy">
		<td class="bright">
			blue
		</td>
		<td class="bright">
			busy
		</td>
		<td class="bright">
			The Task Runner is currently busy with a task.
		</td>
	</tr>
	<tr class="suspended">
		<td class="bright">
			gray
		</td>
		<td class="bright">
			suspended
		</td>
		<td class="bright">
			The Task Runner is suspended by a user.
			The Control Center doesn't assign tasks to it while it has this status.
			The Task Runner is still syncing.
		</td>
	</tr>
	<tr class="warning">
		<td class="bright">
			orange
		</td>
		<td class="bright">
			warning
		</td>
		<td class="bright">
			Recently no sync has been received by the Control Center.
			This could be an indication that something might be wrong,
			but its possible task is still blue.
		</td>
	</tr>
	<tr class="lost">
		<td class="bright">
			red
		</td>
		<td class="bright">
			lost
		</td>
		<td class="bright">
			For a long time no sync has been received by the Control Center.
			The Task Runner is considered as lost. Its possible task is
			automatically aborted and gets the 'error' status.
		</td>
	</tr>
</table>

Deleting a Task Runner record is only possible in the status 'lost'. Note that it doesn't mean that the Task Runner itself is deleted, that is not possible within the SoftFab GUI. Deleting a Task Runner record means that the SoftFab GUI doesn't display the status of this Task Runner anymore until it syncs again.

## Scheduling ![Schedules](/styles/Schedule1.png)

It is possible to schedule a job in the future via the web interface. In order to schedule a job, first a job configuration should be created. Both one-time scheduling and sequentially scheduling are possible. In case of a weekly sequence, more days of the week can be chosen.

Once a Schedule has been created, a record is placed in the 'Schedules' overview. The time of the 'Last Run' will be stored and in case of a sequentially schedule, the time of the 'Next Run' will be calculated automatically. The color of this record represents the status, see table below.

<table>
	<tr>
		<th>
			Color:
		</th>
		<th>
			Status:
		</th>
		<th>
			Description:
		</th>
	</tr>
	<tr class="ok">
		<td class="bright">
			green
		</td>
		<td class="bright">
			ok
		</td>
		<td class="bright">
			The scheduled job will run when the 'Next Run' time has elapsed.
		</td>
	</tr>
	<tr class="canceled">
		<td class="bright">
			gray
		</td>
		<td class="bright">
			finished
		</td>
		<td class="bright">
			The scheduled job will not run anymore.
		</td>
	</tr>
	<tr class="error">
		<td class="bright">
			red
		</td>
		<td class="bright">
			error
		</td>
		<td class="bright">
			The scheduled job cannot run. Probably the corresponding job configuration doesn't exist anymore.
		</td>
	</tr>
</table>

Important to know is that the synchronization of the Task Runner(s) is the actual trigger to initiate a scheduled job. If no Task Runners are active, no scheduled jobs will run.

One very handy additional feature to launch a schedule is the 'Passive', so-called 'API-triggered', sequence. One can use this to build a Continuous Integration (CI) process. See [CM-triggered Build and Test](../cm_triggered_build_and_test) for detailed information.

## SoftFab API
Besides the GUI, a growing set of functionality of the SoftFab can be accessed via the [SoftFab API](../api).
