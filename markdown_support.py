"""Shared GitHub-style Markdown parsing for previews and reports."""
from html import escape
from markdown_it import MarkdownIt
from mdit_py_plugins.tasklists import tasklists_plugin
from mdit_py_plugins.container import container_plugin
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import TextLexer, get_lexer_by_name
from pygments.util import ClassNotFound


def render_fence(tokens, index, options, environment):
    token = tokens[index]
    language = token.info.strip().split(
        None, 1)[0] if token.info.strip() else ""
    try:
        lexer = get_lexer_by_name(language) if language else TextLexer()
    except ClassNotFound:
        lexer = TextLexer()
    language_class = (
        ' class="language-' +
        escape(language, quote=True) + '"' if language else ""
    )
    code = highlight(token.content, lexer, HtmlFormatter(nowrap=True))
    return '<pre class="code-block"><code' + language_class + ">" + code + "</code></pre>\n"


def markdown_parser():
    parser = MarkdownIt('gfm-like', {'html': False}).use(tasklists_plugin)
    for align in ('left', 'center', 'right'):
        parser.use(container_plugin, 'align-'+align)
    parser.use(container_plugin, 'figure')
    parser.renderer.rules['fence'] = render_fence
    return parser
