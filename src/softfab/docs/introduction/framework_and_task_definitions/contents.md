# Framework and Task Definitions

This document describes what framework and task definitions are and how you can create them. It builds on the concepts explained in the [Execution Graph](/introduction/execution_graph/) document.

##Control Center Configuration

### Framework Definition<a id="frameworkdef"></a>

You can add a framework definition by starting at the home page and select Configure / Design / Frameworks / Create New Framework in the top navigation bar.

The wrapper name is used by the Task Runner on a Factory PC to find the appropriate wrapper script for this framework. It starts at the wrappers base directory defined in the Task Runner's `config.xml`. In that directory, it looks for a subdirectory with the same name as the wrapper. Inside that subdirectory, it looks for a file named <code>wrapper.<i>ext</i></code>, where <code><i>ext</i></code> can be `bat`, `sh`, `pl`, `py`, etc. depending on the language the wrapper is implemented in (more about that later). _Example path:_ `../wrappers/export/wrapper.sh`. The reason for having a subdirectory per wrapper is that many wrapper scripts need support files, such as postprocessing scripts, templates for configuration files or files containing passwords (it is a good practice to keep passwords out of CM).

Next, you can configure input and output products. You can only select from products that have been already defined, so if you need an additional product, go to Configure / Design / Products / Create New Product to add it.

Finally, you can define parameters if required. Parameters are key/value pairs that are passed to the wrapper. Parameters are defined in a hierarchy: first is the framework level, then the task definition level and finally the execution level. At each level, it is possible to override the value provided by the previous level, unless that previous level declared the parameter as "final".

Parameters are typically used in the following situations:

*   To centralize a piece of configuration, such as the location of your CM server. In this case, you will probably want to prevent this value from being overridden in the task definition, so you should check the "Final" checkbox.
*   To use the same wrapper for multiple frameworks. For example, a typical project will have a top-level Make (C/C++ projects) or Ant (Java projects) file which has multiple targets for building, documentation extraction, static code tests etc. The Make/Ant target could be a parameter. In this case, it is also a good idea to make the parameter final.
*   To use the same framework for multiple task definitions. For example a unittest can have a parameter that selects which components should be tested. Or a duration test can have a parameter for how many test iterations should be executed. In this case you can define the parameter on the framework level and provide a default value. Do not check the "Final" checkbox, to allow the value to be overridden in the Task Definition.

### Task Definition

There is a 1-to-n relation between a framework and task definitions (where n\>=1). This means for every framework one task definition has to be created always (n=1). In some cases you will have to create more than one task definition using the same framework's wrapper. For example a test framework can be used by many task definitions, each task definition performing a specific test case (e.g. different input files) Then the test framework's wrapper needs an input parameter to define what testfile it has to test. This can be done, by creating multiple task definitions using the same test framework.

You can add a Task Definition by starting at the home page and select Configure / Design / Task Definition / Create New Task Definition in the top navigation bar. Be aware, in the execution graph, the task definitions are not visible, only frameworks and products. This keeps the execution graph clear.

### Task Capabilities

Not every Task Runner is necessarily capable of executing every framework. E.g. on the first Factory PC a specific test tool is installed, while on the rest of the Factory PC's it is not. The Task Runner on the first Factory PC has the capability to perform the tests using this specific test tool, while the other Factory PC's are not capable to perform these tests. Only the Task Runner on the first Factory PC is allowed to run the test task. This can be configured in the task definition by declaring a capability. Thus, capabilities are used to declare which frameworks a Task Runner can execute. You can choose a capability name yourself and fill it in. Add the capability to the capability list of the aimed Task Runners on the 'Edit Task Runner' page in "Resources"

### Configurations

To execute tasks, first a configuration has to be created. A configuration contains one or more tasks. E.g. you can create a configuration to perform all tasks or a configuration without tests or a configuration with only some major tests. You can create a configuration by starting at the home page and select Execute / Execute from scratch. Next you will see a list of all the task definitions to choose from. You can further save this as a new configuration, or run it at once.

### Execution Tasks versus Extraction Tasks<a id="extract"></a>

With SoftFab it is possible to store mid-level data and to visualize this so-called mid-level data by plotting trend graphs (examples are e.g. number of lines of code, number of problems reported by a static code check tool, number of compiler errors/warnings, etc.) In this way it is possible to track the evolution of the software developed in the project. It will help to run and lead the project if the extracted data is chosen well. In order to plot a trend graph, the mid-level data has to be extracted from a low-level log report or from the executing environment and stored in the factory. In SoftFab the following two ways are available to send the extracted mid-level data to the control center:

*   **execution task**: add mid-level data extraction code to the wrapper script. How to write extraction code in your wrappers is script language specific. Some examples are available in the [Shared Wrappers](/installation/wrappers/shared_wrappers) web-page. Please read also the document about generating [Mid-level Data](/introduction/mid_level_data/).
*   **extraction task**: add mid-level data extraction code to an additional extraction wrapper, which runs as a separate "shadow" task. The extraction tasks are to be phased-out in a future version of SoftFab. Do not start writing new extraction wrappers, but perform the extraction code in the regular wrapper (execution wrapper).

Here the "extraction task" is explained (for maintenance reasons). It is possible to do task post-processing, such as extraction of mid-level data, as a separate "shadow" task. A "shadow" task always runs directly after the execution task when it finished and before a next execution task starts (if any). An "extraction" task (as opposed to "execution" task) does not appear in the list of tasks belonging to the job. The advantage of a separate "extraction wrapper" is mainly to split mid-level data extraction from the execution wrapper. Sometimes another more suitable script language is used (e.g. Perl or Python) to do the data extraction from low level (text) reports. The extraction task must produce a file called 'extracted.properties', containing the mid-level data fields and their values. It is not possible to extract mid-level data in both the wrapper script (execution task) and the extractor script (extraction task) for the same task (framework). It is strongly advised not to put 'data.<key\>=<value\>' in both the files: 'results.properties' and 'extracted.properties'.

If the "Extract" checkbox is checked on the framework definition edit page, it means the tasks that use this framework will have a "shadow" task attached to them to perform mid-level data extraction. The wrapper for a shadow task is slightly different tough: they use different file names for the wrapper script and for the results file. The extraction wrapper file is called 'extractor._ext_', where the extension is specific for the chosen script language.

## Related Documentation
#### Execution Graph
The [Execution Graph](/introduction/execution_graph/) is the language we use for modeling the build and test process.

#### Writing a Wrapper
To implement execution of defined tasks (and extraction of mid-level data), wrappers should be written. The [Writing a Wrapper](/installation/wrappers/writing_a_wrapper/) document explains how this works.
