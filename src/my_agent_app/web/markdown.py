import markdown
import nh3
from markupsafe import Markup

# O texto dos relatorios vem de um LLM que le logs e eventos arbitrarios do cluster: o HTML
# gerado pelo Markdown (que deixa HTML cru e links javascript: passarem) so e exibido depois de limpo.
ALLOWED_TAGS = {
    "h1", "h2", "h3", "h4", "h5", "h6", "p", "br", "hr", "blockquote",
    "ul", "ol", "li", "strong", "em", "del", "code", "pre",
    "table", "thead", "tbody", "tr", "th", "td", "a",
}
ALLOWED_ATTRIBUTES = {"a": {"href"}, "code": {"class"}}
ALLOWED_URL_SCHEMES = {"http", "https", "mailto"}
CONTENT_TAGS_TO_DROP = {"script", "style"}


def render_markdown(text: str) -> Markup:
    """Converte Markdown em HTML seguro para ser inserido direto em um template."""
    html = markdown.markdown(text or "", extensions=["fenced_code", "tables"])
    clean = nh3.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes=ALLOWED_URL_SCHEMES,
        clean_content_tags=CONTENT_TAGS_TO_DROP,
    )
    return Markup(clean)
