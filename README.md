SoftFab
=======

*Web application for orchestrating build and test execution*

Read [here](https://boxingbeetle.com/tools/softfab/) more about SoftFab.
You also can take a look at the [SoftFab factory](https://softfab.io/sf/) where we build and test SoftFab itself.

Work in Progress
----------------

SoftFab in its current state is not easy to install and installations should not be exposed to untrusted networks like the internet. You are welcome to take a look, but to actually use SoftFab, we recommend waiting for the 3.0.0 release that we're working towards.

Feedback
--------

You can report bugs and make feature requests in [SoftFab's issue tracker at GitHub](https://github.com/boxingbeetle/softfab/issues).

If you are interested in sponsoring a new feature, [contact us at Boxing Beetle](https://boxingbeetle.com/contact/).

Contributing
------------

SoftFab requires Python 3.6 or later. It also needs [Graphviz](http://graphviz.org/) to layout execution graphs. The development environment is managed by [Poetry](https://poetry.eustace.io/), which requires `curl` and `pip` to be installed.

If you are using Debian or a Linux distribution derived from Debian such as Ubuntu, you need to install the packages `python3`, `python3-pip`, `python-pip`, `curl` and `graphviz`.

When you have the required packages installed, you can fetch the SoftFab source code from its Git repository:

    $ git clone https://github.com/boxingbeetle/softfab.git

SoftFab uses Poetry to manage its development environment. Using the [recommended installation procedure](https://github.com/sdispater/poetry#installation) instead of pip helps separate Poetry's dependencies from those of the software it manages, like SoftFab.

Create a virtual environment managed by Poetry:

    $ cd softfab
    $ poetry env use python3

Start a shell in this virtual environment:

    $ poetry shell

Install SoftFab and its runtime and development dependencies:

    $ poetry install

Now you should have the `softfab` command available in the Poetry shell:

    $ softfab --version
    SoftFab version 3.0.0-pre1

This command runs SoftFab directly from the source tree, so any code you edit is active the next time you run the `softfab` command.

Now you can create a database directory to test with. The suggested location is a directory named `run` at the top of your cloned Git work area:

    $ softfab --dir run init

By default this will configure the SoftFab Control Center to run on localhost at port 8100. If you want different settings, check `softfab init --help` for options or edit the generated configuration file `run/softfab.ini`.

You can now start the Control Center using the following command:

    $ softfab --dir run --debug server --anonoper

The `--debug` option enables more detailed logging and other debug features. The `--anonoper` option will give any visitor to the Control Center operator privileges, so you don't need to log in while testing. These options are strictly for development and **should not be enabled in production**.

You can now access the Control Center by entering its URL in your web browser. If you used the default configuration, the URL will be [http://localhost:8100/](http://localhost:8100/).

One of the tools Poetry will install for you is [Invoke](https://www.pyinvoke.org/), which can be used to perform a few useful developer tasks. You can see the full list of tasks by running:

    $ inv --list

You can for example use Invoke to start the Control Center using a shorter command line, assuming you used the suggested name `run` for your database directory:

    $ inv run

Another task that can save time during development is `isort`, which runs the [tool of the same name](https://timothycrosley.github.io/isort/) that sorts all import statements in the source code:

    $ inv isort

Before submitting a pull request, please make sure the following tests pass:

- static type check ([mypy](http://www.mypy-lang.org/)): `inv types`
- unit tests ([pytest](https://docs.pytest.org)): `inv unittest`

While we also use [PyLint](http://pylint.pycqa.org/) (`inv lint`), there are known issues reported by PyLint, mostly false positives but also some real but non-critical issues.
