# Command Line Interface

The `softfab` command can be used to configure and control your SoftFab Control Center from the command line.

The command line interface is currently limited to setup and user management. It will be expanded over time.

### Scripting

Requested data is written to stdout, while informational messages are written to stderr. Thus, if you are using the `softfab` command from a script, you can capture stdout to use later in the script, while sending stderr to the console or a log file.

The format of plain text output and log messages is not guaranteed to stay identical across SoftFab releases. To avoid your script breaking on upgrades, instead rely on JSON output and exit codes:

exit code 0
:   No errors occurred.

exit code 1
:   An error occurred during execution.

exit code 2
:   No command was not executed because the request was invalid.

### Command Line Help

The information on this page can also be accessed on the command line using the `--help` option, for example:

`$ softfab --help`
:   Show the global options and top-level commands.

`$ softfab user --help`
:   List the user management commands.

`$ softfab user add --help`
:   Show the syntax for adding a user.

<?helptext?>
