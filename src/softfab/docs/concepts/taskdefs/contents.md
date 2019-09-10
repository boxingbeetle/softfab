# Framework and Task Definitions

The execution of a single task is configured using framework and task definitions.

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
