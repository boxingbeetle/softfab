# Semi-automatic Testing

Ideally, all build and test tasks in your factory run fully automatic. However, there are situations in which it is too difficult or too costly to automate a certain task. In those situations, it is often still possible to automate most of the task, so you can save time compared to doing everything manually. This document describes two strategies for tasks that cannot be fully automated.

The are two strategies for semi-automating tasks that cannot be fully automated:

<a href="#postponed">Postponed Inspection</a>
: This strategy is applicable if the execution of the task can be fully automated, but a human is required to tell whether the task has passed or failed. Execution can run unattended, but the results of the execution have to be inspected afterwards.

<a href="#hip">Human Intervention Point (HIP)</a>
:   This strategy is applicable if the execution of the task requires human intervention. The Task Runner suspends the execution of the task and marks this in SoftFab (yellow) to indicated a human action is required. After the intervention the Task Runner informs SoftFab and execution is resumed. This method is often more efficient than not automating a task at all.

As postponed inspection and human intervention point are two independent strategies, it is possible to use both in the same task, if necessary.

## Postponed Inspection<a id="postponed"></a>

### Scenarios

If you are testing whether a device can play an audio file, it is probably easy to verify whether the device reports that it is playing the file, but this does not necessarily mean it is correctly playing it. With a little effort, you could record the device's audio output and check whether or not it is silent. However, to determine whether it is playing the right file, without glitches and with a decent audio quality, is hard.

In this situation, you could decide to implement only the silence check, but then there are a lot of problems your test won't catch. You could also try to develop algorithms for judging the played audio, but this is likely to become a project in itself. Postponed inspection offers a third option: record the device's audio output and let a human operator listen to it after the test has finished. That way, the entire process of selecting an appropriate device, loading the device with the right software version, selecting the right the file and starting playback is automated, but the judgement whether the audio is correct is done manually.

### Concept

Postponed inspection is a way of separating task execution from determining the task result. Because the execution is finished before inspection starts, all resources that were used to execute the task waiting for inspection are free to be used for executing other tasks.

Postponed inspection allows automatic execution of a task even if determining the result cannot be automated. It saves time if the duration of the execution is significant compared to the duration of the inspection. If task execution cannot be fully automated, use a [human intervention point](#hip) instead.

A wrapper can decide per execution whether postponed inspection is required or not. For example in the scenario outlined above, if you often encounter the situation in which silence is recorded, it is useful to automate the silence check and only ask for postponed inspection if there was actually any sound recorded.

### Implementation

A postponed inspection consists of the following steps:

1.  **Record test results**
    The wrapper should record test results so they can be inspected later. This could be making a video or audio recording, writing a detailed log file or anything else depending on the test.
2.  **Request postponed inspection**
    The wrapper should tell the Control Center that postponed inspection is required to know the result of the executed task. This is done by passing the result code "inspect" in the results file; see the [Writing a Wrapper](../../reference/wrappers/#passing_results) document for details.
3.  **Offer the user an interface for inspecting the results**
    The user should be presented the recorded test results and given an interface to judge them. Typically this is done with a CGI script on the web server that serves the test reports. For example, the user might be presented a page with a form containing a series of screen captures with next to each capture a set of radio buttons to select "pass" or "fail".
4.  **Report inspection result**
    The Control Center should be told that the postponed inspection has finished and what the result of it was. This is done using the [InspectDone](../../reference/api/#InspectDone)  API call. If the previous step was implemented with a CGI script, that CGI script can make the API call when the user submits the form.

### Example

<p class="todo">
TODO: Re-do the examples for SoftFab 3.0+.<br/>
</p>

## Human Intervention Point (HIP)<a id="hip"></a>

### Scenarios

A device with an optical drive might require a specific disc to be inserted for a particular test. If this is needed very often, it is worth investing in a mechanical disc changer, but if this type of test is run infrequently it might be more efficient to manually change the discs. A human intervention point will tell the operator when a disc has to be changed.

Another use for the human intervention point would be if you have a mechanical disc changer, but it is not 100% reliable. If your setup can detect when the mechanical changer fails, the wrapper can signal a HIP to alert the operator when the automatic disc change has failed.

### Concept

A human intervention point is a way to draw the attention of a human operator when some kind of manual intervention has to take place during task execution. During a HIP task execution is suspended, so any resources in use by the task execution (Task Runner and additional reserved resources) are not available for other tasks.

A human intervention point is useful if task execution can be mostly, but not fully, automated. For tasks of which very little can be automated, it might be better to execute them manually outside SoftFab. For tasks of which the execution can be fully automated but judging of results cannot, [postponed inspection](#postponed) is better suited.

### Implementation

A human intervention point is controlled by the wrapper in three steps:

1.  **Signal start of human intervention point**
    The wrapper notifies the Control Center that the task execution has reached a human intervention point. This is done using the [TaskAlert](../../reference/api/#TaskAlert)  API call.
2.  **Wait for user to perform the required action**
    The wrapper should suspend execution until the required manual action has been taken. In some cases it is possible to automatically detect that the action has been completed. In other cases the user is required to indicate that the action has been performed, for example by pressing a button.
3.  **Signal end of human intervention point**
    The wrapper should tell the Control Center that the task execution is no longer stuck in a human intervention point. This is also done using the [TaskAlert](../../reference/api/#TaskAlert)  API call.

### Example

<p class="todo">
TODO: Re-do the examples for SoftFab 3.0+.<br/>
</p>
