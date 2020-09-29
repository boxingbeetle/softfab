# Factory PC Installation

A Factory PC hosts one or more Task Runners, which handle the actual build and test execution.

Almost any operating system can be used for Factory PC. We have most experience with Windows and Linux, but macOS, Solaris and HP-UX have been used successfully as well.

## Install the Java Runtime

The Task Runner requires the Java runtime environment (JRE) version 8 or higher.

On Debian Linux and distributions derived from it such as Ubuntu, you can install the Java runtime using `sudo apt install default-jre`.

If your operating system does not offer the Java runtime via a package manager, you can [download](https://openjdk.java.net/install/) the open source JDK (development kit), which includes the Java runtime.

## Create a Functional User Account

We recommend to create a dedicated user account on your Factory PC under which the Task Runners are started. This is optional, but it keeps things organized and it reduces the damage that accidents or attacks can do. Don't underestimate how easy it is to remove the wrong directory with a small mistake in a script.

## Create Directories for Reports and Products

The _report directory_ is the working directory for a task: it is where build and test tasks write their reports, logs and results file. Depending on how you design your wrappers, it might also be the location where intermediate files such as object files are written.

The _product directory_ is where a task puts the final output of a job or the products that serve as inputs for other tasks.

If you are going to be installing multiple Factory PCs that will co-operate on the same jobs, you will need a way to share products between them. One way of doing that is using a file server (network drive) for storing products. Another way is using a web server to distribute products: either a web server on each Factory PC or a central web server to which the wrapper uploads products.

## Download the Task Runner JAR

Download the [Task Runner JAR](../../../taskrunner.jar) and put it somewhere accessible to the functional user account. A JAR file can be executed directly by the Java runtime. Multiple Task Runners can share a single `taskrunner.jar`.

## Task Runner Configuration <a id="trconfig"></a>

Every Task Runner needs a configuration file that defines that Task Runner: its identity, what it can do and where it can put the things it produces. If you are using one Task Runner per Factory PC with the binaries installed on the local hard disk, name the configuration file `config.xml`. If you installed the binaries on a network drive or you use more than one Task Runner per Factory PC, you should use a unique file name for each Task Runner instance, for example `config-buildmaster.xml`, `config-testsite1.xml` etc.

<p class="todo">(incomplete)</p>
