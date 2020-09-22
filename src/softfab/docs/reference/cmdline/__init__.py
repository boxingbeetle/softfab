# SPDX-License-Identifier: BSD-3-Clause

from pathlib import Path
from typing import Iterable, Iterator, List, Optional, cast

from click import (
    Argument, Choice, Command, Context, MultiCommand, Option, Parameter
)

from softfab import cmdline
from softfab.docserve import piHandler
from softfab.xmlgen import XMLContent, xhtml

button = 'Command Line'
children = ()
icon = 'IconDocs'

@piHandler
def helptext(arg: str) -> XMLContent:
    ctx = Context(cmdline.main)
    yield xhtml.h3['Global Options']
    # We only have global options, not global arguments.
    globalOptions = cast(Iterable[Option], cmdline.main.params)
    yield presentOptions(ctx, globalOptions)
    yield xhtml.h3['Top-level Commands']
    yield from presentSubcommands(ctx, cmdline.main)

def rootPath(ctx: Optional[Context], command: Command) -> Iterable[str]:
    path: List[str] = []
    while ctx is not None:
        path.insert(0, command.name)
        command = ctx.command
        ctx = ctx.parent
    return path

def presentCommand(ctx: Context, command: Command) -> Iterator[XMLContent]:
    options = []
    arguments = []
    for param in command.params:
        if isinstance(param, Option):
            options.append(param)
        elif isinstance(param, Argument):
            arguments.append(param)

    words = rootPath(ctx, command)
    title: List[XMLContent] = ['softfab']
    title += words
    title += [presentParameter(arg) for arg in arguments]
    yield xhtml.h3[xhtml.code[xhtml[' '].join(title)],
                   xhtml.a(id='-'.join(words))]
    yield from presentHelpBlocks(ctx, command)
    yield presentOptions(ctx, options)
    if isinstance(command, MultiCommand):
        yield from presentSubcommands(Context(command, ctx), command)

def presentHelpBlocks(ctx: Context, command: Command) -> Iterator[XMLContent]:
    text = command.help
    if text is not None:
        for block in text.split('\n\n'):
            yield xhtml.p[presentHelpParagraph(block)]

def presentHelpParagraph(text: str) -> XMLContent:
    first = True
    for word in text.split():
        if first:
            first = False
        else:
            yield ' '
        if word.startswith('--'):
            yield xhtml.code[word]
        elif word[0] == word[-1] == "'":
            yield xhtml.code[word[1:-1]]
        else:
            yield word

def presentSubcommands(ctx: Context,
                       parent: MultiCommand
                       ) -> Iterator[XMLContent]:
    prefix = ''.join(f'{word}-' for word in rootPath(ctx.parent, parent))
    yield xhtml.dl[(
        xhtml.dt[xhtml.code[
            xhtml.a(href=f'#{prefix}{command.name}')[command.name]
            ]] +
        xhtml.dd[command.get_short_help_str(limit=1000)]
        for command in iterCommands(ctx, parent)
        )]
    for command in iterCommands(ctx, parent):
        yield from presentCommand(ctx, command)

def iterCommands(ctx: Context, parent: MultiCommand) -> Iterator[Command]:
    for name in parent.list_commands(ctx):
        command = parent.get_command(ctx, name)
        assert command is not None, name
        yield command

def presentOptions(ctx: Context, options: Iterable[Option]) -> XMLContent:
    return xhtml.dl[(
        xhtml.dt[presentOptionSyntax(option)] +
        xhtml.dd[presentOptionHelp(ctx, option)]
        for option in sorted(options, key=optionSortKey)
        )]

def presentOptionSyntax(option: Option) -> XMLContent:
    yield xhtml[', '].join(xhtml.code[opt] for opt in option.opts)
    if not option.is_flag:
        yield ' ', xhtml.code[presentParameter(option)]

def presentOptionHelp(ctx: Context, option: Option) -> XMLContent:
    yield option.help
    if not option.is_flag:
        default = option.get_default(ctx)
        if default is not None:
            value: XMLContent = str(default)
            if isinstance(default, Path) and value == '.':
                value = 'current directory'
            else:
                value = xhtml.code[value]
            yield xhtml.br, xhtml.em['default:'], ' ', value

def presentParameter(param: Parameter) -> XMLContent:
    if isinstance(param.type, Choice):
        return '|'.join(param.type.choices)
    else:
        return xhtml.em[param.name]

def optionSortKey(option: Option) -> object:
    for opt in option.opts:
        if opt.startswith('--'):
            return opt[2:]
    assert False, option.opts
