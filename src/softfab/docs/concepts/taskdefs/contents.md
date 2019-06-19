# Framework and Task Definitions

This document describes what framework and task definitions are and how you can create them. It builds on the concepts explained in the [Execution Graph](../exegraph/) document.

## Inheritance

Tasks are defined using a layered system, where each layer inherits properties from a parent definition from the layer above it:

1. Wrapper
2. Framework
3. Task definition

So every task definition has one framework and every framework has one wrapper. However, one wrapper can be used by multiple frameworks and one framework can be used by multiple task definitions. For example a unit test framework could be used by many task definitions that define one test suite each.

## Wrapper

A wrapper is a script that forms the glue between SoftFab and an arbitrary third party tool. A typical wrapper script takes a few variables that are defined by SoftFab and uses those to invoke the build or test tool. Afterwards, the wrapper looks at the results of the build or test tool and puts that information in a format that SoftFab understands.

A wrapper executes on a Factory PC. The Task Runner is responsible for starting a wrapper, providing it with the right variables and passing the results to the Control Center.

The implementation of a wrapper script is documented in [Writing a Wrapper](../../reference/wrappers/).

There is no wrapper configuration page on the Control Center: instead the inputs, output and parameters of a wrapper are defined as part of a framework.

### Execution Wrapper versus Extraction Wrapper<a id="extract"></a>

With SoftFab it is possible to store [mid-level data](../midlevel/) and to visualize this data by plotting trend graphs (number of lines of code, number of problems reported by a static code check tool etc.) This mid-level data has to be extracted from a low-level log report or from the executing environment and stored in the factory. The following two ways are available to send the extracted mid-level data to the Control Center:

execution wrapper
:   Mid-level data can extracted as part of the task execution; the data is included in the execution results file.

extraction wrapper
:   Mid-level data can be extracted by a separate extraction wrapper, which runs as a separate "shadow" task.

It is possible to do task post-processing, such as extraction of mid-level data, as a separate "shadow" task. A "shadow" task always runs directly after the execution task when it finished and before a next execution task starts (if any). An "extraction" task (as opposed to "execution" task) does not appear in the list of tasks belonging to the job. The advantage of a separate "extraction wrapper" is mainly to split mid-level data extraction from the execution wrapper. Sometimes another more suitable script language is used (e.g. Perl or Python) to do the data extraction from low level (text) reports. The extraction task must produce a file called 'extracted.properties', containing the mid-level data fields and their values. It is not possible to extract mid-level data in both the wrapper script (execution task) and the extractor script (extraction task) for the same task (framework). It is strongly advised not to put 'data.<key\>=<value\>' in both the files: 'results.properties' and 'extracted.properties'.

If the "Extract" checkbox is checked on the framework definition edit page, it means the tasks that use this framework will have a "shadow" task attached to them to perform mid-level data extraction. The wrapper for a shadow task is slightly different tough: they use different file names for the wrapper script and for the results file. The extraction wrapper file is called 'extractor._ext_', where the extension is specific for the chosen script language.

## Framework Definition<a id="frameworkdef"></a>

You can [define frameworks](../../../FrameworkIndex) in the Control Center configuration.

The wrapper name is used by the Task Runner on a Factory PC to find the appropriate wrapper script for this framework. It starts at the wrappers base directory defined in the Task Runner's `config.xml`. In that directory, it looks for a subdirectory with the same name as the wrapper. Inside that subdirectory, it looks for a file named <code>wrapper.<i>ext</i></code>, where <code><i>ext</i></code> can be `bat`, `sh`, `pl`, `py`, etc. depending on the language the wrapper is implemented in (more about that later). _Example path:_ `../wrappers/export/wrapper.sh`. The reason for having a subdirectory per wrapper is that many wrapper scripts need support files, such as postprocessing scripts, templates for configuration files or files containing passwords (it is a good practice to keep passwords out of CM).

Next, you can configure input and output products. You can only select from [products that have been already defined](../../../ProductIndex).

Finally, you can define parameters if required. Parameters are key/value pairs that are passed to the wrapper. Parameters are defined in a hierarchy: first is the framework level, then the task definition level and finally the execution level. At each level, it is possible to override the value provided by the previous level, unless that previous level declared the parameter as "final".

Parameters are typically used in the following situations:

*   To centralize a piece of configuration, such as the location of your CM server. In this case, you will probably want to prevent this value from being overridden in the task definition, so you should check the "Final" checkbox.
*   To use the same wrapper for multiple frameworks. For example, a typical project will have a top-level Make (C/C++ projects) or Ant (Java projects) file which has multiple targets for building, documentation extraction, static code tests etc. The Make/Ant target could be a parameter. In this case, it is also a good idea to make the parameter final.
*   To use the same framework for multiple task definitions. For example a unittest can have a parameter that selects which components should be tested. Or a duration test can have a parameter for how many test iterations should be executed. In this case you can define the parameter on the framework level and provide a default value. Do not check the "Final" checkbox, to allow the value to be overridden in the Task Definition.

## Task Definition

There is a 1-to-n relation between a framework and task definitions (where n\>=1). This means for every framework one task definition has to be created always (n=1). In some cases you will have to create more than one task definition using the same framework's wrapper. For example a test framework can be used by many task definitions, each task definition performing a specific test case (e.g. different input files) Then the test framework's wrapper needs an input parameter to define what testfile it has to test. This can be done, by creating multiple task definitions using the same test framework.

You can [define tasks](../../../TaskIndex) in the Control Center configuration.

Be aware, in the execution graph, the task definitions are not visible, only frameworks and products. This keeps the execution graph clear.

## Task Capabilities

Not every Task Runner is necessarily capable of executing every framework. E.g. on the first Factory PC a specific test tool is installed, while on the rest of the Factory PC's it is not. The Task Runner on the first Factory PC has the capability to perform the tests using this specific test tool, while the other Factory PC's are not capable to perform these tests. Only the Task Runner on the first Factory PC is allowed to run the test task. This can be configured in the task definition by declaring a capability. Thus, capabilities are used to declare which frameworks a Task Runner can execute. You can choose a capability name yourself and fill it in. Add the capability to the capability list of the aimed Task Runners on the 'Edit Task Runner' page in "Resources".

## Configurations

To execute tasks, first a configuration has to be created. A configuration contains one or more tasks. E.g. you can create a configuration to perform all tasks or a configuration without tests or a configuration with only some major tests. You can create a configuration by using [Execute from Scratch](../../../Execute). Next you will see a list of all the task definitions to choose from. You can further save this as a new configuration, or run it at once.
