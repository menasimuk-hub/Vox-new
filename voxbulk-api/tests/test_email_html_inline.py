from app.services.email_html_inline import inline_email_css


def test_inline_email_css_applies_class_styles():
    html = (
        '<html><head><style>.btn{color:#fff;background:#16a34a}</style></head>'
        '<body><a class="btn" href="{{trial_url}}">Go</a> {{event-name}}</body></html>'
    )
    out = inline_email_css(html)
    assert "{{trial_url}}" in out
    assert "{{event-name}}" in out
    assert "color:" in out.lower()
    assert "background" in out.lower()


def test_inline_email_css_empty_passthrough():
    assert inline_email_css("") == ""
    assert inline_email_css(None) == ""
