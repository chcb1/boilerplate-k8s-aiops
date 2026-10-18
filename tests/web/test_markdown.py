import pytest

from my_agent_app.web.markdown import render_markdown


def test_script_tag_and_its_content_are_removed():
    html = render_markdown("antes <script>alert(1)</script> depois")

    assert "<script" not in html and "alert(1)" not in html
    assert "antes" in html and "depois" in html


def test_event_handler_attributes_are_removed():
    html = render_markdown("<img src=x onerror=alert(2)> e <b onclick=alert(3)>b</b>")

    assert "onerror" not in html and "onclick" not in html and "<img" not in html


@pytest.mark.parametrize("target", ["javascript:alert(3)", "JaVaScRiPt:alert(3)", "data:text/html;base64,PHNjcmlwdD4=", "vbscript:x"])
def test_dangerous_link_schemes_are_removed(target):
    html = render_markdown(f"[clique]({target})")

    assert target.split(":")[0].lower() not in html.lower().replace("clique", "")
    assert "clique" in html


def test_https_and_mailto_links_are_kept():
    html = render_markdown("[docs](https://example.com/a?b=1) e [ajuda](mailto:sre@example.com)")

    assert 'href="https://example.com/a?b=1"' in html
    assert 'href="mailto:sre@example.com"' in html
    assert "noopener" in html  # rel adicionado pela limpeza


def test_iframe_style_and_form_are_removed():
    html = render_markdown('<iframe src="https://x"></iframe><style>p{}</style><form action="/x"><input></form><p style="color:red">t</p>')

    for fragment in ("<iframe", "<style", "<form", "<input", "style="):
        assert fragment not in html
    assert "<p>t</p>" in html


def test_table_list_heading_and_emphasis_are_rendered():
    html = render_markdown("## Titulo\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n- item **forte**\n- outro\n")

    assert "<h2>Titulo</h2>" in html
    assert "<table>" in html and "<th>a</th>" in html and "<td>2</td>" in html
    assert "<li>item <strong>forte</strong></li>" in html


def test_fenced_command_is_shown_verbatim():
    html = render_markdown("""### Comando Sugerido
```bash
kubectl patch deployment api -n app --type=merge -p '{"env":[{"value":"*x*"}]}'
```
""")

    assert "<pre><code" in html
    assert "<em>" not in html
    assert "*x*" in html
    assert "&quot;env&quot;" in html or '"env"' in html


def test_unfenced_command_would_be_mangled_which_is_why_the_prompt_fences_it():
    html = render_markdown('kubectl patch deployment api -p \'{"value":"*x*"}\'')

    assert "<em>x</em>" in html


def test_empty_and_none_inputs():
    assert render_markdown("") == ""
    assert render_markdown(None) == ""


def test_result_is_marked_safe_for_templates():
    assert hasattr(render_markdown("x"), "__html__")
