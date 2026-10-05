"""Shared GitHub-style Markdown parsing for previews and reports."""
from markdown_it import MarkdownIt
from mdit_py_plugins.tasklists import tasklists_plugin
from mdit_py_plugins.container import container_plugin

def markdown_parser():
    parser=MarkdownIt('gfm-like',{'html':False}).use(tasklists_plugin)
    for align in ('left','center','right'):parser.use(container_plugin,'align-'+align)
    parser.use(container_plugin,'figure')
    return parser
