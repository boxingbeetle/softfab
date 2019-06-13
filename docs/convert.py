#!/usr/bin/env python3
#
# SPDX-License-Identifier: BSD-3-Clause

from pathlib import Path

from lektor.cli import Context

toc_fragment = '''
```sf
toc
```
'''

doc_dir = Path(__file__).resolve().parent

def collect_page(page):
    meta = dict(
        src=Path(page.source_filename),
        button=page['button'],
        abstract=page['abstract'],
        title=page['title']
        )

    abstract = meta['abstract'].source.strip()
    if abstract and abstract[-1].isalnum():
        abstract += '.'

    content = [
        '# %s' % meta['title'],
        abstract
        ]

    model_name = page.datamodel.name
    if model_name == 'Page':
        content.append(page['body'].source)
    elif model_name == 'Toc':
        content += [
            page['pre_toc'].source,
            toc_fragment,
            page['post_toc'].source
            ]
    else:
        assert False

    return meta, '\n\n'.join(
        fragment.strip()
        for fragment in content
        if fragment.strip()
        ) + '\n'

def write_init(out_dir, meta, children):
    content = '''# SPDX-License-Identifier: BSD-3-Clause

button = '{button}'
children = {children}
'''.format(children=tuple(children), **meta)

    init_file = out_dir / '__init__.py'
    init_file.write_text(content)

def write_content(out_dir, content):
    content_file = out_dir / 'contents.md'
    content_file.write_text(content)

def convert_page(out_dir, page, children):
    print('converting:', page)
    meta, content = collect_page(page)

    write_init(out_dir, meta, children)
    write_content(out_dir, content)

def convert_pages(out_dir, page):
    out_dir.mkdir()

    children = []
    for child in page.children.include_undiscoverable(True):
        slug = child['_slug']
        children.append(slug)
        convert_pages(out_dir / slug, child)

    convert_page(out_dir, page, children)

if __name__ == '__main__':
    context = Context()
    env = context.get_env()
    pad = env.new_pad()
    root = pad.get_root()

    src_dir = doc_dir.parent / 'src' / 'softfab' / 'docs'
    convert_pages(src_dir, root)
